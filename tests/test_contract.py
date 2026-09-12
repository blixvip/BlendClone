import copy
import pytest
from app.models import Plan, fixture_plan, validate_timing
from app.store import Store


def test_plan_preserves_actual_shot_timing():
    plan = fixture_plan()
    validate_timing(plan, 2.0)
    assert plan.shots[0].end == 2.0


def test_rejects_animation_beyond_shot():
    data = fixture_plan().model_dump()
    data['shots'][0]['objects'][0]['keys'][0]['t'] = 10
    with pytest.raises(ValueError, match='keyframe'):
        validate_timing(Plan.model_validate(data), 2.0)


def test_rejects_broken_mesh_faces():
    data = fixture_plan().model_dump()
    obj = data['shots'][0]['objects'][0]
    obj.update(kind='mesh', vertices=[[0, 0, 0]], faces=[[0, 1, 2]])
    with pytest.raises(ValueError, match='face'):
        Plan.model_validate(data)


def test_rejects_parent_cycle():
    data = fixture_plan().model_dump()
    obj = data['shots'][0]['objects'][0]
    obj['parent'] = obj['id']
    with pytest.raises(ValueError, match='parent'):
        Plan.model_validate(data)


def test_rejects_uncovered_time():
    data = fixture_plan().model_dump()
    data['shots'][0]['start'] = .5
    with pytest.raises(ValueError, match='cover'):
        validate_timing(Plan.model_validate(data), 2.0)


def test_rejects_nonfinite_geometry():
    data = fixture_plan().model_dump()
    data['shots'][0]['objects'][0]['location'] = [float('nan'), 0, 0]
    with pytest.raises(ValueError):
        Plan.model_validate(data)


def test_store_persists_jobs_and_rejects_path_escape(tmp_path):
    store = Store(tmp_path)
    job = store.create({'title': 'Test'})
    store.update(job['id'], status='failed', message='Interrupted')
    assert Store(tmp_path).get(job['id'])['status'] == 'failed'
    with pytest.raises(ValueError):
        store.get('../outside')


def test_stale_job_is_recoverable_after_restart(tmp_path):
    store = Store(tmp_path)
    job = store.create({'title': 'Test'})
    store.update(job['id'], status='running')
    Store(tmp_path).recover()
    assert store.get(job['id'])['status'] == 'interrupted'
