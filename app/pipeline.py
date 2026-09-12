import json
import threading
import traceback
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from . import ai, media, render
from .models import Plan
from .process import Cancelled


class Pipeline:
    def __init__(self, store):
        self.store = store
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='blendremake')
        self.tokens = {}
        self.lock = threading.RLock()

    def submit(self, job_id, *, revise=False):
        with self.lock:
            if job_id in self.tokens:
                raise ValueError('This project is already running.')
            token = threading.Event()
            self.tokens[job_id] = token
            self.store.update(job_id, status='queued', progress=0, message='Queued for Blender', artifacts={})
            self.executor.submit(self.work, job_id, token, revise)

    def cancel(self, job_id):
        with self.lock:
            token = self.tokens.get(job_id)
            if token:
                token.set()

    def shutdown(self):
        with self.lock:
            for token in self.tokens.values():
                token.set()
        self.executor.shutdown(wait=True, cancel_futures=False)

    def work(self, job_id, cancel, revise):
        store = self.store
        folder = store.folder(job_id)
        def progress(message, value, **fields):
            if cancel.is_set():
                raise Cancelled()
            store.update(job_id, status='running', message=message, progress=value, **fields)
        try:
            job = store.get(job_id)
            source = folder / 'source.bin'
            progress('Preparing your reference', 3)
            if not source.exists():
                media.download(job['url'], source, cancel)
            if not (folder / 'reference.mp4').exists():
                meta = media.prepare(source, folder, job['start'], job['duration'], cancel)
            else:
                meta = media.probe(folder / 'reference.mp4')
            times = media.timestamps(folder / 'reference.mp4', meta['duration'])
            images = media.sheets(folder / 'reference.mp4', folder, 'SOURCE', times)
            progress('Astra is reconstructing the scene', 15, meta=meta, artifacts={'reference': 'reference.mp4'})
            plan = None
            if (folder / 'plan.json').exists():
                plan = Plan.model_validate_json((folder / 'plan.json').read_text(encoding='utf-8'))
            if plan is None or revise:
                plan = ai.generate(folder, meta, images, job.get('brief', ''), cancel, previous=plan)
            (folder / 'plan.json').write_text(plan.model_dump_json(indent=2), encoding='utf-8')
            review_times = sorted(set(round(min(meta['duration']-1/24, shot.start + (shot.end-shot.start)*fraction), 4) for shot in plan.shots for fraction in (.12, .5, .88)))[:24]
            progress('Blender is building preview frames', 40, title=plan.title, summary=plan.summary, limitations=plan.limitations, shots=[dict(name=s.name, start=s.start, end=s.end, description=s.description, objects=len(s.objects)) for s in plan.shots])
            try:
                previews = render.render(folder, plan, meta, job['quality'], cancel, times=review_times)
            except (ValueError, RuntimeError) as error:
                progress('Repairing a Blender scene error', 42)
                plan = ai.generate(folder, meta, images, job.get('brief', ''), cancel, previous=plan, error=error)
                previews = render.render(folder, plan, meta, job['quality'], cancel, times=review_times)
            if job.get('review', True):
                progress('Astra is comparing the render with your reference', 55)
                source_review = media.sheets(folder / 'reference.mp4', folder, 'SOURCE-review', review_times)
                rendered = media.rendered_sheets(previews, folder, review_times)
                previous = plan
                try:
                    improved = ai.generate(folder, meta, source_review + rendered, job.get('brief', ''), cancel, previous=plan, review=True)
                    previews = render.render(folder, improved, meta, job['quality'], cancel, times=review_times)
                    plan = improved
                except (ValueError, RuntimeError, TimeoutError):
                    (folder / 'review-error.log').write_text(traceback.format_exc(), encoding='utf-8')
                    plan = previous
                    plan.limitations.append('Automatic review did not finish; the initial validated reconstruction was retained.')
                    previews = render.render(folder, plan, meta, job['quality'], cancel, times=review_times)
            progress('Rendering the complete animation', 70, title=plan.title, summary=plan.summary, limitations=plan.limitations,
                shots=[dict(name=s.name, start=s.start, end=s.end, description=s.description, objects=len(s.objects)) for s in plan.shots])
            render.render(folder, plan, meta, job['quality'], cancel, mode='animation')
            progress('Preparing video and Blender downloads', 94)
            render.encode(folder, meta['duration'], job.get('audio', True) and meta['audio'], cancel)
            self.package(folder, plan)
            artifacts = dict(reference='reference.mp4', video='remake.mp4', blend='remake.blend', comparison='comparison.mp4', project='project.zip', plan='plan.json', poster='previews/000.png')
            store.update(job_id, status='completed', progress=100, message='Remake ready. Compare it with your reference.', artifacts=artifacts)
        except Cancelled:
            store.update(job_id, status='cancelled', message='Cancelled. Saved work is available for retry.')
        except Exception as error:
            (folder / 'error.log').write_text(traceback.format_exc(), encoding='utf-8')
            message = str(error) if isinstance(error, (ValueError, TimeoutError)) else 'This step failed. Check the project error log, then retry.'
            if any(word in str(error).lower() for word in ('usage limit', 'rate_limit', 'usage_limit', 'quota')):
                message = 'ChatGPT usage limit reached. Wait for your allowance to reset, then retry.'
            store.update(job_id, status='failed', message=message[:800])
        finally:
            with self.lock:
                self.tokens.pop(job_id, None)

    @staticmethod
    def package(folder, plan):
        readme = folder / 'PROJECT.md'
        readme.write_text(f'# {plan.title}\n\nOpen remake.blend in Blender 5.1+. Objects, cameras, materials, shot markers, and animation are editable.\n\n{plan.summary}\n\n## Known approximations\n\n' + '\n'.join('- '+item for item in plan.limitations) + '\n\nThe source reference is excluded from this export. plan.json is the editable reconstruction specification. rebuild.py compiles it again: blender --background --python rebuild.py -- animation.config.json\n', encoding='utf-8')
        config = json.loads((folder / 'animation.config.json').read_text(encoding='utf-8'))
        config['folder'] = '.'
        with zipfile.ZipFile(folder / 'project.zip', 'w', zipfile.ZIP_DEFLATED) as archive:
            for name in ('remake.blend', 'plan.json', 'PROJECT.md', 'inventory.json'):
                archive.write(folder / name, name)
            archive.write(Path(__file__).with_name('blender_scene.py'), 'rebuild.py')
            archive.writestr('animation.config.json', json.dumps(config, indent=2))
