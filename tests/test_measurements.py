"""Reference measurements must expose missing evidence and stable particle identity."""
import importlib

import numpy as np
import pytest


@pytest.fixture
def measurements():
    return importlib.import_module('app.measurements')


def detection(x, y=20, rx=2, ry=3):
    return dict(x=x, y=y, rx=rx, ry=ry)


def samples_starting_at(tracks, x):
    return next(t['samples'] for t in tracks if t['samples'][0]['x'] == x)


def test_tracking_preserves_identity_and_measurements_during_linear_motion(measurements):
    frames = [
        [detection(10, rx=2), detection(100, rx=4)],
        [detection(103, rx=4.5), detection(13, rx=2.5)],
        [detection(16, rx=3), detection(106, rx=5)],
    ]
    tracks = measurements.track_detections(frames)
    assert len(tracks) == 2
    assert len({t['id'] for t in tracks}) == 2
    assert all(isinstance(t['id'], int) for t in tracks)
    first = samples_starting_at(tracks, 10)
    assert [s['frame'] for s in first] == [0, 1, 2]
    assert [s['x'] for s in first] == [10, 13, 16]
    assert [s['rx'] for s in first] == [2, 2.5, 3]
    assert all(s['y'] == 20 and s['ry'] == 3 for s in first)
    assert [s['x'] for s in samples_starting_at(tracks, 100)] == [100, 103, 106]


def test_tracking_starts_new_identity_for_distant_birth_and_retains_death(measurements):
    tracks = measurements.track_detections([
        [detection(10)], [detection(12), detection(100)], [detection(102)],
    ], max_distance=10)
    assert len(tracks) == 2
    assert [s['frame'] for s in samples_starting_at(tracks, 10)] == [0, 1]
    assert [s['frame'] for s in samples_starting_at(tracks, 100)] == [1, 2]


@pytest.mark.parametrize('frames', [[], [[]], [[], [], []]])
def test_tracking_empty_frames_produce_no_tracks(measurements, frames):
    assert measurements.track_detections(frames) == []


def test_tracking_bridges_one_missing_frame_without_inventing_observation(measurements):
    tracks = measurements.track_detections([
        [detection(10)], [detection(14)], [], [detection(22)],
    ], max_distance=5, max_gap=1)
    assert len(tracks) == 1
    assert [s['frame'] for s in tracks[0]['samples']] == [0, 1, 3]
    assert [s['x'] for s in tracks[0]['samples']] == [10, 14, 22]


def test_tracking_expires_identity_after_gap_limit(measurements):
    tracks = measurements.track_detections([
        [detection(10)], [], [], [detection(10)],
    ], max_gap=1)
    assert len(tracks) == 2
    assert sorted(s['frame'] for t in tracks for s in t['samples']) == [0, 3]
    assert len({t['id'] for t in tracks}) == 2


def test_tracking_never_assigns_two_detections_to_one_track_in_same_frame(measurements):
    tracks = measurements.track_detections([
        [detection(10)], [detection(11), detection(12)],
    ])
    assert len(tracks) == 2
    assert sum(len(t['samples']) for t in tracks) == 3
    for track in tracks:
        indices = [sample['frame'] for sample in track['samples']]
        assert len(indices) == len(set(indices))


def test_tracking_uses_velocity_to_preserve_identity_through_crossing(measurements):
    tracks = measurements.track_detections([
        [detection(0), detection(14)],
        [detection(10), detection(4)],
        [detection(6), detection(8)],
        [detection(12), detection(2)],
    ])
    assert len(tracks) == 2
    assert [s['x'] for s in samples_starting_at(tracks, 0)] == [0, 4, 8, 12]
    assert [s['x'] for s in samples_starting_at(tracks, 14)] == [14, 10, 6, 2]


def test_identical_silhouettes_have_perfect_overlap_and_zero_distance(measurements):
    mask = np.zeros((48, 64), dtype=bool)
    mask[10:30, 12:36] = True
    result = measurements.silhouette_metrics(mask, mask.copy())
    assert result['iou'] == pytest.approx(1)
    assert result['mean_distance'] == pytest.approx(0)
    assert result['max_distance'] == pytest.approx(0)


def test_displaced_silhouette_reports_pixel_error_symmetrically(measurements):
    reference = np.zeros((48, 64), dtype=bool)
    reference[10:30, 12:36] = True
    rendered = np.roll(reference, 4, axis=1)
    result = measurements.silhouette_metrics(reference, rendered)
    reverse = measurements.silhouette_metrics(rendered, reference)
    assert result['iou'] == pytest.approx(20 / 28)
    assert result['mean_distance'] > 0
    assert result['max_distance'] == pytest.approx(4, abs=.01)
    assert reverse == pytest.approx(result)


@pytest.mark.parametrize('reference_missing', [True, False])
def test_missing_silhouette_is_explicitly_unmeasurable(measurements, reference_missing):
    present = np.zeros((48, 64), dtype=bool)
    present[10:30, 12:36] = True
    missing = np.zeros_like(present)
    pair = (missing, present) if reference_missing else (present, missing)
    result = measurements.silhouette_metrics(*pair)
    assert result['iou'] == 0
    assert result['mean_distance'] is None
    assert result['max_distance'] is None
