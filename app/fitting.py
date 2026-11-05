"""Fit editable mesh geometry to measured silhouettes; no source textures."""
import numpy as np


def upper_contour(mask, min_coverage=.9):
    mask = np.asarray(mask, dtype=bool)
    if mask.ndim != 2 or not mask.size:
        raise ValueError('Expected a nonempty two-dimensional silhouette mask.')
    present = mask.any(axis=0)
    if present.mean() < min_coverage or not present.any():
        raise ValueError('Insufficient silhouette coverage; review the subject mask.')
    columns = np.arange(mask.shape[1])
    return np.interp(columns, columns[present], mask[:, present].argmax(axis=0))


def fit_vertical_envelope(vertices, measured_x, measured_top):
    """Fit a mesh sampled in vertical rings, preserving each ring's base and depth."""
    points = np.asarray(vertices, dtype=float).copy()
    xs, tops = np.asarray(measured_x, float), np.asarray(measured_top, float)
    if (points.ndim != 2 or points.shape[1] != 3 or not len(points)
            or xs.ndim != 1 or xs.shape != tops.shape or len(xs) < 2
            or not np.all(np.diff(xs) > 0)
            or not all(np.isfinite(a).all() for a in (points, xs, tops))):
        raise ValueError('Invalid mesh or measured contour.')
    for x in np.unique(points[:, 0]):
        indices = points[:, 0] == x
        z = points[indices, 2]
        bottom, top = z.min(), z.max()
        if top - bottom < 1e-8:
            continue
        target = float(np.interp(x, xs, tops))
        if target <= bottom:
            raise ValueError('Measured contour crosses the mesh base.')
        points[indices, 2] = bottom + (z - bottom) * (target - bottom) / (top - bottom)
    return [tuple(point) for point in points.tolist()]
