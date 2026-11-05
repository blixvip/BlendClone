import pytest
from app.benchmark import validate_segments


def test_segments_cover_every_frame_exactly_once():
    segments = [dict(first=0,end=5),dict(first=5,end=10)]
    assert validate_segments(segments,10) == segments


@pytest.mark.parametrize('segments', [
    [dict(first=0,end=4),dict(first=5,end=10)],
    [dict(first=0,end=6),dict(first=5,end=10)],
    [dict(first=0,end=9)],
    [dict(first=0,end=0),dict(first=0,end=10)],
])
def test_invalid_coverage_cannot_be_accepted(segments):
    with pytest.raises(ValueError):
        validate_segments(segments,10)
