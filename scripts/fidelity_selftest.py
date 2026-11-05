"""Prove the fidelity harness on original content with known ground truth.

Renders the built-in ball-drop scene as a "reference", then scores:
  same      - an identical rebuild (must pass every frame)
  moved     - the ball shifted sideways (must fail layout)
  recolored - the ball a different color (must fail color)
  late      - the bounce 3 frames late (must fail timing/motion)
Usage: .venv/Scripts/python.exe scripts/fidelity_selftest.py
"""
import json
import shutil
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import fidelity, render  # noqa: E402
from app.models import fixture_plan  # noqa: E402
from app.process import run  # noqa: E402

OUT = ROOT / 'outputs' / 'fidelity-selftest'
META = dict(duration=2, width=1280, height=720, fps=24, audio=False)


def build(name, plan):
    folder = OUT / name
    if folder.exists():
        shutil.rmtree(folder)
    folder.mkdir(parents=True)
    render.render(folder, plan, META, 'draft', threading.Event(), mode='animation', engine='BLENDER_EEVEE')
    return folder


def variant(kind):
    plan = fixture_plan()
    ball = plan.shots[0].objects[0]
    if kind == 'moved':
        for key in ball.keys:
            key.value = (key.value[0] + .35, key.value[1], key.value[2])
    elif kind == 'recolored':
        plan.materials[0].color = '#3f7df1'
    elif kind == 'late':
        for key in ball.keys[1:-1]:
            key.t = round(key.t + 3 / 24, 4)
    return plan


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    reference_run = build('reference', fixture_plan())
    reference = OUT / 'reference.mp4'
    run(['ffmpeg', '-y', '-v', 'error', '-framerate', '24', '-i', reference_run / 'frames' / 'frame-%04d.png',
         '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-crf', '18', '-colorspace', 'bt709', '-color_range', 'tv', reference], timeout=300)
    results = {}
    for kind in ('same', 'moved', 'recolored', 'late'):
        attempt = build(kind, variant(kind))
        report = fidelity.score_run(reference, attempt, META)
        results[kind] = dict(verdict=report['verdict'], passing=f"{report['passing_frames']}/{report['frames']}",
                             timing=report['timing'], metrics=report['metrics'])
        print(kind, json.dumps(results[kind]))
    (OUT / 'selftest.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
    expected_pass = results['same']['verdict'].startswith('metrics-pass')
    expected_fail = all(results[k]['verdict'] == 'approximate' for k in ('moved', 'recolored', 'late'))
    print('SELFTEST', 'OK' if expected_pass and expected_fail else 'FAILED')
    return 0 if expected_pass and expected_fail else 1


if __name__ == '__main__':
    raise SystemExit(main())
