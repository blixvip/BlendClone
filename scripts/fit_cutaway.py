"""One-frame silhouette pilot against the existing cutaway benchmark.

Run with .venv/Scripts/python.exe scripts/fit_cutaway.py.
The result is a measured still experiment, not a full-video reconstruction.
"""
import json
import sys
import threading
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.fitting import upper_contour, fit_vertical_envelope
from app.models import Plan
from app.media import probe
from app.render import render


def skin_mask(image):
    """Benchmark-specific warm skin against blue background; discard thin hairs."""
    b, g, r = cv2.split(image.astype(np.float32))
    mask = ((r > 80) & (r > b * 1.08) & (r > g * 1.03)).astype(np.uint8)
    mask[int(len(mask) * .55):] = 0
    width = max(3, round(image.shape[1] * .022))
    return cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((1, width), np.uint8))


def main():
    out = ROOT / 'outputs' / 'cutaway-fit'
    out.mkdir(parents=True, exist_ok=True)
    source = ROOT / 'data/references/splinter/source.mp4'
    meta = probe(source)
    # Choose the nearest original frame, then use that exact timestamp everywhere.
    index = round(14 * meta['fps'])
    seconds = index / meta['fps']
    cap = cv2.VideoCapture(str(source))
    try:
        cap.set(cv2.CAP_PROP_POS_FRAMES, index)
        ok, reference = cap.read()
        if not ok:
            raise ValueError('Could not decode benchmark frame.')
    finally:
        cap.release()
    cv2.imwrite(str(out / 'reference.png'), reference)
    contour = upper_contour(skin_mask(reference))
    height, width = reference.shape[:2]
    receipt = json.loads((ROOT / 'data/references/splinter/hero-job.json').read_text())
    plan = Plan.model_validate_json((ROOT / 'data/projects' / receipt['id'] / 'plan.json').read_text(encoding='utf-8'))
    plan.engine = 'CYCLES'
    # This pilot uses the benchmark's known orthographic front camera.
    camera = plan.shots[0].camera
    if not camera.orthographic or camera.location[0] != camera.target[0] or camera.location[2] != camera.target[2]:
        raise ValueError('Pilot requires the calibrated front orthographic camera.')
    xs = ((np.arange(width) + .5) / width - .5) * camera.ortho_scale * width / height + camera.target[0]
    zs = (.5 - (contour + .5) / height) * camera.ortho_scale + camera.target[2]
    fitted = plan.model_copy(deep=True)
    skin = next(o for o in fitted.shots[0].objects if o.id == 'rounded_inflamed_cap')
    skin.vertices = fit_vertical_envelope(skin.vertices, xs, zs)
    fitted = Plan.model_validate(fitted.model_dump())
    local_time = seconds - 13.5
    render_meta = dict(meta, duration=plan.shots[-1].end)
    rows, scores = [], {}
    for name, candidate in [('before', plan), ('after', fitted)]:
        folder = out / name
        folder.mkdir(exist_ok=True)
        print('Rendering', name, flush=True)
        path = render(folder, candidate, render_meta, 'standard', threading.Event(), times=[local_time])[0]
        image = cv2.imread(str(path))
        target = cv2.resize(reference, (image.shape[1], image.shape[0]), interpolation=cv2.INTER_AREA)
        observed = upper_contour(skin_mask(image))
        expected = upper_contour(skin_mask(target))
        # Report in original source pixels, over the central 90% of the visible contour.
        margin = round(image.shape[1] * .05)
        errors = np.abs(observed[margin:-margin] - expected[margin:-margin]) * height / image.shape[0]
        scores[name] = dict(mean_outline_error_px=float(errors.mean()), max_outline_error_px=float(errors.max()))
        rows.append(image)
    panel = np.hstack([target, *rows])
    cv2.imwrite(str(out / 'comparison.png'), panel)
    report = dict(source_frame=index, source_time=seconds, measurements=scores,
                  scope='One still, upper skin outline only. Materials, internal anatomy and motion remain unmatched.')
    (out / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report), flush=True)


if __name__ == '__main__':
    main()
