"""Measured scene revisions preserve recovered geometry and use bounded patches."""
import copy
import json
import threading

import pytest

from app import ai
from app.models import Plan, fixture_plan


def measured_plan(*, legacy=False):
    data = fixture_plan().model_dump()
    data['timeline'] = dict(frame_count=30, fps_num=30000, fps_den=1001)
    data['shots'][0]['end'] = 1.001
    for obj in data['shots'][0]['objects']:
        obj['keys'] = []
    ball = data['shots'][0]['objects'][0]
    vertices = [[0.123456, 0, 0], [1, 0, 0], [0, 1, 0]]
    ball.update(kind='mesh', vertices=vertices, faces=[[0, 1, 2]], mesh_samples=[
        dict(frame=0, vertices=vertices),
        dict(frame=29, vertices=[[0.123456, 0, 1], [1, 0, 1], [0, 1, 1]]),
    ])
    locations = [[0, 0, 2], [2, 0, 1]]
    if legacy:
        ball['keys'] = [dict(t=t, property='location', value=value) for t, value in zip([0, 1], locations)]
    else:
        ball['frame_keys'] = [dict(frame=f, property='location', value=value) for f, value in zip([0, 29], locations)]
    return Plan.model_validate(data)


def patch():
    return dict(materials=[], adjustments=[], lights=[], limitations=[])


def request_patch(monkeypatch, response):
    calls = []

    def request(folder, tag, prompt, schema, images, cancel):
        calls.append(dict(prompt=prompt, schema=schema))
        return copy.deepcopy(response)

    monkeypatch.setattr(ai, 'request_json', request)
    return calls


def revise(tmp_path, previous):
    return ai.generate(tmp_path, dict(duration=1.001, fps=30000 / 1001, width=1080, height=1920),
                       [], 'Improve the material match.', threading.Event(), previous=previous, review=True)


def test_measured_revision_sends_compact_inventory_and_patch_schema(tmp_path, monkeypatch):
    previous = measured_plan()
    calls = request_patch(monkeypatch, patch())
    revise(tmp_path, previous)
    assert len(calls) == 1
    prompt = calls[0]['prompt']
    assert 'CURRENT PLAN:' not in prompt
    assert 'mesh_samples' not in prompt
    assert '0.123456' not in prompt
    assert '30' in prompt and 'frame' in prompt.lower()
    schema = calls[0]['schema']
    assert set(schema['properties']) == {'materials', 'adjustments', 'lights', 'limitations'}
    assert 'mesh_samples' not in json.dumps(schema)


def test_material_patch_preserves_measured_geometry_tracks_and_previous_plan(tmp_path, monkeypatch):
    previous = measured_plan()
    snapshot = previous.model_dump()
    material = previous.materials[0].model_dump()
    material['color'] = '#123456'
    request_patch(monkeypatch, dict(materials=[material], adjustments=[], lights=[], limitations=[]))
    revised = revise(tmp_path, previous)
    assert revised.materials[0].color == '#123456'
    assert previous.model_dump() == snapshot
    assert revised is not previous
    assert revised.timeline == previous.timeline
    assert revised.shots[0].objects == previous.shots[0].objects
    assert revised.shots[0].objects[0] is not previous.shots[0].objects[0]


@pytest.mark.parametrize('legacy', [False, True])
def test_translation_updates_base_and_location_track_without_touching_mesh(tmp_path, monkeypatch, legacy):
    previous = measured_plan(legacy=legacy)
    snapshot = previous.model_dump()
    adjustment = dict(shot=0, object_id='ball', translation=[1, 0, 0], scale_multiplier=[1, 1, 1])
    request_patch(monkeypatch, dict(materials=[], adjustments=[adjustment], lights=[], limitations=[]))
    revised = revise(tmp_path, previous)
    before, after = previous.shots[0].objects[0], revised.shots[0].objects[0]
    assert after.location == (before.location[0] + 1, before.location[1], before.location[2])
    before_keys = before.keys if legacy else before.frame_keys
    after_keys = after.keys if legacy else after.frame_keys
    assert [k.value for k in after_keys] == [(k.value[0] + 1, k.value[1], k.value[2]) for k in before_keys]
    assert after.vertices == before.vertices
    assert after.mesh_samples == before.mesh_samples
    assert after.scale == before.scale
    assert previous.model_dump() == snapshot


def test_light_patch_updates_only_addressed_light(tmp_path, monkeypatch):
    previous = measured_plan()
    light = previous.shots[0].lights[0].model_dump()
    light['energy'] = 700
    request_patch(monkeypatch, dict(materials=[], adjustments=[], lights=[dict(shot=0, index=0, light=light)], limitations=[]))
    revised = revise(tmp_path, previous)
    assert revised.shots[0].lights[0].energy == 700
    assert revised.shots[0].lights[1:] == previous.shots[0].lights[1:]
    assert previous.shots[0].lights[0].energy == 1200


@pytest.mark.parametrize('unknown', ['material', 'object'])
def test_patch_rejects_unknown_target_without_mutating_previous(tmp_path, monkeypatch, unknown):
    previous = measured_plan()
    snapshot = previous.model_dump()
    response = patch()
    if unknown == 'material':
        material = previous.materials[0].model_dump()
        material['id'] = 'missing_material'
        response['materials'] = [material]
    else:
        response['adjustments'] = [dict(shot=0, object_id='missing_object', translation=[1, 0, 0], scale_multiplier=[1, 1, 1])]
    request_patch(monkeypatch, response)
    with pytest.raises(ValueError, match=f'(?i)(unknown.*{unknown}|{unknown}.*unknown|missing_{unknown})'):
        revise(tmp_path, previous)
    assert previous.model_dump() == snapshot
