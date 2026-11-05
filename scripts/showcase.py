"""Build the README showcase: original scene JSON -> Blender renders -> MP4 / GIF / poster.

Every scene here is authored for this repository (no third-party footage). Each one goes
through the same validated contract and compiler the app uses, so the media shows what the
compiler can actually produce.

    python scripts/showcase.py                 # render every scene, then build media
    python scripts/showcase.py --preview       # quick draft stills for framing checks
    python scripts/showcase.py --only cascade  # one scene
    python scripts/showcase.py --media-only    # rebuild GIFs from existing renders
"""
import argparse
import json
import math
import shutil
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.models import Plan  # noqa: E402
from app.render import render  # noqa: E402
from app.process import run  # noqa: E402

WORK = ROOT / 'outputs' / 'showcase'
MEDIA = ROOT / 'docs' / 'media' / 'showcase'
EXAMPLES = ROOT / 'examples'
W, H, FPS = 960, 540, 24


def key(t, prop, value, interp='BEZIER'):
    return dict(t=t, property=prop, value=list(value), interpolation=interp)


def orbit(radius, height, start_deg, end_deg, duration, steps=6):
    keys = []
    for i in range(steps + 1):
        a = math.radians(start_deg + (end_deg - start_deg) * i / steps)
        keys.append(key(duration * i / steps, 'location', (radius * math.cos(a), radius * math.sin(a), height), 'LINEAR'))
    return keys


def shifted(objects, offset, duration):
    """Re-time shot-relative keys for a later shot that continues the same action."""
    out = json.loads(json.dumps(objects))
    for obj in out:
        keys, by_prop = [], {}
        for k in sorted(obj.get('keys', []), key=lambda k: k['t']):
            by_prop.setdefault(k['property'], []).append(k)
        for prop, track in by_prop.items():
            before = [k for k in track if k['t'] - offset <= 0]
            after = [dict(k, t=round(k['t'] - offset, 4)) for k in track if 0 < k['t'] - offset <= duration]
            if before:
                keys.append(dict(before[-1], t=0))
            keys += after
        obj['keys'] = keys
    return out


def studio_lights(warm='#ffe2c4', cool='#9fd2ff', energy=1.0):
    return [
        dict(kind='AREA', location=[4, -5, 7], target=[0, 0, 1], color=warm, energy=1400 * energy, size=4),
        dict(kind='AREA', location=[-6, 2, 4], target=[0, 0, 1], color=cool, energy=900 * energy, size=6),
        dict(kind='AREA', location=[0, 7, 5], target=[0, 0, 1], color='#ffffff', energy=700 * energy, size=3),
    ]


def turntable():
    d = 4.0
    return dict(
        title='Studio turntable', engine='CYCLES',
        summary='Authored showcase: coated, metallic and glass materials on a bevelled pedestal with an orbiting camera.',
        limitations=['Authored scene; not a reconstruction of any reference video.'],
        materials=[
            dict(id='lacquer', color='#e8432e', roughness=.18, coat=1),
            dict(id='chrome', color='#d9dde3', roughness=.08, metallic=1),
            dict(id='glass', color='#cfe9ff', roughness=.02, transmission=1),
            dict(id='marble', color='#ecebe6', roughness=.35, pattern='noise', detail_color='#b9b8b2', texture_scale=3, bump=.15),
            dict(id='stage', color='#1c2026', roughness=.6),
        ],
        shots=[dict(
            name='Turntable', start=0, end=d, background='#0f1216',
            description='Three hero objects on a marble pedestal; the camera orbits a quarter turn.',
            camera=dict(location=[7, -7, 3.6], target=[0, 0, 1.25], lens=50, aperture=2.8, keys=orbit(9.2, 3.6, -50, 20, d)),
            lights=studio_lights(),
            objects=[
                dict(id='pedestal', kind='cylinder', material='marble', location=[0, 0, .3], scale=[2.6, 2.6, .3], bevel=.05),
                dict(id='cube', kind='cube', material='lacquer', location=[-1.15, -.35, 1.2], scale=[.6, .6, .6], bevel=.12,
                     keys=[key(0, 'rotation', (0, 0, 0), 'LINEAR'), key(d, 'rotation', (0, 0, 90), 'LINEAR')]),
                dict(id='ring', kind='torus', material='chrome', location=[1.1, -.2, 1.45], rotation=[70, 0, 0], scale=[.75, .75, .75],
                     keys=[key(0, 'rotation', (70, 0, 0), 'LINEAR'), key(d, 'rotation', (70, 0, 180), 'LINEAR')]),
                dict(id='orb', kind='sphere', material='glass', location=[.05, .95, 1.2], scale=[.6, .6, .6], subdivision=1,
                     keys=[key(0, 'location', (.05, .95, 1.2)), key(d / 2, 'location', (.05, .95, 1.55)), key(d, 'location', (.05, .95, 1.2))]),
                dict(id='floor', kind='plane', material='stage', scale=[60, 60, 1]),
            ])])


def cascade():
    d1, d2 = 2.4, 4.0
    dominoes = []
    half_t, half_h = .12, .9
    for i in range(9):
        x = -4 + i * 1.0
        t = .35 + i * .17
        rest = 86 if i == 8 else 72
        keys = []
        # Tip over the leading bottom edge so the tile never sinks into or floats off the floor.
        for step, frac in enumerate((0, .3, .6, .85, 1)):
            a = math.radians(rest * frac)
            at = t + .4 * (step / 4) ** .8
            keys += [key(at, 'rotation', (0, rest * frac, 0)),
                     key(at, 'location', (x + half_t - half_t * math.cos(a) + half_h * math.sin(a), 0, half_t * math.sin(a) + half_h * math.cos(a)))]
        dominoes.append(dict(
            id=f'tile_{i}', kind='cube', material='tile_a' if i % 2 else 'tile_b', location=[x, 0, half_h], scale=[half_t, .55, half_h], bevel=.03,
            keys=[key(0, 'rotation', (0, 0, 0)), key(0, 'location', (x, 0, half_h)), *keys]))
    ball = dict(id='ball', kind='sphere', material='ball', location=[-6, 0, .45], scale=[.45, .45, .45],
                keys=[key(0, 'location', (-6, 0, .45)), key(.35, 'location', (-4.3, 0, .45)),
                      key(0, 'rotation', (0, 0, 0)), key(.35, 'rotation', (0, 220, 0))])
    floor = dict(id='floor', kind='plane', material='floor', scale=[60, 60, 1])
    mats = [
        dict(id='tile_a', color='#f2b33d', roughness=.3, coat=.6),
        dict(id='tile_b', color='#f4efe6', roughness=.3, coat=.6),
        dict(id='ball', color='#2f7cf6', roughness=.15, coat=1),
        dict(id='floor', color='#262b33', roughness=.45, pattern='noise', detail_color='#1d2128', texture_scale=12),
    ]
    common = dict(lights=studio_lights(energy=1.1), background='#12151a')
    objs = [ball, *dominoes, floor]
    return dict(
        title='Domino cascade', engine='CYCLES',
        summary='Authored showcase: staggered rotation keys and a two-shot edit with a hard camera cut.',
        limitations=['Keyframed motion, not a physics simulation.'],
        materials=mats,
        shots=[
            dict(name='Wide', start=0, end=d1, description='Wide tracking shot as the ball starts the run.',
                 camera=dict(location=[-3, -9, 3], target=[-1.5, 0, .8], lens=40,
                             keys=[key(0, 'location', (-4, -9, 3)), key(d1, 'location', (1, -9, 2.6))],
                             target_keys=[key(0, 'location', (-3, 0, .8)), key(d1, 'location', (1.5, 0, .7))]),
                 objects=json.loads(json.dumps(objs)), **common),
            dict(name='Close', start=d1, end=d2, description='Low close-up as the last tiles land.',
                 camera=dict(location=[8, -5.5, 1.8], target=[2.6, 0, .4], lens=42, aperture=2.8,
                             keys=[key(0, 'location', (8.4, -6, 2.0)), key(d2 - d1, 'location', (7.2, -4.8, 1.6))]),
                 objects=shifted(objs, d1, d2 - d1), **common),
        ])


def neon():
    d = 4.0
    rings = []
    for i, (r, tilt, spin) in enumerate([(2.4, 72, 140), (3.0, 60, -110), (3.6, 84, 80)]):
        points = [[r * math.cos(math.tau * k / 12), r * math.sin(math.tau * k / 12), 0] for k in range(13)]
        rings.append(dict(id=f'ring_{i}', kind='curve', material=['neon_pink', 'neon_cyan', 'neon_violet'][i], points=points, thickness=.045,
                          location=[0, 1.6, 1.7], rotation=[tilt, 0, 0],
                          keys=[key(0, 'rotation', (tilt, 0, 0), 'LINEAR'), key(d, 'rotation', (tilt, spin * .25, spin), 'LINEAR')]))
    return dict(
        title='Neon type', engine='CYCLES',
        summary='Authored showcase: emissive materials, 3D text, spinning rings and a dolly push-in.',
        limitations=['Authored scene; not a reconstruction of any reference video.'],
        materials=[
            dict(id='neon_pink', color='#ff1f8f', emission=3, unlit=True),
            dict(id='neon_cyan', color='#12d6ff', emission=3, unlit=True),
            dict(id='neon_violet', color='#8a4dff', emission=3, unlit=True),
            dict(id='type', color='#f4f6ff', roughness=.28, metallic=.35, emission=.25),
            dict(id='floor', color='#0b0c12', roughness=.12, metallic=.3),
        ],
        shots=[dict(
            name='Title', start=0, end=d, background='#05060a',
            description='Chrome title card inside neon rings, reflected in a glossy floor.',
            camera=dict(location=[0, -11, 2.2], target=[0, 0, 1.6], lens=40, aperture=4,
                        keys=[key(0, 'location', (-1.4, -12, 2.6)), key(d, 'location', (.6, -10.6, 2.0))]),
            lights=[dict(kind='AREA', location=[0, -6, 5], target=[0, 0, 1.6], color='#dfe6ff', energy=700, size=5),
                    dict(kind='POINT', location=[-2, 1.6, 2.4], color='#ff3ea5', energy=400, size=.5),
                    dict(kind='POINT', location=[2.2, 1.6, 1.2], color='#2de2ff', energy=400, size=.5)],
            objects=[
                dict(id='title', kind='text', text='BlendClone', material='type', location=[0, 0, 1.6], rotation=[90, 0, 0],
                     scale=[1.9, 1.9, 1.9],
                     keys=[key(0, 'scale', (.01, .01, .01)), key(.7, 'scale', (2.0, 2.0, 2.0)), key(1.0, 'scale', (1.9, 1.9, 1.9)),
                           key(0, 'location', (0, 0, 1.0)), key(.8, 'location', (0, 0, 1.6))]),
                *rings,
                dict(id='floor', kind='plane', material='floor', scale=[60, 60, 1]),
            ])])


def island():
    """Low-poly island: one generated mesh with per-face materials picked by height."""
    d, n, size = 4.0, 34, 14.0

    def height(x, y):
        r = math.hypot(x, y) / (size * .42)
        bumps = .55 * math.sin(x * .9) * math.cos(y * .7) + .35 * math.sin(x * 1.7 + y * 1.3) + .2 * math.cos(y * 2.3 - x * .5)
        return 3.2 * max(0, 1 - r * r) + bumps * max(0, 1 - r) - .9 * min(1, r)

    vertices = []
    for j in range(n + 1):
        for i in range(n + 1):
            x, y = (i / n - .5) * size, (j / n - .5) * size
            vertices.append([round(x, 4), round(y, 4), round(height(x, y), 4)])
    faces, face_materials = [], []
    for j in range(n):
        for i in range(n):
            a, b = j * (n + 1) + i, j * (n + 1) + i + 1
            c, e = (j + 1) * (n + 1) + i + 1, (j + 1) * (n + 1) + i
            for tri in ((a, b, c), (a, c, e)):
                faces.append(list(tri))
                z = sum(vertices[v][2] for v in tri) / 3
                face_materials.append('sand' if z < .25 else 'grass' if z < 1.7 else 'rock' if z < 2.6 else 'snow')
    trees = []
    for k, (x, y) in enumerate([(-2.2, -1.1), (-1.5, -2.0), (1.8, -1.6), (2.6, .4), (-2.8, .9), (.9, 2.4), (-.6, -2.7), (3.1, -.9)]):
        trees.append(dict(id=f'tree_{k}', kind='cone', material='pine', location=[x, y, height(x, y) + .45], scale=[.32, .32, .55], smooth=False))
    return dict(
        title='Low-poly island', engine='CYCLES',
        summary='Authored showcase: a generated custom mesh with per-face materials, flat shading, water and an orbiting flyover.',
        limitations=['Authored scene; not a reconstruction of any reference video.'],
        materials=[
            dict(id='sand', color='#e9d29a', roughness=.9), dict(id='grass', color='#5fae4e', roughness=.85),
            dict(id='rock', color='#8a8178', roughness=.9), dict(id='snow', color='#f5f7fa', roughness=.6),
            dict(id='pine', color='#2f7d4a', roughness=.8),
            dict(id='water', color='#1f86c4', roughness=.08, coat=.8),
            dict(id='boat', color='#e8432e', roughness=.4),
        ],
        shots=[dict(
            name='Flyover', start=0, end=d, background='#9fd3f0',
            description='Sunlit island; the camera sweeps around while a boat crosses the bay.',
            camera=dict(location=[10, -10, 6], target=[0, 0, .8], lens=35, keys=orbit(13.5, 6.2, -70, -20, d)),
            lights=[dict(kind='SUN', location=[5, -5, 10], target=[0, 0, 0], color='#fff1d6', energy=4, size=.05),
                    dict(kind='AREA', location=[-8, 6, 8], target=[0, 0, 0], color='#bfe3ff', energy=1500, size=10)],
            objects=[
                dict(id='island', kind='mesh', material='grass', vertices=vertices, faces=faces, face_materials=face_materials, smooth=False),
                dict(id='sea', kind='plane', material='water', location=[0, 0, .05], scale=[80, 80, 1]),
                dict(id='boat', kind='cube', material='boat', location=[-6, -5.2, .18], scale=[.7, .28, .18], bevel=.06,
                     keys=[key(0, 'location', (-5.5, -5.6, .22), 'LINEAR'), key(d, 'location', (-.5, -6.4, .22), 'LINEAR')],
                     rotation=[0, 0, -9]),
                *trees,
            ])])


SCENES = {'turntable': (turntable, 4.0), 'cascade': (cascade, 4.0), 'neon': (neon, 4.0), 'island': (island, 4.0)}


def build(name, preview):
    maker, duration = SCENES[name]
    plan = Plan.model_validate(maker())
    EXAMPLES.joinpath(f'{name}.json').write_text(plan.model_dump_json(indent=2, exclude_defaults=True), encoding='utf-8')
    folder = WORK / name
    folder.mkdir(parents=True, exist_ok=True)
    meta = dict(duration=duration, width=W, height=H, audio=False, fps=FPS)
    cancel = threading.Event()
    started = time.monotonic()
    if preview:
        paths = render(folder, plan, meta, 'standard', cancel, mode='preview', times=[0.4, duration * .5, duration - .2])
        print(name, 'preview', [str(p) for p in paths], f'{time.monotonic() - started:.0f}s')
        return
    render(folder, plan, meta, 'standard', cancel, mode='animation')
    print(name, 'rendered', f'{time.monotonic() - started:.0f}s', flush=True)


def ffmpeg(*args):
    run(['ffmpeg', '-y', '-v', 'error', *args], timeout=1800)


def explainer():
    """Scene JSON on the left, the compiled Blender render on the right."""
    from PIL import Image, ImageDraw, ImageFont
    plan = json.loads((EXAMPLES / 'turntable.json').read_text(encoding='utf-8'))
    shot = plan['shots'][0]
    excerpt = {
        'materials': [m for m in plan['materials'] if m['id'] in ('lacquer', 'chrome', 'glass')],
        'objects': [{k: v for k, v in o.items() if k != 'keys'} | ({'keys': f"[{len(o['keys'])} keys]"} if o.get('keys') else {})
                    for o in shot['objects'] if o['id'] in ('cube', 'ring', 'orb')],
    }
    import re
    text = json.dumps(excerpt, indent=2)
    text = re.sub(r'\[\s*([-0-9.,\s]+?)\s*\]', lambda m: '[' + ', '.join(v.strip() for v in m.group(1).split(',')) + ']', text)
    lines = []
    for line in text.splitlines():
        lines.append(line if len(line) <= 58 else line[:55] + '...')
    lines = lines[:33]
    width, height, pad = 1600, 640, 28
    card = Image.new('RGB', (width, height), '#0d1117')
    draw = ImageDraw.Draw(card)

    def font(name, size):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            return ImageFont.load_default()
    mono, label = font('consola.ttf', 15), font('segoeuib.ttf', 20)
    draw.rounded_rectangle((pad, pad, 640, height - pad), 14, fill='#161b22', outline='#30363d')
    draw.text((pad + 20, pad + 14), 'scene.json  (validated contract)', font=label, fill='#e6edf3')
    y = pad + 52
    for line in lines:
        x = pad + 20
        stripped = line.lstrip()
        draw.text((x, y), line[:len(line) - len(stripped)], font=mono, fill='#8b949e')
        indent = draw.textlength(line[:len(line) - len(stripped)], font=mono)
        if stripped.startswith('"') and '":' in stripped:
            k, rest = stripped.split('":', 1)
            draw.text((x + indent, y), k + '":', font=mono, fill='#79c0ff')
            draw.text((x + indent + draw.textlength(k + '":', font=mono), y), rest, font=mono, fill='#a5d6ff' if '"' in rest else '#ffa657')
        else:
            draw.text((x + indent, y), stripped, font=mono, fill='#8b949e')
        y += 16
    draw.polygon([(668, 300), (700, 320), (668, 340)], fill='#f5792a')
    draw.rectangle((652, 314, 672, 326), fill='#f5792a')
    render_img = Image.open(WORK / 'turntable' / 'frames' / 'frame-0001.png').convert('RGB').resize((width - 740 - pad, round((width - 740 - pad) * 9 / 16)), Image.LANCZOS)
    top = (height - render_img.height) // 2 + 14
    draw.text((740, top - 34), 'remake.blend  (native Blender objects, Cycles render)', font=label, fill='#e6edf3')
    card.paste(render_img, (740, top))
    card.save(MEDIA / 'scene-to-render.png', optimize=True)


def media(names):
    MEDIA.mkdir(parents=True, exist_ok=True)
    for name in names:
        frames = WORK / name / 'frames' / 'frame-%04d.png'
        ffmpeg('-framerate', str(FPS), '-i', frames, '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-crf', '20', '-movflags', '+faststart', MEDIA / f'{name}.mp4')
        ffmpeg('-i', MEDIA / f'{name}.mp4', '-vf', 'fps=12,scale=560:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=128:stats_mode=diff[p];[b][p]paletteuse=dither=sierra2_4a:diff_mode=rectangle',
               MEDIA / f'{name}.gif')
        last = sorted((WORK / name / 'frames').glob('frame-*.png'))
        shutil.copy(last[len(last) * 2 // 3], MEDIA / f'{name}.png')
    if len(names) == 4:
        inputs = []
        for name in names:
            inputs += ['-i', MEDIA / f'{name}.mp4']
        grid = ('[0:v]scale=480:270[a];[1:v]scale=480:270[b];[2:v]scale=480:270[c];[3:v]scale=480:270[d];'
                '[a][b][c][d]xstack=inputs=4:layout=0_0|w0_0|0_h0|w0_h0[v]')
        ffmpeg(*inputs, '-filter_complex', grid, '-map', '[v]', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-crf', '20', '-movflags', '+faststart', MEDIA / 'showcase-grid.mp4')
        ffmpeg('-i', MEDIA / 'showcase-grid.mp4', '-vf', 'fps=12,scale=800:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=160:stats_mode=diff[p];[b][p]paletteuse=dither=sierra2_4a:diff_mode=rectangle',
               MEDIA / 'showcase-grid.gif')
    if 'turntable' in names:
        explainer()
    for path in sorted(MEDIA.iterdir()):
        print(f'{path.name:24} {path.stat().st_size / 1e6:6.2f} MB')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--preview', action='store_true')
    parser.add_argument('--media-only', action='store_true')
    parser.add_argument('--only', choices=list(SCENES))
    args = parser.parse_args()
    names = [args.only] if args.only else list(SCENES)
    if not args.media_only:
        for name in names:
            build(name, args.preview)
    if not args.preview:
        media(names if args.only is None else names)
