import json
import os
import shutil
import time
from pathlib import Path
from .models import validate_timing
from .process import run

ROOT = Path(__file__).resolve().parents[1]
RESUME_ATTEMPTS = 4


def blender_binary():
    configured = os.environ.get('BLENDER_PATH')
    if configured and Path(configured).is_file():
        return configured
    found = shutil.which('blender')
    if found:
        return found
    candidates = [
        *Path('C:/Program Files/Blender Foundation').glob('Blender */blender.exe'),
        *Path('/Applications').glob('Blender*.app/Contents/MacOS/Blender'),
        *Path('/opt').glob('blender*/blender'),
    ]
    if candidates:
        return str(sorted(candidates, reverse=True)[0])
    raise ValueError('Blender is missing. Install Blender 5.1 or set BLENDER_PATH.')


def dimensions(meta, quality):
    if quality == 'final':
        return int(meta['width']), int(meta['height'])
    edge = {'draft': 432, 'standard': 720}[quality]
    scale = min(1, edge / max(meta['width'], meta['height']))
    return max(2, round(meta['width']*scale/2)*2), max(2, round(meta['height']*scale/2)*2)


def render(folder, plan, meta, quality, cancel, *, mode='preview', times=None, engine=None, on_progress=None):
    validate_timing(plan, meta['duration'])
    selected = engine or plan.engine
    if selected == 'auto':
        selected = 'BLENDER_EEVEE' if any(o.kind == 'asset' for s in plan.shots for o in s.objects) else 'CYCLES'
    if selected not in ('CYCLES', 'BLENDER_EEVEE'):
        raise ValueError('Unsupported Blender render engine.')
    # Pin the choice in both the reviewed plan and its portable expanded copy.
    plan.engine = selected
    (folder / 'plan.json').write_text(plan.model_dump_json(indent=2), encoding='utf-8')
    from .anatomy import expand_assets
    expanded=expand_assets(plan)
    (folder / 'expanded_plan.json').write_text(expanded.model_dump_json(),encoding='utf-8')
    width, height = dimensions(meta, quality)
    fps = plan.timeline.fps_num / plan.timeline.fps_den if plan.timeline else meta.get('fps',24)
    config = dict(folder=str(folder), width=width, height=height, duration=meta['duration'],
        fps=round(fps), fps_base=round(fps)/fps, samples={'draft': 12, 'standard': 32, 'final': 64}[quality], mode=mode, times=times or [],
        plan='expanded_plan.json', engine=selected)
    if plan.timeline:
        config.update(fps=round(fps), fps_base=round(fps) * plan.timeline.fps_den / plan.timeline.fps_num,
                      frame_count=plan.timeline.frame_count, source_start_frame=plan.timeline.source_start_frame)
    config_path = folder / f'{mode}.config.json'
    config_path.write_text(json.dumps(config), encoding='utf-8')
    # Every invocation must produce its own editable project and requested frames.
    # The pipeline keeps successful revisions in separate immutable attempt folders.
    for name in ('remake.blend', 'inventory.json'):
        (folder / name).unlink(missing_ok=True)
    if mode == 'preview':
        previews = (folder / 'previews').resolve()
        if not previews.is_relative_to(folder.resolve()):
            raise ValueError('Invalid preview output directory.')
        for index in range(len(times or [])):
            (previews / f'{index:03d}.png').unlink(missing_ok=True)
    if mode == 'animation':
        # Old frames must never fill gaps in a failed rerender. Delete only matching
        # generated PNGs beneath this exact job's validated frame directory.
        frames = (folder / 'frames').resolve()
        if not frames.is_relative_to(folder.resolve()):
            raise ValueError('Invalid render output directory.')
        for old_frame in frames.glob('frame-*.png'):
            old_frame.unlink()
    last_tick = [0.0]
    def report():
        if on_progress and mode == 'animation' and time.monotonic()-last_tick[0] >= 3:
            last_tick[0] = time.monotonic()
            on_progress(sum(1 for _ in (folder/'frames').glob('frame-*.png')), max(1, round(meta['duration']*fps)))
    def launch():
        run([blender_binary(), '--background', '--factory-startup', '--disable-autoexec', '--python-exit-code', '1',
             '--python', ROOT / 'app' / 'blender_scene.py', '--', config_path], cwd=folder,
            timeout=3600 if mode == 'animation' else 600, cancel=cancel, log=folder / f'blender-{mode}.log', on_tick=report)
    if mode != 'animation':
        launch()
    else:
        # Long GPU renders can die mid-sequence (driver resets on consumer cards). Resume from the
        # frames this call already finished instead of failing the job, as long as each attempt progresses.
        frames_dir = folder / 'frames'
        done = lambda: sorted(frames_dir.glob('frame-*.png'))
        for attempt in range(RESUME_ATTEMPTS + 1):
            before = len(done())
            try:
                launch()
                break
            except RuntimeError:
                finished_now = done()
                if attempt == RESUME_ATTEMPTS or len(finished_now) <= before:
                    raise
                finished_now[-1].unlink()  # the newest file may be a partial write
                config['resume'] = True
                config_path.write_text(json.dumps(config), encoding='utf-8')
    def finished(path):
        return path.is_file() and path.stat().st_size > 0
    if not finished(folder / 'remake.blend'):
        raise ValueError('Blender did not save an editable project.')
    if mode == 'preview':
        paths = [folder / 'previews' / f'{i:03d}.png' for i in range(len(times or []))]
        if not all(finished(p) for p in paths):
            raise ValueError('Blender did not finish the preview frames.')
        return paths
    expected = max(1, round(meta['duration']*fps))
    if not all(finished(folder / 'frames' / f'frame-{i:04d}.png') for i in range(1, expected+1)):
        raise ValueError('Blender did not finish every animation frame.')
    return []


def encode(folder, duration, audio, cancel, reference=None):
    reference = reference or folder / 'reference.mp4'
    config=json.loads((folder/'animation.config.json').read_text(encoding='utf-8'))
    fps=config['fps']/config.get('fps_base',1)
    args = ['ffmpeg', '-y', '-v', 'error', '-framerate', repr(fps), '-i', folder / 'frames' / 'frame-%04d.png']
    if audio:
        args += ['-i', reference, '-map', '0:v:0', '-map', '1:a:0?']
    args += ['-t', str(duration), '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-crf', '18', '-c:a', 'aac', '-movflags', '+faststart', folder / 'remake.mp4']
    run(args, timeout=1800, cancel=cancel)
    # Comparison is rendered from the same source/rebuilt pair used by the workspace.
    run(['ffmpeg', '-y', '-v', 'error', '-i', reference, '-i', folder / 'remake.mp4',
         '-filter_complex', '[0:v]scale=-2:720,setsar=1[a];[1:v]scale=-2:720,setsar=1[b];[a][b]hstack=inputs=2[v]',
         '-map', '[v]', *(['-map', '0:a:0?'] if audio else []), '-t', str(duration), '-c:v', 'libx264', '-crf', '20',
         '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-movflags', '+faststart', folder / 'comparison.mp4'], timeout=1800, cancel=cancel)
