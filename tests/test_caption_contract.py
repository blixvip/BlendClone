import pytest
from app.models import Caption, Plan, Timeline, fixture_plan


def test_captions_are_frame_bounded_and_survive_scene_roundtrip():
    plan=fixture_plan()
    plan.timeline=Timeline(frame_count=60)
    plan.captions=[Caption(text='Visible words',first_frame=5,end_frame=30)]
    loaded=Plan.model_validate_json(plan.model_dump_json())
    assert loaded.captions[0].first_frame==5
    assert loaded.captions[0].end_frame==30


@pytest.mark.parametrize('first,end',[(0,61),(30,30),(40,30)])
def test_captions_cannot_outlive_or_reverse_the_timeline(first,end):
    plan=fixture_plan()
    plan.timeline=Timeline(frame_count=60)
    plan.captions=[Caption(text='Visible words',first_frame=first,end_frame=end)]
    with pytest.raises(ValueError,match='caption'):
        Plan.model_validate(plan.model_dump())
