import json
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from app.benchmark import source_manifest

boundaries=[0,37,146,162,217,249,310,364,390,492,666,708,830,886,910]
names=['Wood contact and recoil','Finger close-up and extraction','Card flip','Embedded shard cutaway',
       'Cutaway to surface','Unreachable shard','Swelling','Opening cutaway','Swollen tissue and particles',
       'Pressure and shard rise','Return to surface','Recovery and emergence','Final extraction','Final hold']
segments=[dict(id=i,first=a,end=b,name=name,status='unmatched') for i,(a,b,name) in enumerate(zip(boundaries,boundaries[1:],names))]
manifest=source_manifest(ROOT/'data/references/splinter/source.mp4',segments)
folder=ROOT/'outputs/reconstruction-pilot'
folder.mkdir(parents=True,exist_ok=True)
(folder/'source-manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
print(json.dumps({k:manifest[k] for k in ('source_sha256','width','height','fps_num','fps_den','frame_count')}))
