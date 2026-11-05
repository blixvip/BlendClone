import threading

import pytest

from app import ai


def fixture(tmp_path, count=5):
    sheets = []
    paths = []
    for i in range(count):
        path = tmp_path / f'sheet-{i}.jpg'
        path.write_bytes(f'image {i}'.encode())
        paths.append(path)
        sheets.append(dict(file=path.name, start=float(i), end=float(i + 1), frame_count=24))
    return dict(frame_count=count * 24, sheets=sheets), paths


def response(start, end):
    return dict(summary='A ball descends onto a plinth.', events=[dict(start=start, end=end,
        action='Ball moves down', camera='Locked', transition='Continuous motion',
        caption='', visual_details='Coral sphere, grey plinth, dark background')], limitations=[])


def test_every_sheet_observed_and_unchanged_batches_cached(tmp_path, monkeypatch):
    manifest, paths = fixture(tmp_path)
    calls = []
    def request(folder, tag, prompt, schema, images, cancel):
        calls.append(images)
        return response(0, 4) if len(images) == 4 else response(4, 5)
    monkeypatch.setattr(ai, 'request_json', request)
    progress = []
    result = ai.observe(tmp_path, {'duration': 5, 'fps': 24}, manifest, paths, threading.Event(),
                        on_progress=lambda done, total: progress.append((done, total)))
    assert len(result) == 2
    assert [p for batch in calls for p in batch] == paths
    assert progress[-1] == (2, 2)
    ai.observe(tmp_path, {'duration': 5, 'fps': 24}, manifest, paths, threading.Event())
    assert len(calls) == 2
    paths[-1].write_bytes(b'changed image')
    ai.observe(tmp_path, {'duration': 5, 'fps': 24}, manifest, paths, threading.Event())
    assert len(calls) == 3


def test_observation_rejects_events_outside_visible_sequence(tmp_path, monkeypatch):
    manifest, paths = fixture(tmp_path, 1)
    monkeypatch.setattr(ai, 'request_json', lambda *args: response(0, 2))
    with pytest.raises(ValueError, match='outside'):
        ai.observe(tmp_path, {'duration': 1, 'fps': 24}, manifest, paths, threading.Event())
    assert not list((tmp_path / 'observations').glob('*.cache.json'))


def test_cancelled_observation_makes_no_model_call(tmp_path, monkeypatch):
    from app.process import Cancelled
    manifest, paths = fixture(tmp_path, 1)
    monkeypatch.setattr(ai, 'request_json', lambda *_: pytest.fail('Must not call model'))
    cancel = threading.Event()
    cancel.set()
    with pytest.raises(Cancelled):
        ai.observe(tmp_path, {'duration': 1, 'fps': 24}, manifest, paths, cancel)
