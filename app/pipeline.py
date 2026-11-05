import json
import re
import shutil
import threading
import traceback
import uuid
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import cv2

from . import ai, fidelity, media, reference, render
from .models import Plan
from .process import Cancelled

CAPACITY = 8
RUN_NAME = re.compile(r'[a-f0-9]{12}')


def preview_pairs(folder, attempt, times, previews):
    """Pair each rendered still with the reference frame at the same timestamp."""
    stills = attempt / 'reference-stills'
    stills.mkdir(exist_ok=True)
    cap = cv2.VideoCapture(str(folder / 'reference.mp4'))
    pairs = []
    try:
        for index, (time, path) in enumerate(zip(times, previews)):
            cap.set(cv2.CAP_PROP_POS_MSEC, time * 1000)
            ok, frame = cap.read()
            if not ok:
                raise ValueError(f'Could not extract the reference frame at {time:.3f}s.')
            target = stills / f'{index:03d}.jpg'
            cv2.imwrite(str(target), frame, [cv2.IMWRITE_JPEG_QUALITY, 92])
            pairs.append(dict(time=time, source=target.relative_to(folder).as_posix(),
                              render=Path(path).resolve().relative_to(folder.resolve()).as_posix()))
    finally:
        cap.release()
    return pairs


class Pipeline:
    def __init__(self, store):
        self.store = store
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='blendremake')
        self.tokens = {}
        self.lock = threading.RLock()

    def submit(self, job_id, *, revise=False, final=False):
        with self.lock:
            if job_id in self.tokens:
                raise ValueError('This project is already running.')
            if len(self.tokens) >= CAPACITY:
                raise ValueError('Eight projects are already queued. Wait for one to finish.')
            token = threading.Event()
            self.tokens[job_id] = token
            self.store.update(job_id, status='queued', progress=0,
                              message='Queued for the final render' if final else 'Queued for Blender')
            self.executor.submit(self.work, job_id, token, revise, final=final)

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

    @staticmethod
    def attempt(folder):
        # Each run writes into its own folder, so a failed run can never damage
        # the last good downloads referenced by the job.
        path = folder / 'runs' / uuid.uuid4().hex[:12]
        path.mkdir(parents=True)
        return path

    @staticmethod
    def prune(folder, job):
        """Delete run folders no artifact references. Only exact generated run names are touched."""
        runs = (folder / 'runs').resolve()
        if not runs.is_dir() or not runs.is_relative_to(folder.resolve()):
            return
        paths = list(job.get('artifacts', {}).values())
        paths += [p for frame in job.get('preview_frames') or [] for p in (frame['source'], frame['render'])]
        keep = {p.split('/')[1] for p in paths if p.startswith('runs/') and p.count('/') >= 2}
        for child in runs.iterdir():
            if child.is_dir() and RUN_NAME.fullmatch(child.name) and child.name not in keep and child.parent == runs:
                shutil.rmtree(child)

    def work(self, job_id, cancel, revise, final=False):
        store = self.store
        folder = store.folder(job_id)
        phase = 'final' if final else 'preview'

        def progress(message, value, **fields):
            if cancel.is_set():
                raise Cancelled()
            store.update(job_id, status='running', message=message, progress=value, **fields)

        try:
            job = store.get(job_id)
            if final:
                self.final(job_id, folder, job, cancel, progress)
            else:
                self.preview(job_id, folder, job, cancel, revise, progress)
            self.prune(folder, store.get(job_id))
        except Cancelled:
            store.update(job_id, status='cancelled', resume_phase=phase, message='Cancelled. Saved work is available for retry.')
        except Exception as error:
            (folder / 'error.log').write_text(traceback.format_exc(), encoding='utf-8')
            message = str(error) if isinstance(error, (ValueError, TimeoutError)) else 'This step failed. Check the project error log, then retry.'
            if any(word in str(error).lower() for word in ('usage limit', 'rate_limit', 'usage_limit', 'quota')):
                message = 'ChatGPT usage limit reached. Wait for your allowance to reset, then retry.'
            store.update(job_id, status='failed', resume_phase=phase, message=message[:800])
        finally:
            with self.lock:
                self.tokens.pop(job_id, None)

    def reference_meta(self, folder, job, cancel, progress):
        source = folder / 'source.bin'
        progress('Preparing your reference', 3)
        if not source.exists():
            media.download(job['url'], source, cancel)
        if not (folder / 'reference.mp4').exists():
            return media.prepare(source, folder, job['start'], job['duration'], cancel)
        return media.probe(folder / 'reference.mp4')

    def preview(self, job_id, folder, job, cancel, revise, progress):
        store = self.store
        meta = self.reference_meta(folder, job, cancel, progress)
        progress('Scanning every reference frame', 6, meta=meta, artifacts=dict(job.get('artifacts') or {}, reference='reference.mp4'))
        manifest, sheet_paths = reference.audit(folder / 'reference.mp4', folder, cancel,
            on_progress=lambda done, total: progress(f'Scanned frame {done} of {total}', 6 + round(6 * done / max(total, 1))))
        analysis = dict(frames=manifest['frame_count'], sheets=len(manifest['sheets']), reviewed_batches=0,
                        total_batches=-(-len(manifest['sheets']) // ai.OBSERVATION_BATCH), visual_review='pending')
        store.update(job_id, analysis=analysis)
        plan = None
        if (folder / 'plan.json').exists():
            plan = Plan.model_validate_json((folder / 'plan.json').read_text(encoding='utf-8'))
        times = media.timestamps(folder / 'reference.mp4', meta['duration'])
        images = media.sheets(folder / 'reference.mp4', folder, 'SOURCE', times)
        if plan is None or revise:
            def observed(done, total):
                progress(f'Astra is reading frame sequences ({done} of {total})', 12 + round(10 * done / max(total, 1)),
                         analysis=dict(analysis, reviewed_batches=done, visual_review='complete' if done == total else 'pending'))
            observations = ai.observe(folder, meta, manifest, sheet_paths, cancel, on_progress=observed)
            progress('Astra is reconstructing the scene', 24)
            plan = ai.generate(folder, meta, images, job.get('brief', ''), cancel, previous=plan, observations=observations)
        brief = job.get('brief', '')
        review_times = sorted(set(round(min(meta['duration'] - 1 / meta.get('fps', 24), shot.start + (shot.end - shot.start) * fraction), 4)
                                  for shot in plan.shots for fraction in (.12, .5, .88)))[:24]
        attempt = self.attempt(folder)
        progress('Blender is building preview frames', 40, **self.plan_fields(plan))
        try:
            previews = render.render(attempt, plan, meta, 'draft', cancel, times=review_times)
        except (ValueError, RuntimeError) as error:
            progress('Repairing a Blender scene error', 42)
            plan = ai.generate(folder, meta, images, brief, cancel, previous=plan, error=error)
            previews = render.render(attempt, plan, meta, 'draft', cancel, times=review_times)
        if job.get('review', True):
            progress('Astra is comparing the render with your reference', 55)
            source_review = media.sheets(folder / 'reference.mp4', folder, 'SOURCE-review', review_times)
            rendered = media.rendered_sheets(previews, folder, review_times)
            previous = plan
            try:
                improved = ai.generate(folder, meta, source_review + rendered, brief, cancel, previous=plan, review=True)
                previews = render.render(attempt, improved, meta, 'draft', cancel, times=review_times)
                plan = improved
            except (ValueError, RuntimeError, TimeoutError):
                (folder / 'review-error.log').write_text(traceback.format_exc(), encoding='utf-8')
                plan = previous
                plan.limitations.append('Automatic review did not finish; the initial validated reconstruction was retained.')
                previews = render.render(attempt, plan, meta, 'draft', cancel, times=review_times)
        # The reviewed plan becomes the one a final render must use without new model calls.
        pending = folder / 'plan.json.tmp'
        pending.write_text(plan.model_dump_json(indent=2), encoding='utf-8')
        pending.replace(folder / 'plan.json')
        frames = preview_pairs(folder, attempt, review_times, previews)
        artifacts = dict(store.get(job_id).get('artifacts') or {})
        artifacts.update(reference='reference.mp4', preview_blend=(attempt / 'remake.blend').relative_to(folder).as_posix())
        if frames:
            artifacts['poster'] = frames[0]['render']
        store.update(job_id, status='preview', progress=100, resume_phase='final', preview_frames=frames, artifacts=artifacts,
                     message='Preview ready. Compare the stills, revise, or render the full video.', **self.plan_fields(plan))
        if job.get('preview_first', True) is False:
            self.final(job_id, folder, store.get(job_id), cancel, progress)

    def final(self, job_id, folder, job, cancel, progress):
        store = self.store
        meta = self.reference_meta(folder, job, cancel, progress)
        plan_path = folder / 'plan.json'
        if not plan_path.exists():
            raise ValueError('Build a preview before rendering the full video.')
        plan = Plan.model_validate_json(plan_path.read_text(encoding='utf-8'))
        attempt = self.attempt(folder)
        quality = job.get('quality', 'draft')
        progress('Rendering the complete animation', 10, **self.plan_fields(plan))
        render.render(attempt, plan, meta, quality, cancel, mode='animation',
            on_progress=lambda done, total: progress(f'Rendering frame {done} of {total}', 10 + round(75 * done / total)))
        progress('Preparing video and Blender downloads', 88)
        render.encode(attempt, meta['duration'], job.get('audio', True) and meta.get('audio'), cancel, folder / 'reference.mp4')
        self.package(attempt, plan)
        progress('Scoring the remake against every reference frame', 92)
        score = None
        try:
            score = fidelity.score_run(folder / 'reference.mp4', attempt, meta, cancel)
        except Cancelled:
            raise
        except Exception:
            # A scoring failure must not hide a finished render; the log explains why no score is shown.
            (attempt / 'fidelity-error.log').write_text(traceback.format_exc(), encoding='utf-8')
        relative = lambda name: (attempt / name).relative_to(folder).as_posix()
        artifacts = dict(job.get('artifacts') or {})
        artifacts.pop('preview_blend', None)
        artifacts.update(reference='reference.mp4', video=relative('remake.mp4'), blend=relative('remake.blend'),
                         comparison=relative('comparison.mp4'), project=relative('project.zip'), plan=relative('plan.json'))
        if score:
            artifacts['fidelity'] = relative('fidelity.json')
        store.update(job_id, status='completed', progress=100, resume_phase=None, preview_frames=[], artifacts=artifacts,
                     fidelity=fidelity.summary(score) if score else None,
                     message='Remake ready. Compare it with your reference.')

    @staticmethod
    def plan_fields(plan):
        return dict(title=plan.title, summary=plan.summary, limitations=plan.limitations,
                    shots=[dict(name=s.name, start=s.start, end=s.end, description=s.description, objects=len(s.objects)) for s in plan.shots])

    @staticmethod
    def package(folder, plan):
        readme = folder / 'PROJECT.md'
        readme.write_text(f'# {plan.title}\n\nOpen remake.blend in Blender 5.1+. Objects, cameras, materials, shot markers, and animation are editable.\n\n{plan.summary}\n\n## Known approximations\n\n' + '\n'.join('- '+item for item in plan.limitations) + '\n\nThe source reference is excluded from this export. plan.json contains compact asset recipes for regeneration inside BlendClone. expanded_plan.json contains the complete portable geometry and is the input to rebuild.py. Edit the expanded plan when rebuilding without the app: blender --background --factory-startup --disable-autoexec --python rebuild.py -- animation.config.json\n', encoding='utf-8')
        config = json.loads((folder / 'animation.config.json').read_text(encoding='utf-8'))
        config['folder'] = '.'
        with zipfile.ZipFile(folder / 'project.zip', 'w', zipfile.ZIP_DEFLATED) as archive:
            for name in ('remake.blend', 'plan.json', 'expanded_plan.json', 'PROJECT.md', 'inventory.json'):
                archive.write(folder / name, name)
            archive.write(Path(__file__).with_name('blender_scene.py'), 'rebuild.py')
            if plan.captions:
                font = folder / 'fonts' / 'arialbd.ttf'
                if not font.is_file():
                    font = Path('C:/Windows/Fonts/arialbd.ttf')
                archive.write(font, 'fonts/arialbd.ttf')
            archive.writestr('animation.config.json', json.dumps(config, indent=2))
