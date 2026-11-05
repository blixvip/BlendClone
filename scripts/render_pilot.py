"""Render and package the best measured pilot in a new immutable run directory."""
import argparse
import json
import sys
import threading
import uuid
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from app.models import Plan
from app.render import render, encode, blender_binary
from app.process import run
from app.pipeline import Pipeline

out=ROOT/'outputs/reconstruction-pilot'
parser=argparse.ArgumentParser()
parser.add_argument('--quality',choices=['draft','standard','final'],default='standard')
args=parser.parse_args()
plan=Plan.model_validate_json((out/'measured/plan.json').read_text(encoding='utf-8'))
appearance=Plan.model_validate_json((out/'material-fit/best-plan.json').read_text(encoding='utf-8'))
fitted_materials={material.id:material for material in appearance.materials}
plan.materials=[fitted_materials.get(material.id,material) for material in plan.materials]
plan.shots[0].lights=appearance.shots[0].lights
meta=json.loads((out/'meta.json').read_text())
folder=out/'renders'/uuid.uuid4().hex[:12]
folder.mkdir(parents=True)
(out/'active-render.json').write_text(json.dumps(dict(folder=str(folder))),encoding='utf-8')
cancel=threading.Event()
run(['ffmpeg','-y','-v','error','-framerate','30000/1001','-start_number','420','-i',out/'reference/%04d.png',
     '-frames:v','30','-c:v','libx264','-crf','18','-pix_fmt','yuv420p',folder/'reference.mp4'],timeout=180)
last=[-1]
def progress(n,total):
    if n != last[0]:
        print(f'{args.quality} pilot: {n}/{total}',flush=True)
        last[0]=n
render(folder,plan,meta,args.quality,cancel,mode='animation',on_progress=progress)
run([blender_binary(),'--background','--factory-startup',folder/'remake.blend','--disable-autoexec','--python-exit-code','1',
     '--python',ROOT/'scripts/verify_pilot.py','--',folder],timeout=300,cancel=cancel,log=folder/'native-verification.log')
encode(folder,meta['duration'],False,cancel,folder/'reference.mp4')
Pipeline.package(folder,plan)
(out/'finished-render.json').write_text(json.dumps(dict(folder=str(folder))),encoding='utf-8')
print(f'{args.quality} pilot saved:',folder,flush=True)
