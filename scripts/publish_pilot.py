"""Add the completed experimental pilot and its review evidence to the local library."""
import json
import shutil
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from app.models import Plan
from app.pipeline import Pipeline
from app.store import Store

out=ROOT/'outputs/reconstruction-pilot'
finished=Path(json.loads((out/'finished-render.json').read_text())['folder'])
report=json.loads((finished/'acceptance.json').read_text())
plan=Plan.model_validate_json((finished/'plan.json').read_text(encoding='utf-8'))
store=Store(ROOT/'data/projects')
job=store.create(dict(title=plan.title,url='',brief='Continue the measured reconstruction; retain geometry and tracked animation.',
    original_brief='Visually indistinguishable reconstruction of the complete splinter video.',
    start=420*1001/30000,duration=30*1001/30000,quality='standard',audio=False,review=True,preview_first=True))
folder=store.folder(job['id'])
attempt=Pipeline.attempt(folder)
shutil.copy2(ROOT/'data/references/splinter/source.mp4',folder/'source.bin')
shutil.copy2(finished/'reference.mp4',folder/'reference.mp4')
shutil.copy2(finished/'plan.json',folder/'plan.json')
artifacts=dict(reference='reference.mp4')
for key,name in [('blend','remake.blend'),('video','remake.mp4'),('comparison','comparison.mp4'),('project','project.zip'),
                 ('plan','plan.json'),('acceptance','acceptance.json'),('native_verification','native-verification.json')]:
    shutil.copy2(finished/name,attempt/name)
    artifacts[key]=(attempt/name).relative_to(folder).as_posix()
shutil.copytree(finished/'review',attempt/'review')
for index,path in enumerate(sorted((attempt/'review').iterdir())):
    artifacts['review' if path.name=='index.html' else f'review_asset_{index}']=path.relative_to(folder).as_posix()
artifacts['poster']=(attempt/'review/00-render.jpg').relative_to(folder).as_posix()
meta=json.loads((out/'meta.json').read_text())
store.update(job['id'],status='completed',progress=100,message='Pilot rendered. Fidelity remains approximate; full-video reconstruction incomplete.',
    meta=meta,artifacts=artifacts,benchmark=dict(rendered_frames=30,source_first_frame=420,source_end_frame=450,
    visual_acceptance=False,full_clip_complete=False,render_size=report['render_size']),**Pipeline.plan_fields(plan))
(out/'published-job.json').write_text(json.dumps(dict(id=job['id'])),encoding='utf-8')
print('http://127.0.0.1:4331/#'+job['id'])
