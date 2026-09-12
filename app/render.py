import json
import os
import shutil
from pathlib import Path
from .models import validate_timing
from .process import run

ROOT = Path(__file__).resolve().parents[1]


def blender_binary():
    configured = os.environ.get('BLENDER_PATH')
    if configured and Path(configured).is_file():
        return configured
    found = shutil.which('blender')
    if found:
        return found
    candidates = list(Path('C:/Program Files/Blender Foundation').glob('Blender */blender.exe'))
    if candidates:
        return str(sorted(candidates, reverse=True)[0])
    raise ValueError('Blender is missing. Install Blender 5.1 or set BLENDER_PATH.')


def dimensions(meta, quality):
    edge = 720 if quality == 'standard' else 432
    scale = edge / max(meta['width'], meta['height'])
    return max(2, round(meta['width']*scale/2)*2), max(2, round(meta['height']*scale/2)*2)


def render(folder, plan, meta, quality, cancel, *, mode='preview', times=None):
    validate_timing(plan, meta['duration'])
    (folder / 'plan.json').write_text(plan.model_dump_json(indent=2), encoding='utf-8')
    width, height = dimensions(meta, quality)
    config = dict(folder=str(folder), width=width, height=height, duration=meta['duration'],
        fps=24, samples=32 if quality == 'standard' else 12, mode=mode, times=times or [])
    config_path = folder / f'{mode}.config.json'
    config_path.write_text(json.dumps(config), encoding='utf-8')
    if mode == 'animation':
        # Old frames must never fill gaps in a failed rerender. Delete only matching
        # generated PNGs beneath this exact job's validated frame directory.
        frames = (folder / 'frames').resolve()
        if not frames.is_relative_to(folder.resolve()):
            raise ValueError('Invalid render output directory.')
        for old_frame in frames.glob('frame-*.png'):
            old_frame.unlink()
    run([blender_binary(), '--background', '--factory-startup', '--disable-autoexec', '--python-exit-code', '1',
         '--python', ROOT / 'app' / 'blender_scene.py', '--', config_path], cwd=folder,
        timeout=3600 if mode == 'animation' else 600, cancel=cancel, log=folder / f'blender-{mode}.log')
    if not (folder / 'remake.blend').is_file():
        raise ValueError('Blender did not save an editable project.')
    if mode == 'preview':
        paths = [folder / 'previews' / f'{i:03d}.png' for i in range(len(times or []))]
        if not all(p.exists() for p in paths):
            raise ValueError('Blender did not finish the preview frames.')
        return paths
    expected = max(1, round(meta['duration']*24))
    if not all((folder / 'frames' / f'frame-{i:04d}.png').is_file() for i in range(1, expected+1)):
        raise ValueError('Blender did not finish every animation frame.')
    return []


def encode(folder, duration, audio, cancel):
    args = ['ffmpeg', '-y', '-v', 'error', '-framerate', '24', '-i', folder / 'frames' / 'frame-%04d.png']
    if audio:
        args += ['-i', folder / 'reference.mp4', '-map', '0:v:0', '-map', '1:a:0?']
    args += ['-t', str(duration), '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-crf', '18', '-c:a', 'aac', '-movflags', '+faststart', folder / 'remake.mp4']
    run(args, timeout=180, cancel=cancel)
    # Comparison is rendered from the same source/rebuilt pair used by the workspace.
    run(['ffmpeg', '-y', '-v', 'error', '-i', folder / 'reference.mp4', '-i', folder / 'remake.mp4',
         '-filter_complex', '[0:v]scale=-2:720,setsar=1[a];[1:v]scale=-2:720,setsar=1[b];[a][b]hstack=inputs=2[v]',
         '-map', '[v]', *(['-map', '0:a:0?'] if audio else []), '-t', str(duration), '-c:v', 'libx264', '-crf', '20',
         '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-movflags', '+faststart', folder / 'comparison.mp4'], timeout=180, cancel=cancel)
