"""Explicit opt-in live Astra acceptance check; consumes connected ChatGPT allowance."""
import json
import time
from pathlib import Path
import httpx

root = Path(__file__).resolve().parents[1]
source = root / 'outputs' / 'renderer-check' / 'reference.mp4'
if not source.exists():
    raise SystemExit('Run scripts/renderer_check.py first.')
with httpx.Client(base_url='http://127.0.0.1:4327', timeout=60) as client:
    with source.open('rb') as video:
        response = client.post('/api/jobs', headers={'X-BlendRemake': '1'},
            data=dict(duration='2', start='0', quality='draft', audio='false', review='true',
                      brief='Synthetic reconstruction acceptance test. Match the visible ball, circular plinth, background, lighting and bounce timing. This is a test reference, not a famous creator video.'),
            files={'video': ('Synthetic ball reference.mp4', video, 'video/mp4')})
    response.raise_for_status()
    job = response.json()
    (root/'outputs'/'ai-check-job.json').write_text(json.dumps(job), encoding='utf-8')
    print('Submitted live Astra test:', job['id'], flush=True)
    previous = ''
    deadline = time.monotonic()+2400
    while time.monotonic() < deadline:
        job = client.get('/api/jobs/'+job['id']).json()
        if job['message'] != previous:
            print(job['status'], job['progress'], job['message'], flush=True)
            previous = job['message']
        if job['status'] not in ('running', 'queued'):
            break
        time.sleep(3)
    if job['status'] != 'completed':
        raise SystemExit(json.dumps(job))
    for kind in ('blend', 'video', 'comparison', 'project'):
        response = client.get(f'/api/jobs/{job["id"]}/files/{job["artifacts"][kind]}')
        response.raise_for_status()
        assert len(response.content) > 100
    print('Live Astra reconstruction and all downloads passed.', flush=True)
    print('Inspect visually: http://127.0.0.1:4327/#'+job['id'], flush=True)
