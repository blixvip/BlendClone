# BlendRemake

Turn a reference video into an **editable Blender reconstruction**. Import a public video link or file, select a short section, rebuild its scene with Astra, compare the render, and export a `.blend`, MP4, comparison MP4, or complete project ZIP.

This is a separate local Windows app and repository. It does not import, modify, or require MotionClone.

## What the first version does

- Imports YouTube, Vimeo, and X links through yt-dlp, or local MP4/MOV/WebM files.
- Selects a 0.25–30 second section, starting at any valid source timestamp; defaults to 8 seconds.
- Samples timestamped frames, including extra samples around strong visual changes.
- Uses `gpt-6-astra` through the official Codex CLI and your ChatGPT login to describe geometry, materials, cameras, lighting, shot boundaries, and animation.
- Compiles validated scene data into native Blender objects. No model-authored Python executes.
- Optionally compares source/rendered frames at matching timestamps and performs one correction pass.
- Renders 24 fps with Cycles; draft has a 432-pixel longest edge, standard 720. Cycles GPU is selected when available, with CPU fallback.
- Saves projects and job status locally; supports cancellation, retry, and natural-language revisions.
- Plays the original and remake together, with shared seeking, speed, and audio controls.
- Exports native `.blend`, rendered MP4, side-by-side comparison, and a project ZIP with the scene JSON and standalone Blender compiler.

## Quality limits

This is an experimental reconstruction app, not an original-project recovery tool. Astra infers unseen geometry, lighting, and motion from sampled images. A successful render does not demonstrate visual similarity.

Version 0.1 supports primitives, custom meshes, tube curves, text, materials, bevel/subdivision modifiers, object parenting, transform keyframes, camera targets, lights, and shot cuts. Parent joints allow simple articulated movement. It **does not yet support** imported character assets, skinned rigs, facial animation, shape-key deformation, physics simulation, image textures, or asset search. Complex anatomy and character scenes will be approximate. These are consequential limits for Zack D. Films-style videos.

Start with one 5–10 second object/camera shot and compare the result. Improving recognizable 3D assets and deformable characters is the next major quality step. Do not advertise unattended creator-level fidelity based on the synthetic test.

## Run

Install Python 3.12, Blender 5.1+, FFmpeg/ffprobe, and the official Codex CLI. Run `codex login` using your ChatGPT account.

```powershell
.\start.ps1
```

The launcher creates its own environment when needed and starts the app at **http://127.0.0.1:4327**. It opens the browser and leaves the server running hidden. It never closes or restarts Warp or any unrelated application.

Manual setup:

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.lock.txt
.venv\Scripts\python.exe -m uvicorn app.server:app --host 127.0.0.1 --port 4327
```

Optional environment variables:

| Variable | Default | Purpose |
| --- | --- | --- |
| `BLENDER_PATH` | Detect installed Blender | Full path to Blender executable |
| `BLENDREMAKE_MODEL` | `gpt-6-astra` | Model available through your Codex account |
| `BLENDREMAKE_DATA` | `./data` | Project storage directory |

## Privacy and execution

Source videos, rendered media, scene data, logs, and project state stay under the configured data directory. Selected source frames and review renders are sent through Codex for model analysis. Video-link imports contact the source platform. This is not an offline-only app. Generated projects and diagnostic logs are excluded from Git.

Only repository-owned Blender Python executes. Scene output is a Pydantic-validated declarative specification, with bounded objects, geometry, keyframes, references, and durations. It cannot request filesystem access, shell commands, imports, downloads, or process cleanup. The app binds to loopback, restricts Host and Origin, checks mutation headers and upload sizes, and exposes only named artifacts. It is a **local single-user app**, not a hardened public hosting service.

Downloads contain no credentials or prompt logs. Project ZIPs exclude the original video and reference frames. A standalone `.blend` contains editable scene objects and animation; retained source audio is included in MP4 exports, not the `.blend`.

Jobs run one at a time. Cancellation signals only the exact child process created for that step. Server restarts mark unfinished jobs interrupted; retry reuses a saved validated plan. A revision requests a fresh plan. Completed frame directories are retained locally for inspection and re-encoding, so long renders can consume substantial disk space.

## Verify

```powershell
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe scripts\renderer_check.py
.venv\Scripts\python.exe scripts\browser_check.py
```

The renderer check builds a synthetic two-second ball-drop scene, renders native Blender frames, verifies frame count/duration, and encodes the remake and comparison. Browser checks use installed Chrome and the running local app, and cover five widths plus import, loading/error/success, retry, playback, and revision. HTTP fixtures avoid additional AI work; screenshots go to `outputs/`.

Optional **live Astra** check, using the synthetic reference created above:

```powershell
.venv\Scripts\python.exe scripts\ai_check.py
```

This submits a real reconstruction and review through the connected ChatGPT account, uses account allowance, saves a project in the app library, and checks all downloads. Inspect its comparison visually. It is not a benchmark for real creator footage.

Run `.venv\Scripts\python.exe scripts\export_check.py PROJECT_ID` for a completed local project to rebuild its ZIP in a separate directory, reopen the `.blend`, and capture the actual comparison.

## Repository

| Path | Purpose |
| --- | --- |
| `app/models.py` | Validated scene contract and timing rules |
| `app/ai.py` | Astra analysis, correction prompts, Codex bridge |
| `app/blender_scene.py` | Deterministic JSON-to-Blender compiler |
| `app/media.py` | Link imports, video normalization, frame sampling |
| `app/render.py` | Blender execution, video and comparison encoding |
| `app/pipeline.py` | Persistent job orchestration, retry, export packaging |
| `app/server.py` | Local HTTP application and input boundaries |
| `web/` | Import, library, comparison, and revision workspace |
| `examples/` | Small declarative scene examples |
| `tests/`, `scripts/` | Contract, API, renderer, and browser checks |

See [Architecture and next steps](docs/ARCHITECTURE.md) and [Acceptance evidence](docs/ACCEPTANCE.md).
