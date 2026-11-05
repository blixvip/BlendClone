"""Verify a completed project's portable export in a separate directory."""
import json
import os
import sys
import uuid
import zipfile
from pathlib import Path
from playwright.sync_api import sync_playwright, expect
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.render import blender_binary
from app.process import run
from app.store import Store

root = Path(__file__).resolve().parents[1]
job_id = sys.argv[1]
store = Store(root / 'data' / 'projects')
job = store.get(job_id)
assert job['status'] == 'completed'
folder = store.folder(job_id)
out = root / 'outputs' / ('export-check-' + uuid.uuid4().hex[:8])
out.mkdir(parents=True)
artifact=job.get('artifacts',{}).get('project','project.zip')
with zipfile.ZipFile(folder / artifact) as archive:
    assert not any('source' in name or 'reference' in name or '.log' in name for name in archive.namelist())
    for entry in archive.infolist():
        assert (out / entry.filename).resolve().is_relative_to(out.resolve())
        archive.extract(entry, out)
config = json.loads((out / 'animation.config.json').read_text())
config.update(mode='preview', times=[min(14.5, job['meta']['duration']/2)])
(out / 'verify.config.json').write_text(json.dumps(config), encoding='utf-8')
run([blender_binary(), '--background', '--factory-startup', '--disable-autoexec', '--python-exit-code', '1',
     '--python', out / 'rebuild.py', '--', out / 'verify.config.json'], cwd=out, timeout=300, log=out / 'compile.log')
assert (out / 'previews' / '000.png').is_file()
run([blender_binary(), '--background', '--disable-autoexec', out / 'remake.blend', '--python-exit-code', '1', '--python-expr',
     'import bpy; s=bpy.context.scene; assert len(s.objects)>0; assert s.camera; assert s.frame_end>1; assert any(o.animation_data for o in s.objects); print("BLEND REOPEN PASSED")'], cwd=out, timeout=60, log=out / 'reopen.log')
if job.get('benchmark'):
    run([blender_binary(), '--background', '--factory-startup', out / 'remake.blend', '--disable-autoexec',
         '--python-exit-code','1','--python',root/'scripts/verify_pilot.py','--',out],cwd=out,timeout=120,log=out/'native-verification.log')
with sync_playwright() as p:
    browser = p.chromium.launch(channel='chrome', headless=True)
    page = browser.new_page(viewport={'width': 1440, 'height': 1100})
    page.goto(os.environ.get('BLENDCLONE_URL','http://127.0.0.1:4331')+'/#'+job_id, wait_until='networkidle')
    page.get_by_role('link', name='Download .blend').wait_for()
    expect(page.locator('#reference-video')).to_have_js_property('readyState', 4)
    expect(page.locator('#remake-video')).to_have_js_property('readyState', 4)
    page.get_by_label('Playback position').evaluate("(el,time) => { el.value = time; el.dispatchEvent(new Event('input', {bubbles:true})); }",min(14.5,job['meta']['duration']/2))
    page.wait_for_timeout(400)
    page.screenshot(path=str(root / 'outputs' / 'actual-reference-comparison.png'), full_page=True)
    page.set_viewport_size({'width': 390, 'height': 844})
    assert page.locator('body').evaluate('(el) => el.scrollWidth <= innerWidth')
    page.screenshot(path=str(root / 'outputs' / 'actual-reference-mobile.png'), full_page=True)
    browser.close()
print('Portable scene recompiled, .blend reopened, actual reference comparison captured.')
print(out)
