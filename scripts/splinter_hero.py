"""Measured cutaway revision. Build and inspect stills before any animation render."""
import json
import sys
import threading
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.models import Plan,Shot,Camera,Light
from app.reference_anatomy import cutaway,materials
from app.render import render,encode
from app.media import prepare
from app.store import Store
from app.pipeline import Pipeline

ROOT=Path(__file__).resolve().parents[1]
def main():
    store=Store(ROOT/'data/projects');receipt=ROOT/'data/references/splinter/hero-job.json'
    if receipt.exists():job=store.get(json.loads(receipt.read_text())['id'])
    else:
        job=store.create(dict(title='Splinter: measured cutaway revision',url='',brief='Reference frame audit and matched cutaway revision',start=13.5,duration=3,quality='standard',audio=True,review=False))
        receipt.write_text(json.dumps({'id':job['id']}),encoding='utf-8')
    folder=store.folder(job['id']);cancel=threading.Event()
    meta=prepare(ROOT/'data/references/splinter/source.mp4',folder,13.5,3,cancel)
    plan=Plan(title=job['title'],view_transform='Standard',summary='Cutaway revision measured against source frames, with rebuilt tissue relief, rounded skin, traced branching networks, and revised lighting.',limitations=['Work in progress toward the requested 1:1 target. This three-second cutaway is a visual test, not a completed full-video replica.'],materials=materials(),shots=[Shot(name='Measured cutaway',start=0,end=meta['duration'],description='Matched cutaway geometry and lighting test.',background='#626262',camera=Camera(location=(0,-16,-1.1),target=(0,0,-1.1),orthographic=True,ortho_scale=8),lights=[Light(location=(-3,-4,4),target=(0,0,-1),energy=500,size=3),Light(location=(3,-2,0),target=(0,0,-2),energy=170,size=4),Light(location=(0,2,5),target=(0,0,0),energy=700,size=4)],objects=cutaway(meta['duration']))])
    store.update(job['id'],status='running',progress=35,message='Matching cutaway geometry and lighting',meta=meta,artifacts={'reference':'reference.mp4'},summary=plan.summary,limitations=plan.limitations)
    print('HERO PROJECT',job['id'],flush=True)
    render(folder,plan,meta,'standard',cancel,times=[.5],engine='CYCLES')
    print('PREVIEW',folder/'previews/000.png',flush=True)
    if '--animate' in sys.argv:
        render(folder,plan,meta,'standard',cancel,mode='animation',engine='CYCLES',on_progress=lambda done,total:store.update(job['id'],message=f'Rendering {done}/{total}',progress=70+round(23*done/total)))
        encode(folder,meta['duration'],True,cancel);Pipeline.package(folder,plan)
        store.update(job['id'],status='completed',progress=100,message='Cutaway revision ready for comparison',artifacts=dict(reference='reference.mp4',video='remake.mp4',comparison='comparison.mp4',blend='remake.blend',project='project.zip',poster='previews/000.png',plan='plan.json'),shots=[dict(name='Measured cutaway',start=0,end=meta['duration'],description=plan.shots[0].description,objects=len(plan.shots[0].objects))])
    else:store.update(job['id'],status='interrupted',message='Still ready for visual inspection; animation pending.',artifacts={'reference':'reference.mp4','blend':'remake.blend','plan':'plan.json','poster':'previews/000.png'})

if __name__=='__main__':main()
