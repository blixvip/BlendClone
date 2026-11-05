"""Measured 30-frame reconstruction pilot; outputs are experimental until visual acceptance."""
import argparse
import hashlib
import json
import sys
import threading
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.fitting import upper_contour, fit_vertical_envelope
from app.measurements import yellow_particles, track_detections
from app.models import Plan, Timeline, FrameKey, MeshSample, Object, Caption, Material, MaterialSample
from app.process import run
from app.render import render, encode
from fit_cutaway import skin_mask

OUT = ROOT / 'outputs/reconstruction-pilot'
SOURCE = ROOT / 'data/references/splinter/source.mp4'
FIRST, COUNT = 420, 30
RATE = 30000 / 1001
BOTTOM = [(0,623),(132,622),(222,645),(324,700),(459,748),(592,770),(650,752),(717,726),(827,662),(951,650),(1079,613)]


def extract():
    folder = OUT / 'reference'
    folder.mkdir(parents=True, exist_ok=True)
    if not all((folder / f'{n:04d}.png').exists() for n in range(FIRST, FIRST + COUNT)):
        run(['ffmpeg', '-y', '-v', 'error', '-i', SOURCE, '-vf', f'select=between(n\\,{FIRST}\\,{FIRST+COUNT-1})',
             '-fps_mode', 'passthrough', '-start_number', str(FIRST), folder / '%04d.png'], timeout=300)
    return [cv2.imread(str(folder / f'{n:04d}.png')) for n in range(FIRST, FIRST + COUNT)]


def measure(images):
    first_gray = cv2.cvtColor(images[0], cv2.COLOR_BGR2GRAY)
    anchors = np.array(BOTTOM, np.float32).reshape(-1, 1, 2)
    feature_mask = np.zeros_like(first_gray)
    feature_mask[800:1750,:] = 255
    feature_mask[740:1750,260:780] = 0
    feature_mask[1400:1600,:] = 0
    features = cv2.goodFeaturesToTrack(first_gray,200,.015,12,mask=feature_mask)
    results, detections = [], []
    for index, image in enumerate(images):
        contour = upper_contour(skin_mask(image))
        if index:
            current = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            points, valid, error = cv2.calcOpticalFlowPyrLK(first_gray, current, anchors, None,
                winSize=(41,41), maxLevel=3, criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 30, .01))
            points[valid.ravel() == 0] = anchors[valid.ravel() == 0]
            tracked,good,_ = cv2.calcOpticalFlowPyrLK(first_gray,current,features,None,winSize=(41,41),maxLevel=3)
            measured = good.ravel().astype(bool)
            affine,inliers = cv2.estimateAffinePartial2D(features[measured],tracked[measured],method=cv2.RANSAC,ransacReprojThreshold=3)
            if affine is None or inliers.sum() < 12:
                raise ValueError(f'Insufficient tissue motion evidence at frame {FIRST+index}')
        else:
            points = anchors.copy()
            valid = np.ones((len(anchors),1), np.uint8)
            affine = np.array([[1,0,0],[0,1,0]],float)
        bottom = points.reshape(-1,2)
        bottom = bottom[np.argsort(bottom[:,0])]
        results.append(dict(frame=FIRST+index, time=(FIRST+index)/RATE,
                            upper=contour.tolist(), lower=bottom.tolist(), tissue_affine=affine.tolist(), lower_tracking_valid=valid.ravel().astype(bool).tolist()))
        detections.append(yellow_particles(image))
    tracks = track_detections(detections, max_distance=35, max_gap=1)
    payload = dict(first_frame=FIRST, frame_count=COUNT, fps_num=30000, fps_den=1001,
                   lower_boundary_provenance='Agent-marked image landmarks at original frame 420, optical flow propagated; inspect overlay before acceptance.',
                   frames=results, particles=tracks,
                   limitations=['Touching/occluded particles can merge or be missed.', 'Lower boundary anchors are provisional measurements, not accepted ground truth.'])
    (OUT / 'measurements.json').write_text(json.dumps(payload), encoding='utf-8')
    return payload


def build(measurements, images):
    receipt = json.loads((ROOT / 'data/references/splinter/hero-job.json').read_text())
    plan = Plan.model_validate_json((ROOT / 'data/projects' / receipt['id'] / 'plan.json').read_text(encoding='utf-8'))
    plan.schema_version = 2
    plan.timeline = Timeline(frame_count=COUNT, source_start_frame=FIRST)
    plan.engine = 'CYCLES'
    plan.title = 'Frame-accurate reconstruction pilot · frames 420–449'
    plan.summary = 'Measured upper and lower skin boundaries and individual particle tracks across 30 original frames. Experimental; visual acceptance pending.'
    plan.limitations = ['The full appearance and anatomy remain approximate.', 'Particle segmentation may merge touching particles.', 'Captions and lower-boundary tracking require visual verification.']
    shot = plan.shots[0]
    shot.start, shot.end = 0, COUNT / RATE
    for obj in shot.objects:
        obj.keys = []
    shot.objects = [o for o in shot.objects if not o.id.startswith('pressure_particle_')]
    skin = next(o for o in shot.objects if o.id == 'rounded_inflamed_cap')
    camera = shot.camera
    height, width = images[0].shape[:2]
    world_x = lambda x: (np.asarray(x) / width - .5) * camera.ortho_scale * width / height + camera.target[0]
    world_z = lambda y: (.5 - np.asarray(y) / height) * camera.ortho_scale + camera.target[2]
    vertices = np.array(skin.vertices)
    xcoords = world_x(np.arange(width) + .5)
    for index, frame in enumerate(measurements['frames']):
        fitted = np.array(fit_vertical_envelope(skin.vertices, xcoords, world_z(np.array(frame['upper']) + .5)))
        bottom = np.array(frame['lower'])
        xs, zs = world_x(bottom[:,0]), world_z(bottom[:,1])
        for x in np.unique(vertices[:,0]):
            chosen = vertices[:,0] == x
            old = fitted[chosen,2]
            top, base = old.max(), old.min()
            new_base = float(np.interp(x, xs, zs))
            fitted[chosen,2] = new_base + (old-base) * (top-new_base) / max(top-base, 1e-6)
        skin.mesh_samples.append(MeshSample(frame=index, vertices=fitted.tolist()))
    skin.vertices = skin.mesh_samples[0].vertices
    backing = skin.model_copy(deep=True)
    backing.id, backing.material = 'continuous_skin_underlayer', 'hero_cells'
    backing.vertices = [(x,y+.1,z-.32) for x,y,z in backing.vertices]
    for sample in backing.mesh_samples:
        sample.vertices = [(x,y+.1,z-.32) for x,y,z in sample.vertices]
    shot.objects.append(backing)
    # Move the underlying cell row with the measured lower skin boundary.
    lower = np.array(measurements['frames'][0]['lower'])
    xs, zs = world_x(lower[:,0]), world_z(lower[:,1])
    for obj in shot.objects:
        if obj.id == 'irregular_epidermal_cells':
            updated = []
            for x,y,z in obj.vertices:
                old = .08 - .36 * np.exp(-((x-.25)/1.5)**2)
                updated.append((x,y,z + float(np.interp(x,xs,zs)) - old))
            obj.vertices = updated
            baseline = np.array(updated)
            for index,frame in enumerate(measurements['frames']):
                edge=np.array(frame['lower'])
                frame_z=np.interp(baseline[:,0],world_x(edge[:,0]),world_z(edge[:,1]))
                base_z=np.interp(baseline[:,0],xs,zs)
                sampled=baseline.copy()
                sampled[:,2]+=frame_z-base_z
                obj.mesh_samples.append(MeshSample(frame=index,vertices=sampled.tolist()))
        if obj.id == 'sculpted_dermis':
            updated = []
            for x,y,z in obj.vertices:
                old_cap = .08 - .36 * np.exp(-((x-.25)/1.5)**2)
                bottom_z = -3.8 + .16 * np.sin(x*2) + .1 * np.cos(x*5)
                influence = np.clip((z-bottom_z)/(old_cap-.34-bottom_z),0,1)
                updated.append((x, y - .013 * np.sin(x*12+z*17), z + influence * (float(np.interp(x,xs,zs))-old_cap+.36)))
            obj.vertices = updated
    wall = next(o for o in shot.objects if o.id == 'sculpted_dermis')
    wall_points=np.array(wall.vertices)
    wall_x=np.unique(wall_points[:,0])
    def front_y(x,z):
        column=wall_points[wall_points[:,0]==wall_x[np.argmin(np.abs(wall_x-x))]]
        order=np.argsort(column[:,2])
        return float(np.interp(z,column[order,2],column[order,1]))
    for obj in shot.objects:
        if obj.id.startswith(('nerve_trace_','vessel_trace_')):
            margin=.025 if obj.id.startswith('nerve') else obj.thickness+.015
            obj.points=[(x,front_y(x,z)-margin,z) for x,y,z in obj.points]
        if obj.id=='hair_follicle_0':
            source_z=world_z(np.array([1020,840,610,300]))
            source_x=world_x(np.array([178,150,124,118]))
            updated=[]
            for x,y,z in obj.vertices:
                new_z=z if z<=-.6 else -.6+(z+.6)*(1.633+.6)/(2.18+.6)
                updated.append((x+float(np.interp(new_z,source_z,source_x))-obj.location[0],y,new_z))
            obj.vertices=updated
        if obj.id in ('follicle_hair_0','follicle_hair_1'):
            pixels=[(178,900),(149,610),(152,320)] if obj.id.endswith('0') else [(178,900),(162,550),(193,310)]
            obj.points=[(float(world_x(x)),-.17,float(world_z(y))) for x,y in pixels]
    for track in measurements['particles']:
        samples = {s['frame']:s for s in track['samples']}
        first = track['samples'][0]
        material_id = f"tracked_pus_{track['id']}"
        plan.materials.append(Material(id=material_id, color=first['color'], unlit=True, emission=1,
            color_samples=[MaterialSample(frame=s['frame'], color=s['color']) for s in track['samples']]))
        keys = []
        for frame in range(COUNT):
            sample = samples.get(frame)
            if sample:
                x,z = float(world_x(sample['x'])), float(world_z(sample['y']))
                rx,rz = sample['rx'] / height * camera.ortho_scale, sample['ry'] / height * camera.ortho_scale
                keys.extend([FrameKey(frame=frame, property='location', value=(x,-1.15,z)),
                             FrameKey(frame=frame, property='scale', value=(rx,rx*.65,rz))])
            else:
                keys.append(FrameKey(frame=frame, property='scale', value=(0,0,0), interpolation='CONSTANT'))
        shot.objects.append(Object(id=f"tracked_particle_{track['id']}", kind='sphere', material=material_id,
                                   location=(float(world_x(first['x'])),-1.15,float(world_z(first['y']))), frame_keys=keys))
    for mat in plan.materials:
        if mat.id == 'hero_blue':
            mat.color, mat.detail_color, mat.pattern, mat.stretch = '#50B1E8','#007FAD','gradient',(1.8,1.1,0)
        elif mat.id == 'hero_pus':
            mat.emission, mat.roughness = .8, .5
    motion = []
    origin = np.array([width/2, height/2 + camera.target[2]/camera.ortho_scale*height, 1])
    for index,frame in enumerate(measurements['frames']):
        affine = np.array(frame['tissue_affine'])
        xy = affine @ origin
        scale = float(np.hypot(affine[0,0],affine[1,0]))
        angle = float(np.degrees(np.arctan2(affine[1,0],affine[0,0])))
        motion.extend([FrameKey(frame=index,property='location',value=(float(world_x(xy[0])),0,float(world_z(xy[1])))),
                       FrameKey(frame=index,property='scale',value=(scale,1,scale)),
                       FrameKey(frame=index,property='rotation',value=(0,angle,0))])
    for obj in shot.objects:
        if obj.id not in ('rounded_inflamed_cap','continuous_skin_underlayer','irregular_epidermal_cells','blue_backdrop') and not obj.id.startswith('tracked_particle_') and not obj.parent:
            obj.parent = 'tracked_tissue'
    shot.objects.append(Object(id='tracked_tissue',kind='empty',frame_keys=motion))
    # White caption ink is separated from warm particles inside the known text band.
    image = images[0].astype(np.float32)
    white = (image.min(axis=2) > 210) & (image.max(axis=2)-image.min(axis=2) < 20)
    roi = np.zeros_like(white)
    roi[round(height*.75):round(height*.83), round(width*.2):round(width*.8)] = True
    count,labels,stats,_ = cv2.connectedComponentsWithStats((white & roi).astype(np.uint8))
    letters = np.zeros_like(white)
    for label in range(1,count):
        x,y,w,h,area = stats[label]
        if 500 <= area <= 2500 and 20 <= w <= 75 and 35 <= h <= 80 and 1460 <= y <= 1500:
            letters |= labels == label
    ys, caption_xs = np.where(letters)
    if len(ys):
        left,right,top,bottom = caption_xs.min(),caption_xs.max(),ys.min(),ys.max()
        plan.captions = [Caption(text='as pus forms',first_frame=0,end_frame=COUNT,
            x=float((left+right)/2/width), y=float((top+bottom)/2/height),
            width=float((right-left+1)/width),height=float((bottom-top+1)/height),stroke=2.5/height)]
    Plan.model_validate(plan.model_dump())
    return plan


def overlays(images, measurements):
    panels = []
    for index in (0,10,20,29):
        im = images[index].copy()
        data = measurements['frames'][index]
        upper = np.c_[np.arange(im.shape[1]), data['upper']].astype(np.int32)
        cv2.polylines(im,[upper],False,(0,255,0),3)
        cv2.polylines(im,[np.array(data['lower'],np.int32)],False,(255,255,0),3)
        for track in measurements['particles']:
            for sample in track['samples']:
                if sample['frame'] == index:
                    center = (round(sample['x']),round(sample['y']))
                    cv2.ellipse(im,center,(max(1,round(sample['rx'])),max(1,round(sample['ry']))),0,0,360,(255,0,255),2)
                    cv2.putText(im,str(track['id']),center,cv2.FONT_HERSHEY_SIMPLEX,.6,(255,255,255),2)
        panels.append(cv2.resize(im,(270,480)))
    cv2.imwrite(str(OUT/'measurements-overlay.png'),np.hstack(panels))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--animate', action='store_true')
    parser.add_argument('--prepare-only', action='store_true')
    args = parser.parse_args()
    OUT.mkdir(parents=True,exist_ok=True)
    images = extract()
    measurements = measure(images)
    overlays(images, measurements)
    plan = build(measurements, images)
    folder = OUT / 'measured'
    folder.mkdir(exist_ok=True)
    (folder/'plan.json').write_text(plan.model_dump_json(),encoding='utf-8')
    meta = dict(duration=COUNT/RATE, width=1080,height=1920,fps=RATE,audio=False)
    (OUT/'meta.json').write_text(json.dumps(meta),encoding='utf-8')
    print('Measured',COUNT,'frames;',len(measurements['particles']),'particle tracks',flush=True)
    if args.prepare_only:
        return
    mode = 'animation' if args.animate else 'preview'
    render(folder,plan,meta,'standard',threading.Event(),mode=mode,times=[0,10/RATE,20/RATE,29/RATE],
           on_progress=lambda done,total:print('Frames',done,'/',total,flush=True))
    print('Rendered', mode, flush=True)


if __name__ == '__main__':
    main()
