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

## Complex supplied reference: splinter Short

The user supplied Zack D. Films' `yGw0nhlUtkQ`. Its real 1080×1920, 30.363667-second video and audio were downloaded and inspected. The revised app download helper was separately exercised against that URL; split video/audio merging succeeded.

The reference-specific authored plan contains seven shots covering 30.375 seconds after 24 fps normalization. Native Blender inspection confirmed 468 objects, 122 meshes, seven cameras, 264,335 mesh vertices, four shape keys, and a 729-frame timeline. Direct inspection verified independent shape-key bases, increasing surface swelling, upward extraction, and camera switching. The scene uses Eevee.

All 23 current tests passed, including split-stream imports, full Short duration, mesh construction, deformation, material bounds, and subprocess progress. Browser verification again passed at five widths, with actual desktop/mobile screenshots inspected.

The normal app retry pipeline rendered all 729 frames. The remake is 406×720; the synchronized comparison is 812×720. Both are 30.375 seconds with source audio. All four HTTP downloads matched their files on disk. The 8.3 MB ZIP rebuilt independently in `outputs/export-check-44807d64`, and its `.blend` reopened successfully. The real comparison was inspected in desktop and mobile screenshots. The local completed project is `cc2d3dc22850` on port 4328.

The benchmark was manually authored and visually calibrated by the agent using reusable procedural assets. It was not an unattended Astra generation. See [shot details and observed differences](SPLINTER-BENCHMARK.md).

## Fidelity boundary

The synthetic fixture verifies automatic planning, editing, and rendering for a simple scene. The complex reference demonstrates anatomical scene construction and deformation, with visible differences in modeling, shading, framing, and motion. Neither establishes automatic creator-level fidelity. Further quality gains require better assets and repeated visual calibration against real footage.
