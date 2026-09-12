"""Full reference-specific reconstruction, authored and calibrated against yGw0nhlUtkQ.

Run without flags for keyframes, or --animate for the complete 30-second render.
This is a curated benchmark, not a claim of one-click fidelity on arbitrary footage.
"""
import json
import math
import shutil
import sys
import threading
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.models import Plan,Shot,Camera,Light,Object,Key,ShapeKey,Material
from app.anatomy import palette,mesh
from app.media import prepare,probe,download
from app.render import render,encode
from app.pipeline import Pipeline
from app.store import Store

ROOT=Path(__file__).resolve().parents[1]


def key(t,values,prop='location',interpolation='BEZIER'):
    return Key(t=t,property=prop,value=values,interpolation=interpolation)


def asset(name,kind,**kw):
    return Object(id=name,kind='asset',asset=kind,**kw)


def swelling(points,amplitude=1.1,section=False):
    return ShapeKey(name='swelling',center=(0,0,0),radius=(1.8,2.5 if section else 1.8,1.1 if section else 100),displacement=(0,0,amplitude),
                    keys=[key(t,(v,0,0),'scale') for t,v in points])


def lights():
    return [Light(location=(-4,-5,8),energy=600,size=5),Light(location=(4,-2,3),energy=260,size=4,color='#FEEBE2'),Light(location=(-1,4,5),energy=400,size=3,color='#FFFFFF')]


def make_shot(name,start,end,objects,camera,description):
    objects.append(Object(id='blue_background',kind='plane',material='blue_backdrop',location=(0,12,0),rotation=(90,0,0),scale=(100,100,100)))
    return Shot(name=name,start=start,end=end,objects=objects,camera=camera,lights=lights(),background='#353535',description=description)


def arrow(name,location,rotation,delay,duration):
    outline=[(-.7,-.07),(.18,-.07),(.18,-.2),(.65,0),(.18,.2),(.18,.07),(-.7,.07)]
    v=[(x,y,z) for y in [-.025,.025] for x,z in outline]
    f=[list(range(6,-1,-1)),list(range(7,14))]+[[i,(i+1)%7,(i+1)%7+7,i+7] for i in range(7)]
    return mesh(name,v,f,'arrow',location=location,rotation=rotation,bevel=.008,
                keys=[key(0,(0,0,0),'scale'),key(delay,(0,0,0),'scale'),key(delay+.2,(1,1,1),'scale'),key(duration,(1,1,1),'scale')])


def plan_for(duration):
    shots=[]
    shots.append(make_shot('Contact with wood',0,.7,[
        asset('hand','hand',location=(.7,-.2,-.15),rotation=(0,-18,-10)),
        Object(id='board',kind='cube',material='wood_board',location=(-.95,.5,2),scale=(.36,1.5,4.5)),
        asset('sliver','splinter',location=(-.3,-.2,3.75),scale=(.16,.16,.16))],
        Camera(location=(4,-11,4),target=(0,0,2),lens=58),
        'A pointing hand contacts the wooden surface. The brief opening hand pose is a procedural approximation.'))
    shots.append(make_shot('The splinter in the finger',.7,1.7,[
        asset('hand','hand',location=(0,0,0)),asset('sliver','splinter',location=(-.32,-.03,4.03),scale=(.16,.16,.16))],
        Camera(location=(.5,-10,3),target=(0,0,2.2),orthographic=True,ortho_scale=6.7),
        'The index finger is raised against the blue background, with the splinter visible at its tip.'))
    shots.append(make_shot('Tweezers remove a shallow splinter',1.7,5.1,[
        asset('finger','finger'),
        asset('sliver','splinter',location=(0,-.06,3.9),scale=(.16,.16,.19),keys=[key(0,(0,-.06,3.9)),key(1.6,(0,-.06,3.9)),key(2.7,(0,-.06,6.6))]),
        asset('tweezers','tweezers',location=(0,0,7),scale=(.65,.65,.65),keys=[key(0,(0,0,7)),key(1.4,(0,-.06,4.3)),key(1.6,(0,-.06,4.3)),key(2.7,(0,-.06,7.1))])],
        Camera(location=(.05,-10,3.85),target=(0,0,3.85),orthographic=True,ortho_scale=5.8),
        'Close-up of the finger pad. A metallic tweezer descends, grasps the exposed shard, and pulls it out.'))
    shots.append(make_shot('A deeply lodged splinter',5.1,7.7,[
        asset('section','skin_section'),asset('sliver','splinter',location=(-.43,-.38,-2.65),rotation=(0,8,0))],
        Camera(location=(.1,-14,.8),target=(0,0,-1.3),lens=63,aperture=12),
        'Macro anatomical cutaway: packed epidermal cells, glossy dermis, follicles, branching nerves and vessels, fat lobules, and a deeply embedded wooden shard.'))
    shots.append(make_shot('Out of reach, then inflammation',7.7,12.8,[
        asset('surface','skin_surface',shapes=[swelling([(0,0),(2.7,0),(4,.22),(5.1,.8)])]),
        asset('buried_sliver','splinter',location=(-.2,0,-2.85),scale=(.8,.8,.85)),
        asset('tweezers','tweezers',scale=(.7,.7,2),keys=[key(0,(0,0,5)),key(1,(0,0,.1)),key(1.8,(0,0,.1)),key(2.7,(0,0,5.5))])],
        Camera(location=(0,-9,4.5),target=(0,0,.8),lens=42,aperture=9),
        'The camera returns to the textured skin surface. Tweezers cannot reach the buried shard. The red wound gradually swells.'))
    cap=swelling([(0,.72),(.6,1),(10.2,1)],.78,True)
    cap.name='swelling_left';cap.center=(-.45,0,0)
    cap_right=cap.model_copy(deep=True);cap_right.name='swelling_right';cap_right.center=(.45,0,0)
    objects=[asset('section','skin_section',material='skin_red',shapes=[cap,cap_right]),
             asset('sliver','splinter',location=(-.43,-.4,-2.65),rotation=(0,8,0),keys=[key(0,(-.43,-.4,-2.65)),key(4,(-.43,-.4,-2.65)),key(10.2,(-.27,-.4,-1.3))])]
    import random
    rng=random.Random(413)
    for i in range(64):
        x=rng.uniform(-.65,.62);z=rng.uniform(-3,-.4);r=rng.uniform(.028,.065);delay=rng.uniform(.15,2)
        objects.append(Object(id=f'pus_particle_{i}',kind='sphere',material='pus_bright' if i%4==0 else 'pus',location=(x,-.55,z),scale=(0,0,0),
            keys=[key(0,(0,0,0),'scale'),key(delay,(0,0,0),'scale'),key(delay+.35,(r,r,r),'scale'),
                  key(0,(x,-.55,z)),key(3,(x+.1*math.sin(i),-.55,z+.2)),key(6,(x-.1*math.sin(i),-.55,z+.55)),key(10.2,(x+.15,-.55,z+.9))]))
    objects.extend([arrow('pressure_left',(-1.45,-.65,-1.65),(0,-12,0),3.8,10.2),arrow('pressure_right',(1.35,-.65,-1.65),(0,192,0),3.8,10.2)])
    shots.append(make_shot('Swelling and upward pressure',12.8,23,objects,
        Camera(location=(0,-14,.8),target=(0,0,-1.1),lens=63,aperture=14,keys=[key(0,(0,-14,.8)),key(5,(0,-11.8,.6)),key(10.2,(0,-12.8,.8))]),
        'A raised red skin cap deforms over the cellular cross-section. Yellow particles accumulate around the shard, pressure arrows appear, and the shard moves upward through the tissue.'))
    last=duration-23
    shots.append(make_shot('The splinter reaches the surface',23,duration,[
        asset('surface','skin_surface',shapes=[swelling([(0,.85),(1,.8),(3.9,.2),(last,.06)])]),
        asset('sliver','splinter',location=(-.2,0,-2.65),rotation=(0,5,0),keys=[key(0,(-.2,0,-2.65)),key(3.8,(-.2,0,-2.28)),key(5.5,(-.2,0,-2.2)),key(last,(-.2,0,1.3))]),
        asset('tweezers','tweezers',scale=(.7,.7,2),keys=[key(0,(-.03,0,7)),key(4.2,(-.03,0,7)),key(5.5,(-.03,0,.65)),key(last,(-.03,0,4.2))])],
        Camera(location=(0,-9,4.5),target=(0,0,.8),lens=42,aperture=9),
        'The camera returns above the skin. The swelling subsides, the shard becomes exposed, and the tweezers lift it away.'))
    return Plan(title='How Splinters Get Unstuck · Blender reconstruction',view_transform='Standard',
        summary='Full reference-specific 3D reconstruction: seven shots with editable anatomy, textured materials, swelling shape keys, tool animation, particles, pressure arrows, and camera movement. Authored and visually calibrated against the supplied reference; not a one-click generalization benchmark.',
        limitations=['Procedural hand and skin assets approximate the source models; they are not recovered original assets.',
                     'The brief flip transition and embedded source captions are not reconstructed.',
                     'Tissue geometry and particle movement are illustrative, not medically validated simulation.',
                     'Framing, surface appearance, and fine motion still require visual comparison with the source.'],
        materials=palette()+[Material(id='blue_backdrop',color='#45AEE0',emission=1,unlit=True)],shots=shots)


def main():
    store=Store(ROOT/'data'/'projects')
    receipt=ROOT/'data'/'references'/'splinter'/'rebuild-job.json'
    receipt.parent.mkdir(parents=True,exist_ok=True)
    if receipt.exists():job=store.get(json.loads(receipt.read_text())['id'])
    else:
        job=store.create(dict(title='Splinter reference reconstruction',url='https://www.youtube.com/shorts/yGw0nhlUtkQ',brief='Reference-specific complex reconstruction',start=0,duration=30.363667,quality='standard',audio=True,review=False))
        receipt.write_text(json.dumps({'id':job['id']}),encoding='utf-8')
    folder=store.folder(job['id']);cancel=threading.Event()
    if not (folder/'reference.mp4').exists():
        source=receipt.parent/'source.mp4'
        if not source.exists():download('https://www.youtube.com/shorts/yGw0nhlUtkQ',source,cancel)
        shutil.copy2(source,folder/'source.bin')
        meta=prepare(folder/'source.bin',folder,0,30.363667,cancel)
    else:meta=probe(folder/'reference.mp4')
    plan=plan_for(meta['duration'])
    times=[.3,1.1,2.7,6.3,9.3,12.2,14.5,18.2,21.5,24.8,28.8]
    if '--cutaway' in sys.argv:times=[6.3,14.5,18.2]
    if '--check' in sys.argv:times=[1.1,2.7,9.3,14.5]
    store.update(job['id'],title=plan.title,status='running',progress=35,message='Rendering the actual splinter reference',meta=meta,summary=plan.summary,limitations=plan.limitations,
                 shots=[dict(name=s.name,start=s.start,end=s.end,description=s.description,objects=len(s.objects)) for s in plan.shots],artifacts={'reference':'reference.mp4'})
    print('PROJECT',job['id'],'duration',meta['duration'],flush=True)
    render(folder,plan,meta,'standard',cancel,times=times,engine='BLENDER_EEVEE')
    print('PREVIEWS',folder/'previews',flush=True)
    if '--animate' in sys.argv:
        store.update(job['id'],progress=70,message='Rendering all seven shots')
        render(folder,plan,meta,'standard',cancel,mode='animation',engine='BLENDER_EEVEE')
        encode(folder,meta['duration'],True,cancel)
        Pipeline.package(folder,plan)
        store.update(job['id'],status='completed',progress=100,message='Reference reconstruction ready for comparison',artifacts=dict(reference='reference.mp4',video='remake.mp4',blend='remake.blend',comparison='comparison.mp4',project='project.zip',plan='plan.json',poster='previews/000.png'))
        print('COMPLETED',job['id'],flush=True)
    else:
        store.update(job['id'],status='interrupted',message='Keyframes ready for visual inspection; full animation pending.',artifacts={'reference':'reference.mp4','blend':'remake.blend','plan':'plan.json','poster':'previews/000.png'})


if __name__=='__main__':main()
