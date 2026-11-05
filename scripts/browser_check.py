"""Exercise the real local UI; mock only job/auth HTTP boundaries when necessary."""
from pathlib import Path
import json
import os
import subprocess
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'outputs'
BASE_URL = os.environ.get('BLENDCLONE_URL', 'http://127.0.0.1:4331')


def main():
    OUT.mkdir(exist_ok=True)
    errors = []
    with sync_playwright() as p:
        browser = p.chromium.launch(channel='chrome', headless=True)
        for name, width, height in [('desktop', 1440, 1000), ('mobile', 390, 844), ('small-mobile', 320, 800), ('tablet', 768, 1000), ('small-desktop', 1024, 900)]:
            page = browser.new_page(viewport={'width': width, 'height': height})
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.goto(BASE_URL + '/', wait_until='networkidle')
            page.get_by_role('heading', name='Rebuild a video in Blender.').wait_for()
            assert page.locator('body').evaluate('(el) => el.scrollWidth <= innerWidth')
            assert page.get_by_label('Reference video URL').is_visible()
            assert page.get_by_label('Keep reference audio').is_visible()
            expect(page.get_by_label('Preview before final render')).to_be_checked()
            page.get_by_label('Final render quality', exact=True).select_option('final')
            page.get_by_role('button', name='Build preview').click()
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
        still = OUT / 'browser-fixture.png'
        subprocess.run(['ffmpeg', '-y', '-v', 'error', '-i', str(fixture), '-frames:v', '1', str(still)], check=True, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        job = dict(id='ffffffffffff', title='UI state fixture', created='2026-09-11T20:00:00Z', status='running', progress=40, message='Blender is building preview frames', quality='draft', preview_first=True, artifacts={}, meta={'duration': 2, 'fps': 29.97}, summary='HTTP fixture for interface verification.', shots=[], limitations=[])
        revisions, renders = [], []
        page = browser.new_page(viewport={'width': 1440, 'height': 1000})
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.route('**/api/jobs/ffffffffffff', lambda route: route.fulfill(json=job))
        def serve_video(route):
            if route.request.url.endswith('.png'):
                return route.fulfill(body=still.read_bytes(), content_type='image/png')
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
        page.goto(BASE_URL + '/#ffffffffffff', wait_until='networkidle')
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
        def preview():
            job.update(status='preview', progress=60, message='Preview ready',
                preview_frames=[{'time': .25, 'source': 'sources/000.png', 'render': 'previews/000.png'}, {'time': 1.5, 'source': 'sources/001.png', 'render': 'previews/001.png'}],
                artifacts={'reference': 'reference.mp4', 'blend': 'remake.blend', 'preview_source_0': 'sources/000.png', 'preview_render_0': 'previews/000.png', 'preview_source_1': 'sources/001.png', 'preview_render_1': 'previews/001.png'},
                analysis={'frames': 60, 'sheets': 2, 'reviewed_batches': 1, 'total_batches': 2, 'visual_review': 'pending'})
        preview()
        page.get_by_role('button', name='Render full video').wait_for()
        expect(page.locator('#analysis-machine')).to_have_text('60 frames scanned · 2 contact sheets')
        expect(page.locator('#analysis-visual')).to_contain_text('1 of 2 sheet batches · visual review pending')
        expect(page.locator('#previous-preview')).to_be_disabled()
        expect(page.locator('#reference-still')).to_have_js_property('naturalWidth', 320)
        expect(page.locator('#remake-still')).to_have_js_property('naturalWidth', 320)
        expect(page.locator('#video-transport')).to_be_hidden()
        expect(page.locator('#retry')).to_be_hidden()
        expect(page.get_by_role('link', name='Remake MP4')).to_be_hidden()
        page.get_by_role('button', name='Next preview', exact=True).click()
        expect(page.locator('#preview-time')).to_have_text('0:01.500')
        expect(page.locator('#next-preview')).to_be_disabled()
        page.get_by_role('button', name='Use this time').click()
        expect(page.get_by_label('Refine this remake')).to_have_value('At 0:01.500, ')
        for name, width, height in [('desktop', 1440, 1000), ('mobile', 390, 844), ('small-mobile', 320, 800), ('tablet', 768, 1000), ('small-desktop', 1024, 900)]:
            page.set_viewport_size({'width': width, 'height': height})
            assert page.locator('body').evaluate('(el) => el.scrollWidth <= innerWidth'), name
            assert page.get_by_role('button', name='Render full video').is_visible()
            page.screenshot(path=str(OUT / f'preview-{name}.png'), full_page=True)
        page.set_viewport_size({'width': 1440, 'height': 1000})
        def revise(route):
            revisions.append(route.request.post_data_json)
            job.update(status='queued', message='Queued for revision')
            route.fulfill(json=job)
        page.route('**/api/jobs/ffffffffffff/revise', revise)
        page.get_by_label('Refine this remake').fill('At 0:01.500, make the object taller')
        page.get_by_role('button', name='Revise preview').click()
        page.get_by_role('button', name='Cancel job').wait_for()
        assert revisions == [{'brief': 'At 0:01.500, make the object taller'}]
        preview()
        job['analysis'].update(reviewed_batches=2, visual_review='complete')
        page.get_by_role('button', name='Render full video').wait_for()
        expect(page.locator('#analysis-visual')).to_contain_text('2 of 2 sheet batches · visual review complete')
        def render(route):
            renders.append(route.request.post_data_json)
            job.update(status='queued', message='Queued for final rendering')
            route.fulfill(json=job)
        page.route('**/api/jobs/ffffffffffff/render', render)
        page.get_by_label('Full video render quality').select_option('final')
        page.get_by_role('button', name='Render full video').click()
        page.get_by_role('button', name='Cancel job').wait_for()
        assert renders == [{'quality': 'final'}]
        job.update(status='completed', progress=100, artifacts={'reference': 'reference.mp4', 'video': 'remake.mp4', 'blend': 'remake.blend', 'project': 'project.zip', 'comparison': 'comparison.mp4'})
        page.get_by_role('link', name='Download .blend').wait_for()
        expect(page.locator('#preview-transport')).to_be_hidden()
        expect(page.locator('#video-transport')).to_be_visible()
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
        page.get_by_role('button', name='Next video frame').click()
        step_time = page.locator('#reference-video').evaluate('el => el.currentTime')
        assert abs(step_time - 37 / 29.97) < .002, step_time
        page.get_by_role('button', name='Previous video frame').click()
        step_time = page.locator('#reference-video').evaluate('el => el.currentTime')
        assert abs(step_time - 36 / 29.97) < .002, step_time
        page.get_by_role('button', name='Use this time').click()
        expect(page.get_by_label('Refine this remake')).to_have_value('At 0:01.201, ')
        page.get_by_role('button', name='Remake only', exact=True).click()
        assert not page.locator('#reference-pane').is_visible()
        page.get_by_role('button', name='Compare', exact=True).click()
        page.screenshot(path=str(OUT / 'success.png'), full_page=True)
        page.set_viewport_size({'width': 390, 'height': 844})
        assert page.locator('body').evaluate('(el) => el.scrollWidth <= innerWidth')
        page.screenshot(path=str(OUT / 'success-mobile.png'), full_page=True)
        page.get_by_label('Refine this remake').fill('Make the object taller')
        page.get_by_role('button', name='Revise preview').click()
        page.get_by_role('button', name='Cancel job').wait_for()
        assert revisions[-1] == {'brief': 'Make the object taller'}
        page.close()
        browser.close()
    assert not errors, errors
    print('Five responsive widths; import, loading/error/preview/success, retry, preview corrections, reference-resolution render request, coverage, synchronized playback, actual-fps frame stepping, and revision passed; screenshots in outputs/.')


if __name__ == '__main__':
    main()
