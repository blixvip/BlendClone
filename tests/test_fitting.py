import numpy as np
import pytest

from app.fitting import upper_contour, fit_vertical_envelope


def test_contour_interpolates_small_occlusion_but_rejects_missing_subject():
    mask = np.zeros((12, 10), bool)
    mask[4:, :] = True
    mask[:, 4] = False
    assert np.allclose(upper_contour(mask), 4)
    with pytest.raises(ValueError, match='coverage'):
        upper_contour(np.zeros_like(mask))


def test_fit_moves_measured_outline_preserves_base_and_depth():
    vertices = [(x, y, z) for x in (-1, 0, 1) for y in (0, 1) for z in (0, 1, 2)]
    fitted = np.array(fit_vertical_envelope(vertices, [-1, 0, 1], [3, 4, 3]))
    original = np.array(vertices)
    assert np.allclose(fitted[:, :2], original[:, :2])
    assert np.allclose(fitted[original[:, 2] == 0, 2], 0)
    assert np.allclose(fitted[original[:, 2] == 2, 2], [3, 3, 4, 4, 3, 3])
