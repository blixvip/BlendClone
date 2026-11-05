"""Read-only browser verification of the real pilot and its evidence page."""
import json
import re
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'outputs/reconstruction-pilot'
job=json.loads((OUT/'published-job.json').read_text())['id']
errors=[]
with sync_playwright() as p:
    browser=p.chromium.launch(channel='chrome',headless=True)
    for name,width,height in [('desktop',1440,1000),('mobile',390,844)]:
        page=browser.new_page(viewport=dict(width=width,height=height))
        page.on('pageerror',lambda error:errors.append(str(error)))
        page.goto(f'http://127.0.0.1:4331/#{job}',wait_until='networkidle')
        expect(page.locator('#benchmark-status')).to_contain_text('30 pilot frames rendered')
        expect(page.locator('#benchmark-status')).to_contain_text('visual acceptance pending')
        expect(page.get_by_role('link',name='Download .blend')).to_be_visible()
        assert page.locator('body').evaluate('(el)=>el.scrollWidth<=innerWidth')
        page.screenshot(path=str(OUT/f'app-{name}.png'),full_page=True)
        review=page.locator('#benchmark-link').get_attribute('href')
        page.goto('http://127.0.0.1:4331'+review,wait_until='networkidle')
        expect(page.locator('#source')).to_have_js_property('naturalWidth',540)
        expect(page.locator('#render')).to_have_js_property('naturalWidth',540)
        expect(page.locator('#stats')).to_contain_text('Frame 420')
        page.locator('#seek').focus()
        page.locator('#seek').press('End')
        expect(page.locator('#stats')).to_contain_text('Frame 449')
        page.get_by_role('button',name='← Frame',exact=True).click()
        expect(page.locator('#stats')).to_contain_text('Frame 448')
        page.get_by_role('button',name='Flicker comparison',exact=True).click()
        expect(page.locator('#render')).to_have_attribute('src',re.compile(r'-source\.jpg$'))
        page.get_by_role('button',name='Stop flicker',exact=True).click()
        page.locator('#speed').select_option('0.25')
        assert page.locator('body').evaluate('(el)=>el.scrollWidth<=innerWidth')
        page.screenshot(path=str(OUT/f'review-{name}.png'),full_page=True)
        page.close()
    browser.close()
assert not errors,errors
print('Actual pilot, frame seeking, flicker, quarter speed, assets, desktop/mobile layout verified.')
