import os
import shutil
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Literal
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware
from pydantic import BaseModel, Field
from . import ai, media, render
from .pipeline import Pipeline
from .store import Store

ROOT = Path(__file__).resolve().parents[1]


class Revision(BaseModel):
    brief: Annotated[str, Field(min_length=1, max_length=4000)]


def create_app(data_root=None, *, start_jobs=True):
    store = Store(data_root or os.environ.get('BLENDREMAKE_DATA', ROOT / 'data' / 'projects'))
    pipeline = Pipeline(store)
    auth_cache = {'time': 0, 'connected': False}

    @asynccontextmanager
    async def lifespan(app):
        if start_jobs:
            store.recover()
        yield
        pipeline.shutdown()

    app = FastAPI(title='BlendRemake', lifespan=lifespan, docs_url=None, redoc_url=None)
    app.state.store = store
    app.state.pipeline = pipeline
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=['127.0.0.1', 'localhost'])

    @app.middleware('http')
    async def local_boundary(request: Request, call_next):
        if request.method not in ('GET', 'HEAD', 'OPTIONS'):
            origin = request.headers.get('origin')
            expected = str(request.base_url).rstrip('/')
            if request.headers.get('x-blendremake') != '1' or (origin and origin != expected):
                return JSONResponse({'detail': 'Open BlendRemake locally to make changes.'}, status_code=403)
            try:
                length = int(request.headers.get('content-length', '0'))
            except ValueError:
                return JSONResponse({'detail': 'Invalid request length.'}, status_code=400)
            if length > media.MAX_BYTES + 1024*1024:
                return JSONResponse({'detail': 'Video exceeds 250 MB.'}, status_code=413)
            # Limit actual received bytes too, including chunked multipart requests.
            received = 0
            receive = request._receive
            async def bounded_receive():
                nonlocal received
                message = await receive()
                received += len(message.get('body', b''))
                if received > media.MAX_BYTES + 1024*1024:
                    raise HTTPException(413, 'Video exceeds 250 MB.')
                return message
            request._receive = bounded_receive
        response = await call_next(request)
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['Referrer-Policy'] = 'no-referrer'
        response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data: blob:; media-src 'self' blob:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        if request.url.path.startswith('/api/'):
            response.headers['Cache-Control'] = 'no-store'
        return response

    def get_job(job_id):
        try:
            return store.get(job_id)
        except (ValueError, FileNotFoundError):
            raise HTTPException(404, 'Project not found.')

    @app.get('/api/health')
    def health():
        if time.monotonic() - auth_cache['time'] > 30:
            auth_cache.update(time=time.monotonic(), connected=ai.connected())
        try:
            blender = bool(render.blender_binary())
        except ValueError:
            blender = False
        return dict(app='blendremake', version='0.2.0', blender=blender, codex=auth_cache['connected'],
                    ffmpeg=bool(shutil.which('ffmpeg') and shutil.which('ffprobe')), model=ai.MODEL)

    @app.get('/api/jobs')
    def list_jobs():
        return store.list()

    @app.get('/api/jobs/{job_id}')
    def read_job(job_id: str):
        return get_job(job_id)

    @app.post('/api/jobs', status_code=201)
    async def create_job(
        url: Annotated[str, Form(max_length=2000)] = '',
        brief: Annotated[str, Form(max_length=4000)] = '',
        start: Annotated[float, Form(ge=0, le=86400, allow_inf_nan=False)] = 0,
        duration: Annotated[float, Form(ge=.25, le=60, allow_inf_nan=False)] = 8,
        quality: Annotated[Literal['draft', 'standard'], Form()] = 'draft',
        audio: Annotated[bool, Form()] = True,
        review: Annotated[bool, Form()] = True,
        video: UploadFile | None = File(default=None),
    ):
        if bool(url.strip()) == bool(video and video.filename):
            raise HTTPException(400, 'Choose one reference: a video link or uploaded file.')
        if url.strip():
            try:
                media.validate_url(url.strip())
            except ValueError as error:
                raise HTTPException(400, str(error))
        if len(pipeline.tokens) >= 8:
            raise HTTPException(429, 'Eight projects are already queued. Wait for one to finish.')
        job = store.create(dict(title=Path(video.filename).name[:100] if video and video.filename else 'New reference',
            url=url.strip(), brief=brief, start=start, duration=duration, quality=quality, audio=audio, review=review))
        if video:
            dest = store.folder(job['id']) / 'source.bin'
            try:
                total = 0
                with dest.open('wb') as target:
                    while chunk := await video.read(1024*1024):
                        total += len(chunk)
                        if total > media.MAX_BYTES:
                            raise ValueError('Video exceeds 250 MB.')
                        target.write(chunk)
                if not total:
                    raise ValueError('The uploaded file is empty.')
            except Exception as error:
                dest.unlink(missing_ok=True)
                store.update(job['id'], status='failed', message=str(error))
                raise HTTPException(400, str(error))
            finally:
                await video.close()
        if start_jobs:
            pipeline.submit(job['id'])
        return store.get(job['id'])

    @app.post('/api/jobs/{job_id}/cancel')
    def cancel_job(job_id: str):
        get_job(job_id)
        pipeline.cancel(job_id)
        return {'ok': True}

    @app.post('/api/jobs/{job_id}/retry')
    def retry_job(job_id: str):
        job = get_job(job_id)
        if job['status'] in ('running', 'queued'):
            raise HTTPException(409, 'Project is already running.')
        pipeline.submit(job_id)
        return store.get(job_id)

    @app.post('/api/jobs/{job_id}/revise')
    def revise_job(job_id: str, body: Revision):
        job = get_job(job_id)
        if job['status'] in ('running', 'queued'):
            raise HTTPException(409, 'Wait for this job to finish before revising.')
        store.update(job_id, brief=body.brief)
        pipeline.submit(job_id, revise=True)
        return store.get(job_id)

    @app.get('/api/jobs/{job_id}/files/{name:path}')
    def files(job_id: str, name: str, download: bool = False):
        job = get_job(job_id)
        if name not in job.get('artifacts', {}).values():
            raise HTTPException(404, 'This artifact is not available.')
        folder = store.folder(job_id)
        path = (folder / name).resolve()
        if not path.is_relative_to(folder) or not path.is_file():
            raise HTTPException(404, 'This artifact is not available.')
        return FileResponse(path, filename=path.name if download else None)

    @app.get('/')
    def index():
        return FileResponse(ROOT / 'web' / 'index.html')

    app.mount('/static', StaticFiles(directory=ROOT / 'web'), name='static')
    return app


app = create_app()
