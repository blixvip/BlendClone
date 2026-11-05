"""Account for every reference frame; machine analysis is not visual review.

``audit(video, folder, cancel)`` returns the durable manifest and contact-sheet
paths. All timing refers to the supplied video (usually the prepared clip), not
an original upload that may have been trimmed or converted to constant FPS.
"""
import hashlib
import io
import json
import math
import re
import time
from dataclasses import asdict, dataclass
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw

from .media import FORMATS, MAX_BYTES
from .process import Cancelled, run

VERSION = 1


@dataclass(frozen=True)
class AuditConfig:
    chunk_seconds: float = 1.0
    frames_per_sheet: int = 30
    columns: int = 6
    tile_edge: int = 320
    analysis_edge: int = 160
    cut_threshold: float = 45.0
    jpeg_quality: int = 85
    max_frames: int = 14400
    max_duration: float = 61.0
    max_sheet_bytes: int = 128 * 1024 * 1024

    def __post_init__(self):
        integer_limits = {'frames_per_sheet': (1, 60), 'columns': (1, 8),
                          'tile_edge': (64, 512), 'analysis_edge': (32, 256),
                          'jpeg_quality': (40, 95), 'max_frames': (1, 14400),
                          'max_sheet_bytes': (1, 256 * 1024 * 1024)}
        for field, (low, high) in integer_limits.items():
            value = getattr(self, field)
            if type(value) is not int or not low <= value <= high:
                raise ValueError(f'Invalid reference audit {field}.')
        if (not math.isfinite(self.chunk_seconds) or not .1 <= self.chunk_seconds <= 10
                or not math.isfinite(self.max_duration) or not .25 <= self.max_duration <= 61
                or not math.isfinite(self.cut_threshold) or not 0 < self.cut_threshold <= 255):
            raise ValueError('Invalid reference audit timing or change threshold.')
        if (self.columns * self.tile_edge > 2048
                or math.ceil(self.frames_per_sheet / self.columns) * (self.tile_edge + 24) > 2048):
            raise ValueError('Reference contact sheets must fit within 2048 pixels.')


def _check(cancel):
    if cancel is not None and cancel.is_set():
        raise Cancelled('Reference audit cancelled.')


def _digest(path, cancel):
    result = hashlib.sha256()
    with path.open('rb') as source:
        while block := source.read(1024 * 1024):
            _check(cancel)
            result.update(block)
    return result.hexdigest()


def _save(path, manifest):
    pending = path.with_suffix('.json.tmp')
    pending.write_text(json.dumps(manifest, indent=2, allow_nan=False), encoding='utf-8')
    pending.replace(path)


def _cached(path, source, config, cancel):
    try:
        manifest = json.loads(path.read_text(encoding='utf-8'))
        if (manifest['version'] != VERSION or manifest['source'] != source
                or manifest['config'] != asdict(config) or manifest['status'] != 'complete'
                or not manifest['coverage']['complete']):
            return None
        frames = manifest['frames']
        count = manifest['frame_count']
        if (not 0 < count <= config.max_frames or len(frames) != count
                or [item['frame'] for item in frames] != list(range(count))
                or any(manifest['coverage'][key] != count
                       for key in ('expected_frames', 'decoded_frames', 'sheet_frames'))):
            return None
        covered = 0
        total_bytes = 0
        paths = []
        for index, sheet in enumerate(manifest['sheets']):
            _check(cancel)
            if (not re.fullmatch(r'sheet-\d{4,5}\.jpg', sheet['file'])
                    or sheet['first_frame'] != covered
                    or sheet['last_frame'] != covered + sheet['frame_count'] - 1
                    or not 1 <= sheet['frame_count'] <= config.frames_per_sheet
                    or any(frame['sheet'] != index for frame in frames[covered:sheet['last_frame'] + 1])):
                return None
            image_path = path.parent / sheet['file']
            total_bytes += image_path.stat().st_size
            if total_bytes > config.max_sheet_bytes or _digest(image_path, cancel) != sheet['sha256']:
                return None
            with Image.open(image_path) as image:
                if image.size != (sheet['width'], sheet['height']) or max(image.size) > 2048:
                    return None
                image.verify()
            covered += sheet['frame_count']
            paths.append(image_path)
        return (manifest, paths) if covered == count else None
    except (OSError, ValueError, KeyError, TypeError, IndexError, Image.DecompressionBombError):
        return None


def _timings(video, config, cancel):
    # Reading presentation timestamps avoids synthesizing a CFR timeline for VFR media.
    header = json.loads(run(['ffprobe', '-v', 'error', '-protocol_whitelist', 'file,pipe',
        '-format_whitelist', FORMATS, '-select_streams', 'v:0', '-show_streams', '-show_format',
        '-of', 'json', video], timeout=30, cancel=cancel))
    try:
        stream = header['streams'][0]
        width, height = int(stream['width']), int(stream['height'])
        if min(width, height) < 2 or max(width, height) > 8192:
            raise ValueError('Reference video dimensions must be between 2 and 8192 pixels.')
        duration = float(stream.get('duration') or header['format']['duration'])
        if not math.isfinite(duration) or duration <= 0:
            raise ValueError('Reference audit requires a finite video duration.')
        if duration > config.max_duration:
            raise ValueError('Reference audit duration limit exceeded. Select a shorter clip.')
        frame_count = str(stream.get('nb_frames', ''))
        if frame_count.isdigit() and int(frame_count) > config.max_frames:
            raise ValueError('Reference audit frame limit exceeded. Select a shorter clip.')
    except (KeyError, IndexError, TypeError) as error:
        raise ValueError('Could not read the reference video duration.') from error
    data = json.loads(run(['ffprobe', '-v', 'error', '-protocol_whitelist', 'file,pipe',
        '-format_whitelist', FORMATS, '-select_streams', 'v:0', '-show_frames',
        '-show_entries', 'frame=best_effort_timestamp_time,pkt_duration_time:stream=width,height,avg_frame_rate:format=duration',
        '-of', 'json', video], timeout=120, cancel=cancel))
    frames = data.get('frames', [])
    if not frames:
        raise ValueError('Reference audit found no decodable video frames.')
    if len(frames) > config.max_frames:
        raise ValueError('Reference audit frame limit exceeded. Select a shorter clip.')
    try:
        stream = data['streams'][0]
        width, height = int(stream['width']), int(stream['height'])
        if min(width, height) < 2 or max(width, height) > 8192:
            raise ValueError('Reference video dimensions must be between 2 and 8192 pixels.')
        times = [float(frame['best_effort_timestamp_time']) for frame in frames]
        if any(not math.isfinite(t) for t in times) or any(b <= a for a, b in zip(times, times[1:])):
            raise ValueError('Reference frames require finite, increasing presentation timestamps.')
        durations = [b - a for a, b in zip(times, times[1:])]
        fallback = durations[-1] if durations else 1 / 24
        try:
            numerator, denominator = stream.get('avg_frame_rate', '0/0').split('/')
            fps = float(numerator) / float(denominator)
            if math.isfinite(fps) and fps > 0:
                fallback = 1 / fps
        except (ValueError, ZeroDivisionError):
            pass
        last_duration = float(frames[-1].get('pkt_duration_time', fallback))
        durations.append(last_duration if math.isfinite(last_duration) and last_duration > 0 else fallback)
        duration = times[-1] - times[0] + durations[-1]
        if duration > config.max_duration:
            raise ValueError('Reference audit duration limit exceeded. Select a shorter clip.')
        return times, durations, width, height, duration
    except (KeyError, TypeError, ZeroDivisionError) as error:
        raise ValueError('Could not read reliable presentation timestamps for every reference frame.') from error


def audit(video, folder, cancel=None, *, config=None, on_progress=None):
    """Decode all input frames sequentially, returning ``(manifest, sheet_paths)``.

    Contact sheets are split at second boundaries, strong changes, or tile limits.
    ``on_progress(decoded, total)`` may update a job or signal cancellation.
    Interrupted/failed audits persist partial coverage and are never cache hits.
    Only this module's own named sheet files are replaced or removed.
    """
    config = config or AuditConfig()
    video = Path(video).resolve()
    output = Path(folder).resolve() / 'frame-audit'
    manifest_path = output / 'manifest.json'
    started = time.monotonic()
    _check(cancel)
    stat = video.stat()
    if stat.st_size > MAX_BYTES:
        raise ValueError('Reference video exceeds 250 MB.')
    source = {'path': str(video), 'bytes': stat.st_size, 'mtime_ns': stat.st_mtime_ns,
              'sha256': _digest(video, cancel)}
    cached = _cached(manifest_path, source, config, cancel)
    if cached:
        if on_progress:
            on_progress(cached[0]['frame_count'], cached[0]['frame_count'])
        _check(cancel)
        return cached
    output.mkdir(parents=True, exist_ok=True)
    # Filenames and containment are verified; no recursive cleanup or process enumeration.
    for stale in output.glob('sheet-*.jpg'):
        if re.fullmatch(r'sheet-\d{4,5}\.jpg', stale.name) and stale.resolve().parent == output:
            stale.unlink()
    manifest = {'version': VERSION, 'status': 'running', 'source': source,
        'config': asdict(config), 'timestamp_basis': 'input_video_presentation_timestamps',
        'frame_count': 0, 'duration': 0, 'frames': [], 'sheets': [], 'strong_changes': [],
        'coverage': {'expected_frames': 0, 'decoded_frames': 0, 'sheet_frames': 0,
            'complete': False, 'visually_reviewed_frames': 0, 'visual_review_status': 'pending'},
        'elapsed_seconds': 0,
        'limitations': ['Machine frame analysis and contact-sheet coverage do not establish visual review or reconstruction fidelity.',
            'Timestamps describe the supplied reference clip; preparation may have trimmed or normalized the original upload.']}
    _save(manifest_path, manifest)
    cap = None
    tiles = []
    sheet_first = 0
    sheet_bytes = 0

    def flush():
        nonlocal sheet_first, sheet_bytes
        if not tiles:
            return
        columns = min(config.columns, len(tiles))
        width, height = tiles[0].size
        sheet = Image.new('RGB', (columns * width, math.ceil(len(tiles) / columns) * height), '#14171a')
        for index, tile in enumerate(tiles):
            sheet.paste(tile, ((index % columns) * width, (index // columns) * height))
        buffer = io.BytesIO()
        sheet.save(buffer, format='JPEG', quality=config.jpeg_quality)
        payload = buffer.getvalue()
        if sheet_bytes + len(payload) > config.max_sheet_bytes:
            raise ValueError('Reference audit storage limit exceeded. Select a shorter clip.')
        name = f"sheet-{len(manifest['sheets']):04d}.jpg"
        (output / name).write_bytes(payload)
        last = manifest['frames'][sheet_first + len(tiles) - 1]
        manifest['sheets'].append({'file': name, 'start': manifest['frames'][sheet_first]['time'],
            'end': round(last['time'] + last['duration'], 6), 'first_frame': sheet_first,
            'last_frame': last['frame'], 'frame_count': len(tiles), 'width': sheet.width,
            'height': sheet.height, 'bytes': len(payload), 'sha256': hashlib.sha256(payload).hexdigest()})
        sheet_bytes += len(payload)
        sheet_first += len(tiles)
        manifest['coverage']['sheet_frames'] = sheet_first
        tiles.clear()
        manifest['elapsed_seconds'] = round(time.monotonic() - started, 3)
        _save(manifest_path, manifest)

    try:
        times, durations, width, height, duration = _timings(video, config, cancel)
        manifest.update(frame_count=len(times), duration=round(duration, 6), width=width, height=height)
        manifest['coverage']['expected_frames'] = len(times)
        scale = min(1, config.tile_edge / max(width, height))
        tile_size = (max(1, round(width * scale)), max(1, round(height * scale)))
        scale = min(1, config.analysis_edge / max(width, height))
        analysis_size = (max(2, round(width * scale)), max(2, round(height * scale)))
        cap = cv2.VideoCapture(str(video))
        if not cap.isOpened():
            raise ValueError('Could not decode the reference video for frame analysis.')
        previous = previous_gray = None
        current_chunk = None
        for index, source_time in enumerate(times):
            _check(cancel)
            ok, frame = cap.read()
            if not ok:
                raise ValueError(f'Reference decode stopped at frame {index} of {len(times)}; coverage is incomplete.')
            small = cv2.resize(frame, analysis_size, interpolation=cv2.INTER_AREA)
            gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
            change = mean = peak = 0.0
            if previous is not None:
                change = float(np.abs(small.astype(np.float32) - previous).mean())
                flow = cv2.calcOpticalFlowFarneback(previous_gray, gray, None, .5, 3, 15, 3, 5, 1.2, 0)
                magnitude = np.linalg.norm(flow, axis=2)
                mean, peak = float(magnitude.mean()), float(np.percentile(magnitude, 95))
            timestamp = round(source_time - times[0], 6)
            chunk = math.floor((timestamp + 1e-6) / config.chunk_seconds)
            if tiles and (chunk != current_chunk or len(tiles) >= config.frames_per_sheet or change >= config.cut_threshold):
                flush()
            current_chunk = chunk
            record = {'frame': index, 'time': timestamp, 'source_time': source_time,
                'duration': round(durations[index], 6), 'mean_pixel_change': round(change, 4),
                'motion_mean': round(mean, 4), 'motion_p95': round(peak, 4),
                'sheet': len(manifest['sheets'])}
            manifest['frames'].append(record)
            image = Image.fromarray(cv2.cvtColor(cv2.resize(frame, tile_size, interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2RGB))
            tile = Image.new('RGB', (max(140, image.width), image.height + 24), '#14171a')
            tile.paste(image, ((tile.width - image.width) // 2, 24))
            ImageDraw.Draw(tile).text((4, 5), f'{index:05d}  {timestamp:.3f}s', fill='white')
            tiles.append(tile)
            previous, previous_gray = small.astype(np.float32), gray
            manifest['coverage']['decoded_frames'] = index + 1
            if on_progress:
                on_progress(index + 1, len(times))
        _check(cancel)
        if cap.read()[0]:
            raise ValueError('Reference decoder returned extra frames; timestamp coverage is incomplete.')
        flush()
        _check(cancel)
        if video.stat().st_size != source['bytes'] or video.stat().st_mtime_ns != source['mtime_ns']:
            raise ValueError('Reference changed during frame analysis. Retry with a stable video.')
        manifest['strong_changes'] = sorted(manifest['frames'][1:], key=lambda frame: frame['mean_pixel_change'], reverse=True)[:30]
        manifest['coverage']['complete'] = True
        manifest['status'] = 'complete'
    except Exception as error:
        manifest['status'] = 'cancelled' if isinstance(error, Cancelled) else 'failed'
        manifest['error'] = str(error)[:1000]
        raise
    finally:
        if cap is not None:
            cap.release()
        manifest['elapsed_seconds'] = round(time.monotonic() - started, 3)
        _save(manifest_path, manifest)
    return manifest, [output / sheet['file'] for sheet in manifest['sheets']]
