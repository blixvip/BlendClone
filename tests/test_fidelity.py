import numpy as np
import pytest

from app import fidelity

GATES = dict(calibrated=False, gates=dict(coarse_ssim_min=.95, delta_e_max=5, flow_epe_max=1, timing_lag_max=0))


@pytest.mark.parametrize('lab1, lab2, expected', [
    # Reference pairs from Sharma, Wu & Dalal (2005), Table 1.
    ((50, 2.6772, -79.7751), (50, 0, -82.7485), 2.0425),
    ((50, -1.3802, -84.2814), (50, 0, -82.7485), 1.0000),
    ((50, 0, 0), (50, -1, 2), 2.3669),
    ((50, 2.5, 0), (73, 25, -18), 27.1492),
    ((90.8027, -2.0831, 1.4410), (91.1528, -1.6435, 0.0447), 1.4441),
])
def test_ciede2000_matches_published_values(lab1, lab2, expected):
    result = fidelity.ciede2000(np.array(lab1, float), np.array(lab2, float))
    assert float(result) == pytest.approx(expected, abs=1e-4)


def test_ssim_is_one_for_identical_and_drops_for_shift():
    rng = np.random.default_rng(3)
    image = (rng.random((64, 64)) * 255).astype(np.uint8)
    assert fidelity.ssim(image, image) == pytest.approx(1)
    assert fidelity.ssim(image, np.roll(image, 3, axis=1)) < .5


def test_best_lag_finds_late_events_and_zero_for_aligned():
    curve = np.zeros(40)
    curve[[8, 20, 31]] = 10
    assert fidelity.best_lag(curve, curve)[0] == 0
    assert fidelity.best_lag(curve, np.roll(curve, 2))[0] == -2


def test_verdict_requires_every_frame_timing_and_calibration():
    info = dict(width=10, height=10, fps=24.0, frames=2, bitrate=1, color_range='tv', color_space='bt709')
    good = [dict(frame=i, ssim=.9, coarse_ssim=.99, delta_e=1, flow_epe=None if i == 0 else .1) for i in range(2)]
    for record in good:
        record['passes'] = fidelity.frame_passes(record, GATES['gates'])
    report = fidelity.build_report(info, info, (10, 10), good, 0, 1, GATES)
    assert report['verdict'] == 'metrics-pass-uncalibrated'
    assert fidelity.build_report(info, info, (10, 10), good, 0, 1, dict(GATES, calibrated=True))['verdict'] == 'metrics-pass'
    assert fidelity.build_report(info, info, (10, 10), good, 1, 1, dict(GATES, calibrated=True))['verdict'] == 'approximate'
    short = dict(info, frames=3)
    assert fidelity.build_report(info, short, (10, 10), good, 0, 1, dict(GATES, calibrated=True))['verdict'] == 'approximate'
    bad = [dict(good[0]), dict(good[1], delta_e=9)]
    bad[1]['passes'] = fidelity.frame_passes(bad[1], GATES['gates'])
    assert fidelity.build_report(info, info, (10, 10), bad, 0, 1, dict(GATES, calibrated=True))['verdict'] == 'approximate'


def test_shipped_gates_are_valid():
    assert set(fidelity.load_gates()['gates']) >= {'coarse_ssim_min', 'delta_e_max', 'flow_epe_max', 'timing_lag_max'}
