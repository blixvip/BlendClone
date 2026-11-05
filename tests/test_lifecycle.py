import threading
from pathlib import Path

import pytest

from app import media, render
from app.models import fixture_plan
from app.process import Cancelled


def test_interrupted_normalization_never_replaces_valid_reference(tmp_path, monkeypatch):
    reference = tmp_path / 'reference.mp4'
    reference.write_bytes(b'previous valid reference')
    monkeypatch.setattr(media, 'probe', lambda path: dict(duration=2, fps=24))

    def interrupted(args, **kwargs):
        Path(args[-1]).write_bytes(b'partial encoding')
        raise Cancelled()

    monkeypatch.setattr(media, 'run', interrupted)
    with pytest.raises(Cancelled):
        media.prepare(tmp_path / 'source.bin', tmp_path, 0, 2, threading.Event())
    assert reference.read_bytes() == b'previous valid reference'
    assert list(tmp_path.glob('*.mp4')) == [reference]


def test_failed_normalization_leaves_no_reference_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(media, 'probe', lambda path: dict(duration=2, fps=24))

    def interrupted(args, **kwargs):
        Path(args[-1]).write_bytes(b'partial encoding')
        raise Cancelled()

    monkeypatch.setattr(media, 'run', interrupted)
    with pytest.raises(Cancelled):
        media.prepare(tmp_path / 'source.bin', tmp_path, 0, 2, threading.Event())
    assert not list(tmp_path.glob('*.mp4'))


def test_stale_previews_do_not_make_incomplete_render_succeed(tmp_path, monkeypatch):
    previews = tmp_path / 'previews'
    previews.mkdir()
    (previews / '000.png').write_bytes(b'stale preview')
    (tmp_path / 'remake.blend').write_bytes(b'stale project')
    monkeypatch.setattr(render, 'blender_binary', lambda: 'blender')

    def incomplete(args, **kwargs):
        (tmp_path / 'remake.blend').write_bytes(b'new project')

    monkeypatch.setattr(render, 'run', incomplete)
    with pytest.raises(ValueError, match='preview'):
        render.render(tmp_path, fixture_plan(), dict(duration=2, width=160, height=90, fps=24),
            'draft', threading.Event(), times=[0])


def test_stale_blend_cannot_count_as_new_render_output(tmp_path, monkeypatch):
    (tmp_path / 'remake.blend').write_bytes(b'stale project')
    monkeypatch.setattr(render, 'blender_binary', lambda: 'blender')
    monkeypatch.setattr(render, 'run', lambda *args, **kwargs: None)
    with pytest.raises(ValueError, match='editable project'):
        render.render(tmp_path, fixture_plan(), dict(duration=2, width=160, height=90, fps=24),
            'draft', threading.Event(), times=[])


@pytest.mark.parametrize('size', [(1080, 1920), (1920, 1080), (640, 360), (2160, 3840)])
def test_final_quality_preserves_reference_resolution(size):
    assert render.dimensions(dict(zip(('width', 'height'), size)), 'final') == size


@pytest.mark.parametrize('engine', ['CYCLES', 'BLENDER_EEVEE'])
def test_engine_choice_survives_asset_expansion_and_saved_plan(tmp_path, monkeypatch, engine):
    import json
    from app.models import Object, Plan
    from app.anatomy import expand_assets

    plan = fixture_plan()
    plan.shots[0].objects.append(Object(id='shard', kind='asset', asset='splinter'))
    monkeypatch.setattr(render, 'blender_binary', lambda: 'blender')
    def fake_blender(*args, **kwargs):
        (tmp_path / 'remake.blend').write_bytes(b'project')
    monkeypatch.setattr(render, 'run', fake_blender)
    meta = dict(duration=2, width=160, height=90, fps=24)
    render.render(tmp_path, plan, meta, 'draft', threading.Event(), engine=engine)
    saved = Plan.model_validate_json((tmp_path / 'plan.json').read_text(encoding='utf-8'))
    render.render(tmp_path, expand_assets(saved), meta, 'final', threading.Event())
    assert json.loads((tmp_path / 'preview.config.json').read_text())['engine'] == engine
    assert saved.engine == engine
