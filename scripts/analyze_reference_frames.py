"""Inspect every decoded source frame; preserve timestamps, cuts and motion evidence."""
import json
import math
import sys
from pathlib import Path
import cv2
import numpy as np
from PIL import Image,ImageDraw

ROOT=Path(__file__).resolve().parents[1]
source=ROOT/'data/references/splinter/source.mp4'
out=ROOT/'data/references/splinter/frame-audit'
out.mkdir(parents=True,exist_ok=True)
(out/'frames').mkdir(exist_ok=True)
cap=cv2.VideoCapture(str(source));fps=cap.get(cv2.CAP_PROP_FPS)
records=[];tiles=[];previous=None;previous_gray=None;index=0
while True:
    ok,frame=cap.read()
    if not ok:break
    timestamp=cap.get(cv2.CAP_PROP_POS_MSEC)/1000
    cv2.imwrite(str(out/'frames'/f'{index:04d}.jpg'),frame,[cv2.IMWRITE_JPEG_QUALITY,94])
    small=cv2.resize(frame,(180,320));gray=cv2.cvtColor(small,cv2.COLOR_BGR2GRAY)
    change=0.;flow_mean=0.;flow_peak=0.
    if previous is not None:
        change=float(np.abs(small.astype(float)-previous).mean())
        flow=cv2.calcOpticalFlowFarneback(previous_gray,gray,None,.5,3,15,3,5,1.2,0)
        magnitude=np.linalg.norm(flow,axis=2);flow_mean=float(magnitude.mean());flow_peak=float(np.percentile(magnitude,95))
    records.append(dict(frame=index,time=timestamp,mean_pixel_change=change,motion_mean=flow_mean,motion_p95=flow_peak))
    tile=Image.new('RGB',(180,344),'#111111');tile.paste(Image.fromarray(cv2.cvtColor(small,cv2.COLOR_BGR2RGB)),(0,24))
    ImageDraw.Draw(tile).text((5,5),f'{index:04d}  {timestamp:.3f}s',fill='white');tiles.append(tile)
    if len(tiles)==30:
        sheet=Image.new('RGB',(1080,1720),'#111111')
        for i,tile in enumerate(tiles):sheet.paste(tile,((i%6)*180,(i//6)*344))
        sheet.save(out/f'second-{index//30:02d}.jpg',quality=94);tiles=[]
    previous=small.astype(float);previous_gray=gray;index+=1
cap.release()
if tiles:
    sheet=Image.new('RGB',(1080,math.ceil(len(tiles)/6)*344),'#111111')
    for i,tile in enumerate(tiles):sheet.paste(tile,((i%6)*180,(i//6)*344))
    sheet.save(out/f'second-{(index-1)//30:02d}.jpg',quality=94)
report=dict(source=str(source),fps=fps,total_frames=index,frames=records,strong_changes=sorted(records,key=lambda x:x['mean_pixel_change'],reverse=True)[:30])
(out/'analysis.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in report.items() if k!='frames'},indent=2))
