"""Exercise the real local UI; mock only job/auth HTTP boundaries when necessary."""
from pathlib import Path
import json
import subprocess
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'outputs'


def main():
    OUT.mkdir(exist_ok=True)
    errors = []
    with sync_playwright() as p:
        browser = p.chromium.launch(channel='chrome', headless=True)
        for name, width, height in [('desktop', 1440, 1000), ('mobile', 390, 844), ('small-mobile', 320, 800), ('tablet', 768, 1000), ('small-desktop', 1024, 900)]:
            page = browser.new_page(viewport={'width': width, 'height': height})
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.goto('http://127.0.0.1:4328/', wait_until='networkidle')
            page.get_by_role('heading', name='Rebuild a video in Blender.').wait_for()
            assert page.locator('body').evaluate('(el) => el.scrollWidth <= innerWidth')
            assert page.get_by_label('Reference video URL').is_visible()
            assert page.get_by_label('Keep reference audio').is_visible()
            page.get_by_role('button', name='Rebuild in Blender').click()
            page.get_by_role('alert').filter(has_text='Add a reference').wait_for()
            page.get_by_label('Reference video URL').fill('https://youtube.com/watch?v=example')
            page.locator('#video').set_input_files({'name': 'reference.mp4', 'mimeType': 'video/mp4', 'buffer': b'UI upload test'})
            assert page.get_by_label('Reference video URL').input_value() == ''
            page.get_by_role('button', name='Remove selected file').click()
            page.locator('#error').evaluate('(el) => { el.hidden = true; }')
            page.screenshot(path=str(OUT / f'{name}.png'), full_page=True)
            page.close()
        # Mock only HTTP boundaries to verify states and actions without starting more AI jobs.
        fixture = OUT / 'browser-fixture.mp4'
        subprocess.run(['ffmpeg', '-y', '-v', 'error', '-f', 'lavfi', '-i', 'color=c=0x324038:s=320x240:r=24:d=2', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', str(fixture)], check=True, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        job = dict(id='ffffffffffff', title='UI state fixture', created='2026-09-11T20:00:00Z', status='running', progress=40, message='Blender is building preview frames', artifacts={}, meta={'duration': 2}, summary='HTTP fixture for interface verification.', shots=[], limitations=[])
        page = browser.new_page(viewport={'width': 1440, 'height': 1000})
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.route('**/api/jobs/ffffffffffff', lambda route: route.fulfill(json=job))
        def serve_video(route):
            payload = fixture.read_bytes()
            header = route.request.headers.get('range')
            if header:
                first, last = header.removeprefix('bytes=').split('-', 1)
                start, end = int(first or 0), int(last) if last else len(payload)-1
                route.fulfill(status=206, body=payload[start:end+1], content_type='video/mp4',
                    headers={'Accept-Ranges': 'bytes', 'Content-Range': f'bytes {start}-{end}/{len(payload)}'})
            else:
                route.fulfill(body=payload, content_type='video/mp4', headers={'Accept-Ranges': 'bytes'})
        page.route('**/api/jobs/ffffffffffff/files/**', serve_video)
        page.goto('http://127.0.0.1:4328/#ffffffffffff', wait_until='networkidle')
        page.get_by_role('button', name='Cancel job').wait_for()
        page.screenshot(path=str(OUT / 'loading.png'), full_page=True)
        job.update(status='failed', message='Test failure: reference could not be read.')
        page.get_by_role('button', name='Retry project').wait_for()
        page.screenshot(path=str(OUT / 'error.png'), full_page=True)
        def retry(route):
            job.update(status='queued', message='Queued for Blender')
            route.fulfill(json=job)
        page.route('**/api/jobs/ffffffffffff/retry', retry)
        page.get_by_role('button', name='Retry project').click()
        page.get_by_role('button', name='Cancel job').wait_for()
        job.update(status='completed', progress=100, artifacts={'reference': 'reference.mp4', 'video': 'remake.mp4', 'blend': 'remake.blend', 'project': 'project.zip', 'comparison': 'comparison.mp4'})
        page.get_by_role('link', name='Download .blend').wait_for()
        expect(page.locator('#reference-video')).to_have_js_property('readyState', 4)
        expect(page.locator('#remake-video')).to_have_js_property('readyState', 4)
        page.get_by_role('button', name='Play comparison').click()
        page.wait_for_timeout(400)
        assert page.locator('#reference-video').evaluate('el => el.currentTime') > .15
        page.get_by_role('button', name='Pause comparison').click()
        times = page.evaluate("['reference-video','remake-video'].map(id => document.getElementById(id).currentTime)")
        assert abs(times[0] - times[1]) < .2, times
        page.get_by_label('Playback position').evaluate("el => { el.value = '1.2'; el.dispatchEvent(new Event('input', {bubbles:true})); }")
        seek_time = page.locator('#reference-video').evaluate('el => el.currentTime')
        assert abs(seek_time - 1.2) < .1, seek_time
        page.get_by_role('button', name='Remake only', exact=True).click()
        assert not page.locator('#reference-pane').is_visible()
        page.get_by_role('button', name='Compare', exact=True).click()
        page.screenshot(path=str(OUT / 'success.png'), full_page=True)
        page.set_viewport_size({'width': 390, 'height': 844})
        assert page.locator('body').evaluate('(el) => el.scrollWidth <= innerWidth')
        page.screenshot(path=str(OUT / 'success-mobile.png'), full_page=True)
        page.get_by_label('Refine this remake').fill('Make the object taller')
        page.route('**/api/jobs/ffffffffffff/revise', retry)
        page.get_by_role('button', name='Revise & render').click()
        page.get_by_role('button', name='Cancel job').wait_for()
        page.close()
        browser.close()
    assert not errors, errors
    print('Five responsive widths, import controls, loading/error/success, retry, synchronized playback, and revision passed; screenshots in outputs/.')


if __name__ == '__main__':
    main()
