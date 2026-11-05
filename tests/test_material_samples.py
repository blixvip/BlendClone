import pytest
from app.models import Material, MaterialSample, Plan, Timeline, fixture_plan


def test_material_color_tracks_retain_exact_frames():
    plan=fixture_plan()
    plan.timeline=Timeline(frame_count=60)
    plan.materials[0]=Material(id='coral',color='#ffaa00',unlit=True,
        color_samples=[MaterialSample(frame=0,color='#ffee00'),MaterialSample(frame=59,color='#ccff33')])
    assert Plan.model_validate_json(plan.model_dump_json()).materials[0].color_samples[-1].frame==59


def test_material_tracks_cannot_escape_timeline():
    plan=fixture_plan()
    plan.timeline=Timeline(frame_count=60)
    plan.materials[0].color_samples=[MaterialSample(frame=60,color='#ffffff')]
    with pytest.raises(ValueError,match='material'):
        Plan.model_validate(plan.model_dump())


@pytest.mark.parametrize('frames,timeline', [([0],None),([0,0],Timeline(frame_count=60))])
def test_material_tracks_reject_ambiguous_timing(frames,timeline):
    plan=fixture_plan()
    plan.timeline=timeline
    plan.materials[0].color_samples=[MaterialSample(frame=n,color='#ffffff') for n in frames]
    with pytest.raises(ValueError,match='material'):
        Plan.model_validate(plan.model_dump())


def test_material_track_cannot_be_hidden_by_procedural_input():
    with pytest.raises(ValueError,match='solid'):
        Material(id='animated',color='#ffffff',pattern='noise',color_samples=[MaterialSample(frame=0,color='#ffffff')])
