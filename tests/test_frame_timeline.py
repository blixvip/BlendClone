"""Frame tracks preserve source timing independently of legacy second keys."""
from fractions import Fraction

import pytest
from pydantic import ValidationError

from app import models


def timeline_plan_data():
    data = models.fixture_plan().model_dump()
    data['timeline'] = {'frame_count': 910, 'fps_num': 30000, 'fps_den': 1001}
    data['shots'][0]['end'] = float(Fraction(910 * 1001, 30000))
    for obj in data['shots'][0]['objects']:
        obj['keys'] = []
    return data


def key(frame, property='location'):
    return {'frame': frame, 'property': property, 'value': [0, 0, 1]}


def track(data, owner):
    shot = data['shots'][0]
    if owner == 'object':
        return shot['objects'][0].setdefault('frame_keys', [])
    return shot['camera'].setdefault(owner, [])


def test_reference_timeline_round_trips_integer_rate_and_all_910_frames():
    data = timeline_plan_data()
    data['shots'][0]['objects'][0]['frame_keys'] = [key(frame) for frame in range(910)]
    plan = models.Plan.model_validate(data)
    restored = models.Plan.model_validate_json(plan.model_dump_json())

    assert restored.timeline.frame_count == 910
    assert restored.timeline.source_start_frame == 0
    assert (restored.timeline.fps_num, restored.timeline.fps_den) == (30000, 1001)
    assert [k.frame for k in restored.shots[0].objects[0].frame_keys] == list(range(910))
    assert all(k.interpolation == 'LINEAR' for k in restored.shots[0].objects[0].frame_keys)
    models.validate_timing(restored, float(Fraction(910 * 1001, 30000)))


def test_pilot_can_retain_source_offset_with_local_integer_frames():
    data = timeline_plan_data()
    data['timeline'].update(frame_count=30, source_start_frame=420)
    data['shots'][0]['end'] = 1.001
    data['shots'][0]['camera']['frame_keys'] = [key(0), key(29)]
    data['shots'][0]['camera']['target_frame_keys'] = [key(0), key(29)]
    plan = models.Plan.model_validate(data)
    assert plan.timeline.source_start_frame == 420
    models.validate_timing(plan, 1.001)


@pytest.mark.parametrize('field,value', [
    ('fps_num', 0), ('fps_num', 240001), ('fps_num', 30000.5),
    ('fps_den', 0), ('fps_den', 10001), ('fps_den', 1001.5),
    ('frame_count', 0), ('frame_count', 14401), ('frame_count', 910.5),
    ('source_start_frame', -1), ('source_start_frame', 10000001),
])
def test_timeline_rejects_invalid_integer_bounds(field, value):
    data = {'frame_count': 910, 'fps_num': 30000, 'fps_den': 1001}
    data[field] = value
    with pytest.raises(ValidationError):
        models.Timeline.model_validate(data)


@pytest.mark.parametrize('fps_num,fps_den', [(1, 2), (241, 1)])
def test_timeline_rejects_actual_rate_outside_one_to_240(fps_num, fps_den):
    with pytest.raises(ValidationError):
        models.Timeline(frame_count=30, fps_num=fps_num, fps_den=fps_den)


@pytest.mark.parametrize('owner', ['object', 'frame_keys', 'target_frame_keys'])
def test_frame_track_requires_timeline(owner):
    data = timeline_plan_data()
    del data['timeline']
    track(data, owner).append(key(0))
    with pytest.raises(ValidationError, match='timeline'):
        models.Plan.model_validate(data)


@pytest.mark.parametrize('owner', ['object', 'frame_keys', 'target_frame_keys'])
def test_frame_track_rejects_first_frame_beyond_timeline(owner):
    data = timeline_plan_data()
    track(data, owner).append(key(910))
    with pytest.raises(ValidationError, match='frame|timeline'):
        models.Plan.model_validate(data)


@pytest.mark.parametrize('owner', ['object', 'frame_keys', 'target_frame_keys'])
def test_frame_track_rejects_duplicate_frame_property(owner):
    data = timeline_plan_data()
    track(data, owner).extend([key(420), key(420)])
    with pytest.raises(ValidationError, match='duplicate'):
        models.Plan.model_validate(data)


def test_multiple_properties_at_same_frame_and_separate_tracks_are_allowed():
    data = timeline_plan_data()
    track(data, 'object').extend([key(420), key(420, 'rotation'), key(420, 'scale')])
    track(data, 'frame_keys').append(key(420))
    track(data, 'target_frame_keys').append(key(420))
    plan = models.Plan.model_validate(data)
    assert len(plan.shots[0].objects[0].frame_keys) == 3


@pytest.mark.parametrize('frame', [-1, 1.5])
def test_frame_key_rejects_negative_and_fractional_frames(frame):
    with pytest.raises(ValidationError):
        models.FrameKey.model_validate(key(frame))


@pytest.mark.parametrize('error', [-0.001, 0.001, 0.000002])
def test_rational_timeline_duration_rejects_legacy_tolerance(error):
    plan = models.Plan.model_validate(timeline_plan_data())
    duration = float(Fraction(910 * 1001, 30000))
    with pytest.raises(ValueError, match='timeline|duration'):
        models.validate_timing(plan, duration + error)


def test_rational_timeline_duration_accepts_submicrosecond_conversion_noise():
    plan = models.Plan.model_validate(timeline_plan_data())
    models.validate_timing(plan, float(Fraction(910 * 1001, 30000)) + 0.0000005)


def test_legacy_seconds_plan_still_loads_without_timeline():
    plan = models.fixture_plan()
    assert plan.timeline is None
    assert plan.shots[0].objects[0].frame_keys == []
    assert plan.shots[0].camera.frame_keys == []
    assert plan.shots[0].camera.target_frame_keys == []
    models.validate_timing(plan, 2.0)


@pytest.mark.parametrize('owner,legacy_name', [
    ('object', 'keys'), ('frame_keys', 'keys'), ('target_frame_keys', 'target_keys'),
])
def test_track_cannot_mix_second_and_frame_keys(owner, legacy_name):
    data = timeline_plan_data()
    track(data, owner).append(key(0))
    target = data['shots'][0]['objects'][0] if owner == 'object' else data['shots'][0]['camera']
    target[legacy_name] = [{'t': 0, 'property': 'location', 'value': [0, 0, 1]}]
    with pytest.raises(ValidationError, match='either seconds or frame'):
        models.Plan.model_validate(data)


def test_camera_target_frame_track_requires_location_property():
    data = timeline_plan_data()
    track(data, 'target_frame_keys').append(key(0, 'rotation'))
    with pytest.raises(ValidationError, match='target.*location'):
        models.Plan.model_validate(data)


def sampled_mesh_data():
    data = timeline_plan_data()
    obj = data['shots'][0]['objects'][0]
    vertices = [[0, 0, 0], [1, 0, 0], [0, 1, 0]]
    obj.update(kind='mesh', vertices=vertices, faces=[[0, 1, 2]], mesh_samples=[
        {'frame': 0, 'vertices': vertices},
        {'frame': 909, 'vertices': [[0, 0, 1], [1, 0, 1], [0, 1, 1]]},
    ])
    return data


def test_mesh_samples_preserve_topology_and_frame_indices():
    plan = models.Plan.model_validate(sampled_mesh_data())
    restored = models.Plan.model_validate_json(plan.model_dump_json())
    obj = restored.shots[0].objects[0]
    assert obj.faces == [[0, 1, 2]]
    assert [s.frame for s in obj.mesh_samples] == [0, 909]
    assert obj.mesh_samples[-1].vertices == [(0, 0, 1), (1, 0, 1), (0, 1, 1)]


@pytest.mark.parametrize('invalid_frame', [0, 910])
def test_mesh_samples_reject_duplicate_or_out_of_range_frames(invalid_frame):
    data = sampled_mesh_data()
    data['shots'][0]['objects'][0]['mesh_samples'][-1]['frame'] = invalid_frame
    with pytest.raises(ValidationError, match='mesh sample'):
        models.Plan.model_validate(data)


def test_mesh_samples_require_timeline():
    data = sampled_mesh_data()
    del data['timeline']
    with pytest.raises(ValidationError, match='timeline'):
        models.Plan.model_validate(data)


def test_mesh_samples_reject_changed_vertex_count():
    data = sampled_mesh_data()
    data['shots'][0]['objects'][0]['mesh_samples'][-1]['vertices'].pop()
    with pytest.raises(ValidationError, match='vertex count'):
        models.Plan.model_validate(data)
