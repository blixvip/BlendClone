# Acceptance evidence

Verification date: 2026-09-11 (America/Edmonton).

## Verified foundation

- All 16 contract, local HTTP, and process tests passed: scene timing, invalid geometry, cyclic parenting, nonfinite input, persistence, interrupted jobs, input boundaries, source upload isolation, artifact restrictions, owned-child cancellation, and timeouts.
- Blender 5.1 rendered a native two-second synthetic scene on GPU: three meshes, one camera, 48 frames at 24 fps, and five animated objects.
- The generated `.blend`, animation MP4, and comparison MP4 were produced by the real Blender/FFmpeg pipeline.
- Browser checks passed at 320, 390, 768, 1024, and 1440 px with no page errors or horizontal overflow. Upload controls, loading/error/success states, retry, synchronized playback, seeking, layout switching, and revision were exercised. Actual desktop/mobile screenshots were visually inspected.
- The dependency lock passed `pip check` and `pip-audit` reported no known vulnerabilities.

## Live Astra reconstruction

The app submitted the two-second synthetic ball-drop video through the real Codex/Astra bridge. Astra generated an independent three-mesh scene, reviewed source/render pairs, and revised the reconstruction. Blender rendered all 48 frames, and all four downloads returned valid files.

The ZIP was extracted into a separate directory. Its standalone compiler rebuilt the native scene and rendered a preview with no app imports. The exported `.blend` reopened successfully with a camera, objects, timeline, and animation intact.

Visual inspection of the actual comparison found the ball, plinth, overall composition, light direction, and bounce recognizable. Material colors, light falloff, plinth shape, framing, and motion still differ from the synthetic reference. This is a successful approximate reconstruction of a simple shot, not proof of arbitrary video fidelity.

Screenshots and rendered acceptance artifacts are local under `outputs/` and excluded from Git. Live AI jobs live under `data/` and are also excluded.

## Fidelity boundary

The synthetic fixture verifies editing and rendering. It does not establish reconstruction fidelity on Zack D. Films or other creator footage. A representative user-provided reference remains necessary for that evaluation.
