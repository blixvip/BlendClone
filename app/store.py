import json
import re
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path


class Store:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()

    def folder(self, job_id):
        if not re.fullmatch(r'[a-f0-9]{12}', job_id):
            raise ValueError('Invalid project ID')
        path = (self.root / job_id).resolve()
        if not path.is_relative_to(self.root):
            raise ValueError('Invalid project path')
        return path

    def create(self, fields):
        with self.lock:
            job_id = uuid.uuid4().hex[:12]
            self.folder(job_id).mkdir()
            job = dict(fields, id=job_id, created=datetime.now(timezone.utc).isoformat(), status='queued', progress=0, message='Waiting to start', artifacts={}, events=[])
            self._write(job)
            return job

    def _write(self, job):
        path = self.folder(job['id']) / 'job.json'
        temp = path.with_suffix('.tmp')
        temp.write_text(json.dumps(job, indent=2), encoding='utf-8')
        temp.replace(path)

    def get(self, job_id):
        with self.lock:
            return json.loads((self.folder(job_id) / 'job.json').read_text(encoding='utf-8'))

    def update(self, job_id, **fields):
        with self.lock:
            job = self.get(job_id)
            job.update(fields)
            if 'message' in fields:
                job['events'] = (job.get('events', []) + [{'time': datetime.now(timezone.utc).isoformat(), 'message': fields['message']}])[-60:]
            self._write(job)
            return job

    def list(self):
        jobs = []
        for path in self.root.glob('*/job.json'):
            try:
                jobs.append(self.get(path.parent.name))
            except (ValueError, OSError):
                continue
        return sorted(jobs, key=lambda j: j['created'], reverse=True)

    def recover(self):
        for job in self.list():
            if job['status'] in ('queued', 'running'):
                self.update(job['id'], status='interrupted', message='App restarted. Retry this project to continue.')
