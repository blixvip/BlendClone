"""Per-frame reports, difference images, and an interactive pilot review page."""
import json
import re
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from app.fidelity import ciede2000, lab, ssim
from app.fitting import upper_contour
from fit_cutaway import skin_mask

out=ROOT/'outputs/reconstruction-pilot'
folder=Path(json.loads((out/'finished-render.json').read_text())['folder'])
review=folder/'review'
review.mkdir(exist_ok=True)
records=[]
for index in range(30):
    original=cv2.imread(str(out/f'reference/{420+index:04d}.png'))
    rendered=cv2.imread(str(folder/f'frames/frame-{index+1:04d}.png'))
    if original is None or rendered is None:
        raise ValueError(f'Missing frame {index}')
    a,b=[cv2.resize(im,(270,480),interpolation=cv2.INTER_AREA) for im in (original,rendered)]
    rgb_a,rgb_b=[cv2.cvtColor(im,cv2.COLOR_BGR2RGB) for im in (a,b)]
    delta=ciede2000(lab(rgb_a),lab(rgb_b))
    matched=cv2.resize(original,(rendered.shape[1],rendered.shape[0]),interpolation=cv2.INTER_AREA)
    reference_top=upper_contour(skin_mask(matched))
    render_top=upper_contour(skin_mask(rendered))
    error=np.abs(reference_top-render_top)*original.shape[0]/rendered.shape[0]
    records.append(dict(frame=420+index,local_frame=index,time=(420+index)*1001/30000,
        mean_outline_error_px=float(error.mean()),max_outline_error_px=float(error.max()),
        color_delta_e_mean=float(delta.mean()),ssim=ssim(cv2.cvtColor(a,cv2.COLOR_BGR2GRAY),cv2.cvtColor(b,cv2.COLOR_BGR2GRAY))))
    heat=cv2.applyColorMap(np.clip(delta/40*255,0,255).astype(np.uint8),cv2.COLORMAP_INFERNO)
    cv2.imwrite(str(review/f'{index:02d}-source.jpg'),cv2.resize(original,(540,960)),[cv2.IMWRITE_JPEG_QUALITY,95])
    cv2.imwrite(str(review/f'{index:02d}-render.jpg'),cv2.resize(rendered,(540,960)),[cv2.IMWRITE_JPEG_QUALITY,95])
    cv2.imwrite(str(review/f'{index:02d}-heat.jpg'),cv2.resize(heat,(540,960)))
report=dict(status='approximate',visual_acceptance=False,full_clip_complete=False,
    source_frames=[420,449],reference_size=[1080,1920],render_size=[rendered.shape[1],rendered.shape[0]],
    native_resolution=rendered.shape==original.shape,fps_num=30000,fps_den=1001,
    rendered_frames=30,per_frame=records,
    remaining=['Internal anatomy and fine tissue geometry','Material and reflection match','Particle segmentation gaps and merges','Full-video reconstruction and transitions','User visual acceptance'],
    limitations=['Upper-outline measurement does not score the lower boundary or all object silhouettes.',
                 'Color and SSIM are diagnostics, not a calibrated acceptance pass.'])
(folder/'acceptance.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
data=json.dumps(records).replace('<','\\u003c')
html='''<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>BlendClone · Pilot review</title>
<style>body{margin:0;background:#151916;color:#eee;font:16px system-ui}main{max-width:1250px;margin:auto;padding:24px}h1{font-size:26px}p{color:#bac5bc}button,input{font:inherit}button{background:#ef9564;border:0;padding:12px 18px;border-radius:6px;cursor:pointer}#panes{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px}img{width:100%;display:block}figure{margin:0}figcaption{padding:10px 0}#controls{display:flex;gap:12px;align-items:center;flex-wrap:wrap;margin:18px 0}input{flex:1;min-width:200px}#stats{font-variant-numeric:tabular-nums}strong{color:#ffb487}@media(max-width:650px){main{padding:12px}#panes{grid-template-columns:repeat(2,minmax(0,1fr))}figure:last-child{grid-column:1/-1;max-width:50%}}</style>
<main><h1>BlendClone · 30-frame reconstruction pilot</h1><p><strong>Approximate — visual acceptance pending.</strong> Source frames 420–449. Full-video reconstruction remains incomplete.</p>
<div id="controls"><button id="play">Play</button><button id="back">← Frame</button><button id="next">Frame →</button><button id="flip">Flicker comparison</button><label>Speed <select id="speed"><option value="1">1×</option><option value="0.25">0.25×</option></select></label><input aria-label="Frame" id="seek" type="range" min="0" max="29" value="0"></div>
<p id="stats"></p><div id="panes"><figure><figcaption>Original</figcaption><img id="source" alt="Original frame"></figure><figure><figcaption>Reconstruction / flicker</figcaption><img id="render" alt="Reconstructed frame"></figure><figure><figcaption>Color difference · brighter = larger</figcaption><img id="heat" alt="Color difference heatmap"></figure></div>
<p>Outline error measures the upper skin boundary only. Color difference is diagnostic. Neither establishes a 1:1 match.</p></main>
<script>const records=DATA;let index=0,playing=false,flicker=false,phase=false;const $=id=>document.getElementById(id);function draw(){const p=String(index).padStart(2,'0');$('source').src=p+'-source.jpg';$('render').src=p+(flicker&&phase?'-source.jpg':'-render.jpg');$('heat').src=p+'-heat.jpg';$('seek').value=index;const r=records[index];$('stats').textContent=`Frame ${r.frame} · ${r.time.toFixed(3)} s · upper-outline mean ${r.mean_outline_error_px.toFixed(2)} px · max ${r.max_outline_error_px.toFixed(2)} px · color ΔE ${r.color_delta_e_mean.toFixed(2)}`;}let previous=performance.now(),flick=previous;function tick(now){if(playing&&now-previous>=1001/30/Number($('speed').value)){const steps=Math.floor((now-previous)/(1001/30/Number($('speed').value)));index=(index+steps)%30;previous+=steps*(1001/30/Number($('speed').value));draw()}if(flicker&&now-flick>250){phase=!phase;flick=now;draw()}requestAnimationFrame(tick)}$('play').onclick=()=>{playing=!playing;$('play').textContent=playing?'Pause':'Play';previous=performance.now()};$('flip').onclick=()=>{flicker=!flicker;$('flip').textContent=flicker?'Stop flicker':'Flicker comparison';draw()};$('seek').oninput=e=>{index=Number(e.target.value);draw()};$('back').onclick=()=>{index=Math.max(0,index-1);draw()};$('next').onclick=()=>{index=Math.min(29,index+1);draw()};draw();requestAnimationFrame(tick);</script>'''.replace('DATA',data)
style = re.search(r'<style>(.*?)</style>',html,re.S).group(1)
script = re.search(r'<script>(.*?)</script>',html,re.S).group(1)
html = re.sub(r'<style>.*?</style>','<link rel="stylesheet" href="review.css">',html,flags=re.S)
html = re.sub(r'<script>.*?</script>','<script src="review.js" defer></script>',html,flags=re.S)
(review/'review.css').write_text(style,encoding='utf-8')
(review/'review.js').write_text(script,encoding='utf-8')
(review/'index.html').write_text(html,encoding='utf-8')
print(json.dumps(dict(mean_outline_error_px=float(np.mean([r['mean_outline_error_px'] for r in records])),
                     worst_outline_error_px=max(r['max_outline_error_px'] for r in records),
                     mean_color_delta_e=float(np.mean([r['color_delta_e_mean'] for r in records])),review=str(review/'index.html'))))
