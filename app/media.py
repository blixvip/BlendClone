import ipaddress
import json
import math
import socket
import sys
import uuid
from fractions import Fraction
from pathlib import Path
from urllib.parse import urlsplit
import cv2
from PIL import Image, ImageDraw
from .process import run, Cancelled

MAX_BYTES = 250 * 1024 * 1024
FORMATS = 'mov,matroska,webm,avi,mpegts,mpeg,ogg,flv'


def validate_url(url):
    parsed = urlsplit(url)
    hosts = ('youtube.com', 'youtu.be', 'vimeo.com', 'x.com', 'twitter.com')
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.port not in (None, 443):
        raise ValueError('Use a public HTTPS YouTube, Vimeo, or X video link.')
    if not any(parsed.hostname == h or parsed.hostname.endswith('.' + h) for h in hosts):
        raise ValueError('Use YouTube, Vimeo, or X, or upload a video file.')
    try:
        addresses = socket.getaddrinfo(parsed.hostname, 443, type=socket.SOCK_STREAM)
    except socket.gaierror as error:
        raise ValueError('Could not reach that video host.') from error
    if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
        raise ValueError('Private network links are not supported.')


def download_arguments(url, dest):
    return [sys.executable, '-m', 'yt_dlp', '--ignore-config', '--no-playlist', '--no-progress',
         '--max-filesize', str(MAX_BYTES), '--socket-timeout', '20', '--retries', '1',
         '-f', 'bestvideo[height<=1920][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=1920]+bestaudio/best',
         '--merge-output-format', 'mp4', '--remux-video', 'mp4', '-o', str(Path(dest).with_suffix('.%(ext)s')), '--', url]


def download(url, dest, cancel):
    validate_url(url)
    run(download_arguments(url, dest), timeout=240, cancel=cancel, log=dest.parent / 'download.log')
    merged=dest.with_suffix('.mp4')
    if merged != dest and merged.is_file():
        merged.replace(dest)
    if not dest.exists():
        raise ValueError('No video downloaded. Upload the file instead.')
    if dest.stat().st_size > MAX_BYTES:
        raise ValueError('Video exceeds 250 MB.')


def probe(path):
    try:
        data = json.loads(run(['ffprobe', '-v', 'error', '-protocol_whitelist', 'file,pipe',
            '-format_whitelist', FORMATS, '-show_streams', '-show_format', '-of', 'json', path], timeout=30))
        video = next(s for s in data['streams'] if s['codec_type'] == 'video')
        duration = float(video.get('duration') or data['format'].get('duration') or 0)
        width, height = int(video['width']), int(video['height'])
        if not math.isfinite(duration) or duration <= 0 or min(width, height) < 2 or max(width, height) > 8192:
            raise ValueError()
        rate=float(Fraction(video.get('avg_frame_rate') or '24'))
        if not math.isfinite(rate) or not 1 <= rate <= 240:raise ValueError()
        return dict(duration=duration, width=width, height=height, fps=rate, audio=any(s['codec_type'] == 'audio' for s in data['streams']))
    except (RuntimeError, KeyError, ValueError, ZeroDivisionError, StopIteration) as error:
        raise ValueError('Could not read this video. Upload a valid MP4, MOV, or WebM.') from error


def prepare(source, folder, start, duration, cancel):
    info = probe(source)
    if start >= info['duration']:
        raise ValueError('Start time is past the end of the video.')
    duration = min(duration, info['duration'] - start)
    if duration < .25:
        raise ValueError('Select at least a quarter second of video.')
    target = folder / 'reference.mp4'
    temporary = folder / f'.reference-{uuid.uuid4().hex}.mp4'
    fps=info['fps']
    try:
        run(['ffmpeg', '-y', '-v', 'error', '-protocol_whitelist', 'file,pipe', '-format_whitelist', FORMATS,
             '-ss', str(start), '-i', source, '-t', str(duration), '-map', '0:v:0', '-map', '0:a:0?',
             '-vf', f"scale=trunc(iw/2)*2:trunc(ih/2)*2,setsar=1,fps={fps}",
             '-c:v', 'libx264', '-preset', 'fast', '-crf', '19', '-c:a', 'aac', '-movflags', '+faststart', temporary],
             timeout=180, cancel=cancel, log=folder / 'normalize.log')
        meta = probe(temporary)
        if cancel.is_set():
            raise Cancelled()
        temporary.replace(target)
        return meta
    finally:
        temporary.unlink(missing_ok=True)


def timestamps(video, duration):
    """Uniform samples plus both sides of strong visual changes; timestamps stay explicit."""
    count = min(36, max(8, math.ceil(duration * 3)))
    result = [i * max(0, duration - 1/24) / max(1, count - 1) for i in range(count)]
    cap = cv2.VideoCapture(str(video))
    previous = None
    changes = []
    for i in range(min(360, math.ceil(duration * 12))):
        t = i / 12
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
        ok, frame = cap.read()
        if not ok:
            continue
        small = cv2.resize(frame, (64, 64)).astype('float32')
        if previous is not None:
            score = float(abs(small - previous).mean())
            if score > 45:
                changes.append((score, t))
        previous = small
    cap.release()
    for _, t in sorted(changes, reverse=True)[:6]:
        result.extend([max(0, t - 1/12), min(duration - 1/24, t)])
    return sorted(set(round(t, 4) for t in result if t >= 0))


def sheets(video, folder, prefix, times):
    cap = cv2.VideoCapture(str(video))
    tiles = []
    try:
        for t in times:
            cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
            ok, frame = cap.read()
            if not ok:
                raise ValueError(f'Could not extract reference frame at {t:.2f}s.')
            im = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            im.thumbnail((300, 220))
            tile = Image.new('RGB', (320, 250), '#14171a')
            tile.paste(im, ((320-im.width)//2, 4))
            ImageDraw.Draw(tile).text((10, 232), f'{prefix}  {t:.3f}s', fill='white')
            tiles.append(tile)
    finally:
        cap.release()
    return save_tiles(tiles, folder, prefix)


def rendered_sheets(paths, folder, times):
    tiles = []
    for path, t in zip(paths, times):
        with Image.open(path) as source:
            im = source.convert('RGB')
        im.thumbnail((300, 220))
        tile = Image.new('RGB', (320, 250), '#14171a')
        tile.paste(im, ((320-im.width)//2, 4))
        ImageDraw.Draw(tile).text((10, 232), f'RENDER  {t:.3f}s', fill='white')
        tiles.append(tile)
    return save_tiles(tiles, folder, 'render-review')


def save_tiles(tiles, folder, prefix):
    paths = []
    for offset in range(0, len(tiles), 12):
        chunk = tiles[offset:offset+12]
        sheet = Image.new('RGB', (1280, math.ceil(len(chunk)/4)*250), '#14171a')
        for i, tile in enumerate(chunk):
            sheet.paste(tile, ((i % 4)*320, (i//4)*250))
        path = folder / f'{prefix}-{offset//12}.jpg'
        sheet.save(path, quality=90)
        paths.append(path)
    return paths
