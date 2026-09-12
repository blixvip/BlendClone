import json
import sys
import threading
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.models import fixture_plan
from app.render import render, encode
from app.media import probe
from app.process import run

root = Path(__file__).resolve().parents[1]
folder = root / 'outputs' / 'renderer-check'
folder.mkdir(parents=True, exist_ok=True)
plan = fixture_plan()
meta = dict(duration=2.0, width=720, height=960, audio=False)
cancel = threading.Event()
render(folder, plan, meta, 'draft', cancel, mode='preview', times=[0, .8, 1.15])
render(folder, plan, meta, 'draft', cancel, mode='animation')
run(['ffmpeg', '-y', '-v', 'error', '-framerate', '24', '-i', folder/'frames'/'frame-%04d.png', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', folder/'reference.mp4'])
encode(folder, 2.0, False, cancel)
inventory = json.loads((folder/'inventory.json').read_text())
assert inventory['meshes'] == 3 and inventory['animated_objects'] >= 3
assert inventory['cameras'] == 1 and inventory['frames'] == 48
assert abs(probe(folder/'remake.mp4')['duration']-2) < .05
print(json.dumps(inventory))
print(f'Renderer and encoding passed. Synthetic reference: {folder / "reference.mp4"}')
