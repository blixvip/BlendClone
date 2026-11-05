"""Per-frame fidelity scoring of a rendered remake against its reference.

Both videos are decoded through the same explicit color conversion, and the
render is first encoded at the reference bitrate, so the remake is not penalized
for being sharper than a compressed source. Scores are evidence, not proof: the
verdict never says "1:1" unless calibrated gates pass on every frame, and even
then visual review is still required.
"""
import json
import math
import os
import subprocess
from pathlib import Path

import cv2
import numpy as np

from .process import Cancelled, run

ROOT = Path(__file__).resolve().parents[1]
GATES_PATH = ROOT / 'app' / 'fidelity_gates.json'
ANALYSIS_EDGE = 540
TILE_COLUMNS = 6
FRAME_METRICS = ('coarse_ssim', 'delta_e', 'flow_epe')
LIMITATIONS = [
    'Frame metrics report the worst tile of a grid, not per-object silhouettes. Object masks and a learned perceptual metric are not yet measured.',
    'Passing metrics do not replace watching the remake against the reference.',
]


def load_gates(path=GATES_PATH):
    data = json.loads(Path(path).read_text(encoding='utf-8'))
    for key in ('coarse_ssim_min', 'delta_e_max', 'flow_epe_max', 'timing_lag_max'):
        if not isinstance(data['gates'].get(key), (int, float)) or not math.isfinite(data['gates'][key]):
            raise ValueError(f'Fidelity gate {key} is missing or invalid.')
    return data


def probe(video):
    data = json.loads(run(['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-count_frames', '-show_entries',
        'stream=width,height,r_frame_rate,nb_read_frames,bit_rate,color_range,color_space:format=bit_rate',
        '-of', 'json', video], timeout=120))
    stream, fmt = data['streams'][0], data.get('format', {})
    numerator, denominator = stream['r_frame_rate'].split('/')
    bitrate = stream.get('bit_rate') or fmt.get('bit_rate') or 2_000_000
    return dict(width=int(stream['width']), height=int(stream['height']), fps=float(numerator) / float(denominator),
                frames=int(stream.get('nb_read_frames') or 0), bitrate=int(bitrate),
                color_range=stream.get('color_range', 'tv'), color_space=stream.get('color_space', ''))


def analysis_size(reference, other):
    edge = min(ANALYSIS_EDGE, max(reference['width'], reference['height']), max(other['width'], other['height']))
    scale = edge / max(reference['width'], reference['height'])
    return max(2, round(reference['width'] * scale / 2) * 2), max(2, round(reference['height'] * scale / 2) * 2)


def decode(video, info, size, cancel=None):
    """Yield RGB uint8 frames at ``size`` with range and matrix stated explicitly."""
    width, height = size
    matrix = 'bt709' if info['color_space'] in ('bt709', '') and max(info['width'], info['height']) >= 720 else 'bt601'
    source_range = 'pc' if info['color_range'] in ('pc', 'jpeg') else 'tv'
    args = ['ffmpeg', '-v', 'error', '-i', str(video), '-vf',
            f'scale={width}:{height}:flags=area:in_range={source_range}:in_color_matrix={matrix}:out_range=pc,format=rgb24',
            '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-']
    proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
                            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
    frame_bytes = width * height * 3
    try:
        while True:
            if cancel is not None and cancel.is_set():
                raise Cancelled()
            chunk = proc.stdout.read(frame_bytes)
            if len(chunk) < frame_bytes:
                break
            yield np.frombuffer(chunk, np.uint8).reshape(height, width, 3)
    finally:
        if proc.poll() is None:
            proc.terminate()  # Only the decoder this function started.
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
        proc.stdout.close()


def ssim_map(x, y):
    x, y = x.astype(np.float64), y.astype(np.float64)
    c1, c2 = (0.01 * 255) ** 2, (0.03 * 255) ** 2
    blur = lambda image: cv2.GaussianBlur(image, (11, 11), 1.5)
    mx, my = blur(x), blur(y)
    vx, vy, cxy = blur(x * x) - mx * mx, blur(y * y) - my * my, blur(x * y) - mx * my
    return ((2 * mx * my + c1) * (2 * cxy + c2)) / ((mx * mx + my * my + c1) * (vx + vy + c2))


def ssim(x, y):
    return float(ssim_map(x, y).mean())


def tile_means(values, columns=TILE_COLUMNS):
    """Mean of each tile in a grid, so a small wrong region is not averaged away by a correct frame."""
    height, width = values.shape[:2]
    rows = max(2, round(columns * height / width))
    ys = np.linspace(0, height, rows + 1).astype(int)
    xs = np.linspace(0, width, columns + 1).astype(int)
    return np.array([values[ys[r]:ys[r + 1], xs[c]:xs[c + 1]].mean() for r in range(rows) for c in range(columns)])


def lab(rgb):
    return cv2.cvtColor(rgb.astype(np.float32) / 255, cv2.COLOR_RGB2Lab).astype(np.float64)


def ciede2000(lab1, lab2):
    """CIEDE2000 color difference (Sharma, Wu & Dalal 2005), vectorized."""
    L1, a1, b1 = lab1[..., 0], lab1[..., 1], lab1[..., 2]
    L2, a2, b2 = lab2[..., 0], lab2[..., 1], lab2[..., 2]
    c_bar = (np.hypot(a1, b1) + np.hypot(a2, b2)) / 2
    g = 0.5 * (1 - np.sqrt(c_bar ** 7 / (c_bar ** 7 + 25 ** 7)))
    a1p, a2p = (1 + g) * a1, (1 + g) * a2
    c1p, c2p = np.hypot(a1p, b1), np.hypot(a2p, b2)
    h1p, h2p = np.degrees(np.arctan2(b1, a1p)) % 360, np.degrees(np.arctan2(b2, a2p)) % 360
    chroma_zero = c1p * c2p == 0
    dh = h2p - h1p
    dh = np.where(dh > 180, dh - 360, np.where(dh < -180, dh + 360, dh))
    dh = np.where(chroma_zero, 0, dh)
    dL, dC = L2 - L1, c2p - c1p
    dH = 2 * np.sqrt(c1p * c2p) * np.sin(np.radians(dh / 2))
    L_bar, c_bar_p, h_sum = (L1 + L2) / 2, (c1p + c2p) / 2, h1p + h2p
    h_bar = np.where(np.abs(h1p - h2p) > 180, np.where(h_sum < 360, (h_sum + 360) / 2, (h_sum - 360) / 2), h_sum / 2)
    h_bar = np.where(chroma_zero, h_sum, h_bar)
    t = (1 - .17 * np.cos(np.radians(h_bar - 30)) + .24 * np.cos(np.radians(2 * h_bar))
         + .32 * np.cos(np.radians(3 * h_bar + 6)) - .20 * np.cos(np.radians(4 * h_bar - 63)))
    theta = 30 * np.exp(-((h_bar - 275) / 25) ** 2)
    rc = 2 * np.sqrt(c_bar_p ** 7 / (c_bar_p ** 7 + 25 ** 7))
    sl = 1 + .015 * (L_bar - 50) ** 2 / np.sqrt(20 + (L_bar - 50) ** 2)
    sc, sh = 1 + .045 * c_bar_p, 1 + .015 * c_bar_p * t
    rt = -np.sin(np.radians(2 * theta)) * rc
    return np.sqrt((dL / sl) ** 2 + (dC / sc) ** 2 + (dH / sh) ** 2 + rt * (dC / sc) * (dH / sh))


def coarse(rgb):
    height, width = rgb.shape[:2]
    return cv2.resize(cv2.GaussianBlur(rgb, (0, 0), 2), (max(8, width // 4), max(8, height // 4)), interpolation=cv2.INTER_AREA)


def best_lag(a, b, limit=5):
    """Frame offset that best aligns two change curves; 0 means events land on the same frames."""
    a, b = np.asarray(a, float), np.asarray(b, float)
    if len(a) < 3 or a.std() == 0 or b.std() == 0:
        return 0, None
    scores = {}
    for lag in range(-limit, limit + 1):
        x, y = (a[lag:], b[:len(b) - lag]) if lag >= 0 else (a[:lag], b[-lag:])
        n = min(len(x), len(y))
        if n >= 3 and x[:n].std() and y[:n].std():
            scores[lag] = float(np.corrcoef(x[:n], y[:n])[0, 1])
    if not scores:
        return 0, None
    lag = max(scores, key=lambda key: (scores[key], -abs(key)))
    return lag, scores.get(0)


def compare(reference_video, remake_video, cancel=None, gates=None):
    gates = gates or load_gates()
    ref_info, remake_info = probe(reference_video), probe(remake_video)
    size = analysis_size(ref_info, remake_info)
    flow = cv2.DISOpticalFlow_create(cv2.DISOPTICAL_FLOW_PRESET_MEDIUM)
    records, ref_changes, remake_changes = [], [], []
    previous = None
    flow_scale = ANALYSIS_EDGE / max(size)
    for index, (a, b) in enumerate(zip(decode(reference_video, ref_info, size, cancel), decode(remake_video, remake_info, size, cancel))):
        ga, gb = cv2.cvtColor(a, cv2.COLOR_RGB2GRAY), cv2.cvtColor(b, cv2.COLOR_RGB2GRAY)
        ca, cb = coarse(a), coarse(b)
        coarse_gray = cv2.cvtColor(ca, cv2.COLOR_RGB2GRAY), cv2.cvtColor(cb, cv2.COLOR_RGB2GRAY)
        record = dict(frame=index, ssim=round(ssim(ga, gb), 5),
                      coarse_ssim=round(float(tile_means(ssim_map(*coarse_gray)).min()), 5),
                      delta_e=round(float(tile_means(ciede2000(lab(ca), lab(cb))).max()), 4), flow_epe=None)
        if previous is not None:
            pa, pb = previous
            fa, fb = flow.calc(pa, ga, None), flow.calc(pb, gb, None)
            record['flow_epe'] = round(float(tile_means(np.linalg.norm(fa - fb, axis=2)).max() * flow_scale), 4)
            ref_changes.append(float(np.abs(ga.astype(np.int16) - pa).mean()))
            remake_changes.append(float(np.abs(gb.astype(np.int16) - pb).mean()))
        previous = (ga, gb)
        record['passes'] = frame_passes(record, gates['gates'])
        records.append(record)
    lag, correlation = best_lag(ref_changes, remake_changes)
    return build_report(ref_info, remake_info, size, records, lag, correlation, gates)


def frame_passes(record, gates):
    return bool(record['coarse_ssim'] >= gates['coarse_ssim_min'] and record['delta_e'] <= gates['delta_e_max']
                and (record['flow_epe'] is None or record['flow_epe'] <= gates['flow_epe_max']))


def build_report(ref_info, remake_info, size, records, lag, correlation, gates):
    g = gates['gates']
    count_match = ref_info['frames'] == remake_info['frames'] == len(records)
    fps_match = abs(ref_info['fps'] - remake_info['fps']) < 1e-3
    timing_ok = count_match and fps_match and abs(lag) <= g['timing_lag_max']
    passing = sum(r['passes'] for r in records)
    metrics = {}
    for name in ('ssim',) + FRAME_METRICS:
        values = [r[name] for r in records if r[name] is not None]
        if values:
            worst = min(values) if name.endswith('ssim') else max(values)
            metrics[name] = dict(mean=round(float(np.mean(values)), 4), worst=round(float(worst), 4))
    all_pass = bool(records) and passing == len(records) and timing_ok
    if all_pass and gates.get('calibrated'):
        verdict = 'metrics-pass'
    elif all_pass:
        verdict = 'metrics-pass-uncalibrated'
    else:
        verdict = 'approximate'
    ranked = sorted(records, key=lambda r: (r['coarse_ssim'], -r['delta_e']))
    return dict(verdict=verdict, calibrated=bool(gates.get('calibrated')), gates=g,
                reference=ref_info, remake=remake_info, analysis_size=list(size),
                timing=dict(frame_count_match=count_match, fps_match=fps_match, lag_frames=lag,
                            change_correlation=None if correlation is None else round(correlation, 4), passes=timing_ok),
                frames=len(records), passing_frames=passing, metrics=metrics,
                worst_frames=[r['frame'] for r in ranked[:20]], per_frame=records, limitations=LIMITATIONS)


def encode_like(frames_pattern, fps, reference_info, output, cancel=None):
    """Encode render frames with the reference's codec settings so compression affects both sides alike."""
    bitrate = reference_info['bitrate']
    run(['ffmpeg', '-y', '-v', 'error', '-framerate', repr(fps), '-i', str(frames_pattern),
         '-vf', 'scale=out_color_matrix=bt709:out_range=tv,format=yuv420p', '-c:v', 'libx264', '-preset', 'medium',
         '-b:v', str(bitrate), '-maxrate', str(int(bitrate * 1.5)), '-bufsize', str(bitrate * 2),
         '-color_range', 'tv', '-colorspace', 'bt709', '-color_primaries', 'bt709', '-color_trc', 'bt709', str(output)],
        timeout=900, cancel=cancel)


def score_run(reference_video, attempt, meta, cancel=None):
    config = json.loads((attempt / 'animation.config.json').read_text(encoding='utf-8'))
    fps = config['fps'] / config.get('fps_base', 1)
    encoded = attempt / 'fidelity-encoded.mp4'
    encode_like(attempt / 'frames' / 'frame-%04d.png', fps, probe(reference_video), encoded, cancel)
    report = compare(reference_video, encoded, cancel)
    pending = attempt / 'fidelity.json.tmp'
    pending.write_text(json.dumps(report, indent=2), encoding='utf-8')
    pending.replace(attempt / 'fidelity.json')
    encoded.unlink(missing_ok=True)
    return report


def summary(report):
    return dict(verdict=report['verdict'], calibrated=report['calibrated'], frames=report['frames'],
                passing_frames=report['passing_frames'], timing=report['timing'], metrics=report['metrics'],
                worst_frames=report['worst_frames'][:5])
