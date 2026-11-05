"""Immutable-source benchmark manifests and contiguous frame partitions."""
import hashlib
import json
from fractions import Fraction
from pathlib import Path

from .process import run


def validate_segments(segments, frame_count):
    cursor = 0
    for segment in segments:
        if segment['first'] != cursor or segment['end'] <= cursor:
            raise ValueError('Segments must cover consecutive frames without gaps or overlaps')
        cursor = segment['end']
    if cursor != frame_count:
        raise ValueError('Segments must cover every source frame')
    return segments


def source_manifest(source, segments):
    data = json.loads(run(['ffprobe','-v','error','-select_streams','v:0','-show_streams','-show_frames',
        '-show_entries','stream=width,height,r_frame_rate,color_range,color_space:frame=best_effort_timestamp_time',
        '-of','json',source],timeout=300))
    stream, frames = data['streams'][0],data['frames']
    rate = Fraction(stream['r_frame_rate'])
    digest = hashlib.sha256()
    with Path(source).open('rb') as handle:
        while chunk := handle.read(1024*1024):digest.update(chunk)
    return dict(source_sha256=digest.hexdigest(),source_name=Path(source).name,
        width=stream['width'],height=stream['height'],fps_num=rate.numerator,fps_den=rate.denominator,
        frame_count=len(frames),color_range=stream.get('color_range'),color_space=stream.get('color_space'),
        frames=[dict(frame=index,pts=float(record['best_effort_timestamp_time'])) for index,record in enumerate(frames)],
        segments=validate_segments(segments,len(frames)))
