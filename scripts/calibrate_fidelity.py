"""Set fidelity gates just above the noise floor of changes a viewer cannot see.

Uses the self-test outputs (run scripts/fidelity_selftest.py first):
  invisible: identical re-render, re-encode at 80% bitrate, +1% brightness, 0.5 px blur
  visible:   ball moved, ball recolored, bounce 3 frames late (each must still fail)
Writes app/fidelity_gates.json only when every visible change fails under the new gates.
Usage: .venv/Scripts/python.exe scripts/calibrate_fidelity.py
"""
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import fidelity  # noqa: E402
from app.process import run  # noqa: E402

OUT = ROOT / 'outputs' / 'fidelity-selftest'
MARGIN = 1.25
OPEN = dict(calibrated=False, gates=dict(coarse_ssim_min=-1, delta_e_max=1e9, flow_epe_max=1e9, timing_lag_max=99))


def encoded(name):
    config = json.loads((OUT / name / 'animation.config.json').read_text(encoding='utf-8'))
    target = OUT / f'{name}-encoded.mp4'
    fidelity.encode_like(OUT / name / 'frames' / 'frame-%04d.png', config['fps'] / config.get('fps_base', 1),
                         fidelity.probe(OUT / 'reference.mp4'), target)
    return target


def perturb(reference, name, *args):
    target = OUT / f'invisible-{name}.mp4'
    run(['ffmpeg', '-y', '-v', 'error', '-i', reference, *args, '-c:v', 'libx264', '-pix_fmt', 'yuv420p',
         '-colorspace', 'bt709', '-color_range', 'tv', target], timeout=300)
    return target


def worst(report):
    frames = report['per_frame']
    flows = [f['flow_epe'] for f in frames if f['flow_epe'] is not None]
    return dict(coarse_ssim=min(f['coarse_ssim'] for f in frames), delta_e=max(f['delta_e'] for f in frames),
                flow_epe=max(flows), lag=abs(report['timing']['lag_frames']))


def main():
    reference = OUT / 'reference.mp4'
    bitrate = fidelity.probe(reference)['bitrate']
    invisible = {
        'identical re-render': encoded('same'),
        're-encode 80% bitrate': perturb(reference, 'bitrate', '-b:v', str(int(bitrate * .8))),
        '+1% brightness': perturb(reference, 'brightness', '-vf', 'eq=brightness=0.01', '-crf', '18'),
        '0.5 px blur': perturb(reference, 'blur', '-vf', 'gblur=sigma=0.5', '-crf', '18'),
    }
    floors = {name: worst(fidelity.compare(reference, video, gates=OPEN)) for name, video in invisible.items()}
    for name, value in floors.items():
        print('invisible', name, value)
    gates = dict(
        coarse_ssim_min=round(1 - (1 - min(v['coarse_ssim'] for v in floors.values())) * MARGIN, 4),
        delta_e_max=round(max(v['delta_e'] for v in floors.values()) * MARGIN, 3),
        flow_epe_max=round(max(v['flow_epe'] for v in floors.values()) * MARGIN, 3),
        timing_lag_max=max(v['lag'] for v in floors.values()),
    )
    candidate = dict(calibrated=True, gates=gates)
    checks = {}
    for name in ('same', 'moved', 'recolored', 'late'):
        report = fidelity.compare(reference, encoded(name), gates=candidate)
        checks[name] = dict(verdict=report['verdict'], passing=f"{report['passing_frames']}/{report['frames']}",
                            lag=report['timing']['lag_frames'])
        print('check', name, checks[name])
    sensitive = all(checks[k]['verdict'] == 'approximate' for k in ('moved', 'recolored', 'late'))
    stable = checks['same']['verdict'] == 'metrics-pass'
    result = dict(calibrated=True, calibrated_on=str(date.today()),
                  basis='Built-in synthetic ball-drop scene (original content). Floors are content-dependent; recalibrate on a representative owned clip before trusting a pass on very different material.',
                  margin=MARGIN, gates=gates, invisible_floors=floors, checks=checks)
    (OUT / 'calibration.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    if sensitive and stable:
        (ROOT / 'app' / 'fidelity_gates.json').write_text(json.dumps(
            {k: result[k] for k in ('calibrated', 'calibrated_on', 'basis', 'margin', 'gates')}, indent=2) + '\n', encoding='utf-8')
        print('CALIBRATION OK', gates)
        return 0
    print('CALIBRATION REJECTED: gates would pass a visible error or fail an identical rebuild.', gates)
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
