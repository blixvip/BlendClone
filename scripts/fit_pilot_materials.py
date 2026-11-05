"""Measured material/light coordinate search using one persistent Blender process."""
import json
import sys
import threading
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.fidelity import ciede2000, lab
from app.models import Plan
from app.worker import BlenderWorker
from app.render import render

OUT = ROOT / 'outputs/reconstruction-pilot'


def score(path, reference):
    image = cv2.imread(str(path))
    target = cv2.resize(reference,(image.shape[1],image.shape[0]),interpolation=cv2.INTER_AREA)
    # Coarse, fixed regions: cap, dermis, fat. Captions are excluded from material fitting.
    a,b = [cv2.cvtColor(cv2.GaussianBlur(im,(0,0),2),cv2.COLOR_BGR2RGB) for im in (target,image)]
    delta = ciede2000(lab(a),lab(b))
    h,w = delta.shape
    regions = [(0.05,.4,.1,.9),(.42,.72,.05,.95),(.89,1,.05,.95)]
    values = [float(delta[int(y0*h):int(y1*h),int(x0*w):int(x1*w)].mean()) for y0,y1,x0,x1 in regions]
    return float(np.mean(values)), values


def main():
    source = OUT / 'measured'
    plan = Plan.model_validate_json((source/'plan.json').read_text(encoding='utf-8'))
    meta = json.loads((OUT/'meta.json').read_text())
    folder = OUT / 'material-fit'
    folder.mkdir(exist_ok=True)
    render(folder,plan,meta,'draft',threading.Event(),times=[])
    reference = cv2.imread(str(OUT/'reference/0420.png'))
    history=[]
    with BlenderWorker(folder/'remake.blend',folder/'worker',threading.Event()) as worker:
        image=worker.render(plan)
        best,regions=score(image,reference)
        history.append(dict(name='baseline',score=best,regions=regions,image=str(image)))
        print('Baseline',best,flush=True)
        # Coordinate search: each accepted group becomes the base for the next group.
        groups = [
            ('key_position',[(-3,-6,.5),(-3,-6,1.5),(-4,-5,2)]),
            ('key_energy',[180,300,700]),
            ('rim_energy',[0,150,350]),
            ('cap_roughness',[.2,.45,.65]),
            ('cap_color',['#E52212','#C91C10','#F04425']),
            ('dermis_color',['#E52E12','#C92815','#ED6940']),
            ('fat_color',['#F38D12','#F4AC26','#FCB93E']),
        ]
        for group,values in groups:
            base=plan.model_copy(deep=True)
            for value in values:
                candidate=base.model_copy(deep=True)
                materials={m.id:m for m in candidate.materials}
                lights=candidate.shots[0].lights
                if group=='key_position':lights[0].location=value
                elif group=='key_energy':lights[0].energy=value
                elif group=='rim_energy':lights[2].energy=value
                elif group=='cap_roughness':materials['hero_cap'].roughness=value
                elif group=='cap_color':
                    materials['hero_cap'].color=value
                    materials['hero_cap'].detail_color=value
                elif group=='dermis_color':materials['hero_dermis'].color=value
                elif group=='fat_color':
                    materials['hero_fat'].color=value
                    materials['hero_fat_light'].color=value
                image=worker.render(candidate)
                value_score,regions=score(image,reference)
                accepted=value_score < best
                history.append(dict(name=group,value=value,score=value_score,regions=regions,accepted=accepted,image=str(image)))
                print(group,value,round(value_score,3),'accepted' if accepted else 'retained best',flush=True)
                if accepted:
                    plan,best=candidate,value_score
            (folder/'best-plan.json').write_text(plan.model_dump_json(),encoding='utf-8')
            (folder/'history.json').write_text(json.dumps(history,indent=2),encoding='utf-8')
        final_image=worker.render(plan,frame=29)
        validation,regions=score(final_image,cv2.imread(str(OUT/'reference/0449.png')))
        history.append(dict(name='held-out-frame-449',score=validation,regions=regions,image=str(final_image)))
    (folder/'history.json').write_text(json.dumps(history,indent=2),encoding='utf-8')
    print('Best frame-420 color distance',best,'held-out 449',validation,flush=True)


if __name__=='__main__':main()
