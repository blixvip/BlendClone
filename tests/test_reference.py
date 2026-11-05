import json
import threading
from dataclasses import replace

import cv2
import numpy as np
import pytest
from PIL import Image

from app.process import Cancelled, run
from app.reference import AuditConfig, audit


def make_video(path, count=12, fps=6, color=210):
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*'mp4v'), fps, (96, 64))
    assert writer.isOpened()
    try:
        for index in range(count):
            frame = np.full((64, 96, 3), color if index >= count // 2 else 10, np.uint8)
            cv2.rectangle(frame, (index * 3, 20), (index * 3 + 15, 40), (80, 130, 220), -1)
            writer.write(frame)
    finally:
        writer.release()
    return path


def test_all_frames_have_timing_metrics_and_sheet_coverage(tmp_path):
    source = make_video(tmp_path / 'source.mp4')
    manifest, sheets = audit(source, tmp_path, threading.Event())

    assert manifest['status'] == 'complete'
    assert manifest['coverage']['expected_frames'] == 12
    assert manifest['coverage']['decoded_frames'] == 12
    assert manifest['coverage']['sheet_frames'] == 12
    assert manifest['coverage']['visually_reviewed_frames'] == 0
    assert manifest['coverage']['visual_review_status'] == 'pending'
    assert [frame['frame'] for frame in manifest['frames']] == list(range(12))
    assert [frame['time'] for frame in manifest['frames']] == pytest.approx([i / 6 for i in range(12)], abs=1e-5)
    assert max(frame['mean_pixel_change'] for frame in manifest['frames']) > 100
    assert max(frame['motion_p95'] for frame in manifest['frames']) > 0
    assert sum(sheet['frame_count'] for sheet in manifest['sheets']) == 12
    assert len(sheets) == 2
    for sheet in sheets:
        with Image.open(sheet) as image:
            assert max(image.size) <= 2048
    assert json.loads((tmp_path / 'frame-audit' / 'manifest.json').read_text()) == manifest


def test_audit_preserves_variable_frame_timestamps(tmp_path):
    source = tmp_path / 'variable.mkv'
    run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'testsrc2=size=96x64:rate=10:duration=1',
         '-vf', "select='eq(n,0)+eq(n,2)+eq(n,5)+eq(n,9)'", '-fps_mode', 'vfr', '-c:v', 'ffv1', source])
    manifest, _ = audit(source, tmp_path, threading.Event())
    assert [frame['source_time'] for frame in manifest['frames']] == pytest.approx([0, .2, .5, .9])
    assert manifest['coverage']['decoded_frames'] == 4


def test_cached_audit_requires_matching_source_config_and_intact_sheets(tmp_path):
    source = make_video(tmp_path / 'source.mp4')
    config = AuditConfig()
    first, sheets = audit(source, tmp_path, threading.Event(), config=config)
    path = tmp_path / 'frame-audit' / 'manifest.json'
    original_mtime = path.stat().st_mtime_ns
    cached, _ = audit(source, tmp_path, threading.Event(), config=config)
    assert cached == first
    assert path.stat().st_mtime_ns == original_mtime

    sheets[0].write_bytes(b'corrupted')
    repaired, repaired_sheets = audit(source, tmp_path, threading.Event(), config=config)
    with Image.open(repaired_sheets[0]) as image:
        image.verify()
    assert repaired['coverage']['decoded_frames'] == 12

    changed, _ = audit(source, tmp_path, threading.Event(), config=replace(config, chunk_seconds=.5))
    assert len(changed['sheets']) == 4
    make_video(source, color=80)
    updated, _ = audit(source, tmp_path, threading.Event(), config=config)
    assert updated['source']['sha256'] != first['source']['sha256']


def test_cancellation_records_partial_coverage_and_retry_finishes(tmp_path):
    source = make_video(tmp_path / 'source.mp4')
    cancel = threading.Event()

    def stop_after_three(done, total):
        assert total == 12
        if done == 3:
            cancel.set()

    with pytest.raises(Cancelled):
        audit(source, tmp_path, cancel, on_progress=stop_after_three)
    partial = json.loads((tmp_path / 'frame-audit' / 'manifest.json').read_text())
    assert partial['status'] == 'cancelled'
    assert partial['coverage']['decoded_frames'] == 3
    assert partial['coverage']['complete'] is False
    cancel.clear()
    complete, _ = audit(source, tmp_path, cancel)
    assert complete['coverage']['complete'] is True
    assert complete['coverage']['decoded_frames'] == 12


def test_audit_refuses_excess_frames_without_claiming_completion(tmp_path):
    source = make_video(tmp_path / 'source.mp4')
    with pytest.raises(ValueError, match='frame limit'):
        audit(source, tmp_path, threading.Event(), config=AuditConfig(max_frames=10))
    manifest_path = tmp_path / 'frame-audit' / 'manifest.json'
    assert not manifest_path.exists() or json.loads(manifest_path.read_text())['status'] != 'complete'


def test_audit_sheet_limit_does_not_silently_skip_frames(tmp_path):
    source = make_video(tmp_path / 'source.mp4')
    with pytest.raises(ValueError, match='storage limit'):
        audit(source, tmp_path, threading.Event(), config=AuditConfig(max_sheet_bytes=100))
    manifest = json.loads((tmp_path / 'frame-audit' / 'manifest.json').read_text())
    assert manifest['status'] == 'failed'
    assert manifest['coverage']['complete'] is False


def test_early_decoder_end_is_reported_as_incomplete(tmp_path, monkeypatch):
    source = make_video(tmp_path / 'source.mp4')
    real_capture = cv2.VideoCapture

    class TruncatedCapture:
        def __init__(self, filename):
            self.capture = real_capture(filename)
            self.read_count = 0

        def isOpened(self):
            return self.capture.isOpened()

        def read(self):
            self.read_count += 1
            return (False, None) if self.read_count > 5 else self.capture.read()

        def release(self):
            self.capture.release()

    monkeypatch.setattr(cv2, 'VideoCapture', TruncatedCapture)
    with pytest.raises(ValueError, match='frame 5 of 12'):
        audit(source, tmp_path, threading.Event())
    manifest = json.loads((tmp_path / 'frame-audit' / 'manifest.json').read_text())
    assert manifest['coverage']['expected_frames'] == 12
    assert manifest['coverage']['decoded_frames'] == 5
    assert manifest['coverage']['complete'] is False
