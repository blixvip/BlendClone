"""Own one hidden persistent Blender process and exchange validated render requests."""
import json
import os
import subprocess
import time
import uuid
from pathlib import Path

from .models import Plan
from .process import Cancelled
from .render import ROOT, blender_binary


class BlenderWorker:
    def __init__(self, blend, folder, cancel):
        self.folder = Path(folder).resolve() / uuid.uuid4().hex[:12]
        self.folder.mkdir(parents=True, exist_ok=True)
        self.cancel = cancel
        self.index = 0
        self.log = (self.folder / 'worker.log').open('wb')
        self.process = subprocess.Popen([blender_binary(), '--background', '--factory-startup', str(Path(blend).resolve()),
            '--disable-autoexec', '--python-exit-code', '1', '--python', str(ROOT / 'app/blender_worker.py'), '--', str(self.folder)],
            stdin=subprocess.PIPE, stdout=self.log, stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)

    def render(self, plan, frame=0, size=(270, 480), samples=12, timeout=300):
        plan = Plan.model_validate(plan.model_dump())
        if type(frame) is not int or not 0 <= frame < (plan.timeline.frame_count if plan.timeline else 14400):
            raise ValueError('Frame outside timeline')
        if len(size) != 2 or any(type(v) is not int or not 2 <= v <= 8192 for v in size):
            raise ValueError('Invalid render dimensions')
        if type(samples) is not int or not 1 <= samples <= 512:
            raise ValueError('Invalid sample count')
        self.index += 1
        result = self.folder / f'{self.index:06d}.json'
        used_materials = {o.material for shot in plan.shots for o in shot.objects if o.material}
        used_materials.update(name for shot in plan.shots for o in shot.objects for name in o.face_materials)
        request = dict(id=self.index, frame=frame, size=size, samples=samples,
                       materials=[m.model_dump() for m in plan.materials if m.id in used_materials], lights=[s.model_dump() for s in plan.shots[0].lights])
        self.process.stdin.write((json.dumps(request) + '\n').encode())
        self.process.stdin.flush()
        start = time.monotonic()
        while not result.exists():
            if self.cancel.is_set():
                raise Cancelled()
            if self.process.poll() is not None:
                raise RuntimeError('Blender worker exited; check worker.log')
            if time.monotonic() - start > timeout:
                raise TimeoutError('Blender worker render timed out')
            time.sleep(.1)
        payload = json.loads(result.read_text(encoding='utf-8'))
        if not payload['ok']:
            raise ValueError(payload['error'])
        return self.folder / payload['image']

    def close(self):
        if self.process.stdin and not self.process.stdin.closed:
            self.process.stdin.close()
        try:
            self.process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.process.terminate()  # Only the exact child created by this instance.
            self.process.wait(timeout=10)
        finally:
            self.log.close()

    def __enter__(self):
        return self

    def __exit__(self, *error):
        self.close()
