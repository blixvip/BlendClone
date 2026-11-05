import json
import threading
from pathlib import Path

import pytest

from app import ai
from app.models import fixture_plan
from app.pipeline import Pipeline
from app.store import Store


def prepared_job(tmp_path, **fields):
    store = Store(tmp_path)
    job = store.create(dict(title='Reference', url='', brief='', start=0, duration=2,
                            quality='draft', audio=False, review=False, preview_first=True, **fields))
    folder = store.folder(job['id'])
    (folder / 'source.bin').write_bytes(b'source')
    (folder / 'reference.mp4').write_bytes(b'reference')
    (folder / 'plan.json').write_text(fixture_plan().model_dump_json(), encoding='utf-8')
    return store, job, folder


def fake_media(monkeypatch):
    from app import pipeline
    monkeypatch.setattr(pipeline.media, 'probe', lambda _: dict(duration=2, fps=24, width=320, height=240, audio=False))
    monkeypatch.setattr(pipeline.media, 'timestamps', lambda *_: [0, 1])
    monkeypatch.setattr(pipeline.media, 'sheets', lambda *_, **__: [])
    monkeypatch.setattr(pipeline.reference, 'audit', lambda *_, **__: (
        dict(frame_count=48, sheets=[], frames=[], coverage={'complete': True}), []))
    monkeypatch.setattr(pipeline, 'preview_pairs', lambda *args: [])


def test_preview_does_not_render_final_and_keeps_existing_downloads(tmp_path, monkeypatch):
    from app import pipeline
    fake_media(monkeypatch)
    store, job, folder = prepared_job(tmp_path)
    (folder / 'old.mp4').write_bytes(b'last good')
    store.update(job['id'], artifacts={'video': 'old.mp4'})
    calls = []
    def render(attempt, plan, *args, **kwargs):
        calls.append(kwargs.get('mode', 'preview'))
        (attempt / 'plan.json').write_text(plan.model_dump_json())
        (attempt / 'remake.blend').write_bytes(b'editable')
        return []
    monkeypatch.setattr(pipeline.render, 'render', render)
    worker = Pipeline(store)
    worker.work(job['id'], threading.Event(), False)
    result = store.get(job['id'])
    assert result['status'] == 'preview', result
    assert calls == ['preview']
    assert result['artifacts']['video'] == 'old.mp4'
    assert result['artifacts']['preview_blend'].startswith('runs/')
    assert (folder / result['artifacts']['preview_blend']).is_file()
    worker.shutdown()


def test_failed_final_preserves_last_good_files(tmp_path, monkeypatch):
    from app import pipeline
    fake_media(monkeypatch)
    store, job, folder = prepared_job(tmp_path)
    (folder / 'old.mp4').write_bytes(b'last good')
    store.update(job['id'], status='preview', artifacts={'video': 'old.mp4'}, resume_phase='final')
    attempts = []
    def fail(attempt, *args, **kwargs):
        attempts.append(attempt)
        (attempt / 'remake.mp4').write_bytes(b'incomplete')
        raise ValueError('render failed')
    monkeypatch.setattr(pipeline.render, 'render', fail)
    worker = Pipeline(store)
    worker.work(job['id'], threading.Event(), False, final=True)
    result = store.get(job['id'])
    assert result['status'] == 'failed'
    assert result['artifacts']['video'] == 'old.mp4'
    assert (folder / 'old.mp4').read_bytes() == b'last good'
    assert attempts[0] != folder
    assert result['resume_phase'] == 'final'
    worker.shutdown()


def test_queue_capacity_applies_to_all_submissions(tmp_path):
    store, job, _ = prepared_job(tmp_path)
    worker = Pipeline(store)
    worker.tokens = {f'{i:012x}': threading.Event() for i in range(8)}
    with pytest.raises(ValueError, match='Eight'):
        worker.submit(job['id'])
    assert store.get(job['id'])['message'] == 'Waiting to start'
    worker.shutdown()


def test_final_resumes_saved_plan_without_new_model_calls(tmp_path, monkeypatch):
    from app import pipeline
    fake_media(monkeypatch)
    store, job, folder = prepared_job(tmp_path)
    calls = []
    monkeypatch.setattr(ai, 'generate', lambda *_a, **_k: pytest.fail('Final export must use reviewed plan'))
    def render(attempt, plan, meta, quality, cancel, **kwargs):
        calls.append(kwargs.get('mode', 'preview'))
        for name in ('remake.blend', 'plan.json', 'expanded_plan.json', 'inventory.json'):
            (attempt / name).write_text(plan.model_dump_json())
        (attempt / 'animation.config.json').write_text(json.dumps({'folder': str(attempt)}))
        return []
    def encode(attempt, *args):
        (attempt / 'remake.mp4').write_bytes(b'video')
        (attempt / 'comparison.mp4').write_bytes(b'comparison')
    monkeypatch.setattr(pipeline.render, 'render', render)
    monkeypatch.setattr(pipeline.render, 'encode', encode)
    worker = Pipeline(store)
    worker.work(job['id'], threading.Event(), False, final=True)
    result = store.get(job['id'])
    assert result['status'] == 'completed', result
    assert calls == ['animation']
    assert result['artifacts']['video'].startswith('runs/')
    assert (folder / result['artifacts']['project']).is_file()
    worker.shutdown()
