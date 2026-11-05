# BlendClone reconstruction implementation

Current target: visually indistinguishable, editable reconstruction of the existing splinter reference. Work stays local. First accept original frames 420–449, then extend through all 910 frames. A rendered frame or passing test is not a visual pass.

## Implemented

- Validated frame-indexed scene contract: rational rate, explicit frame count, transform tracks, absolute mesh samples, per-face materials, animated material colors, caption intervals.
- Native Blender compilation and export retain geometry, shape keys, object animation, camera animation, material animation, and packed caption font. Renderer choice is pinned across preview and export.
- Source manifest records SHA-256, presentation timestamps, native dimensions, color metadata, and 14 consecutive segments covering every source frame.
- Pilot measures upper/lower tissue boundaries, tissue motion, and 60 particle tracks across all 30 frames. It drives editable mesh deformation and objects; source frames are not textures.
- Persistent owned Blender worker reuses a loaded scene for material/light fitting. Parameter search retains only measured improvements. The current material fit still has substantial error.
- Measured scene revisions request bounded parameter changes instead of sending dense geometry to the model. Revision validation preserves mesh samples and existing tracks.
- Review page includes every pilot frame, side-by-side source/render/difference, seeking, quarter speed, and flicker comparison. The app shows incomplete coverage and pending visual acceptance.
- Export verification reopens the actual Blender file, checks rational timing within Blender storage precision, sampled control-mesh deformation, material color animation, transform samples, and packed caption font.

## Reproduce

From the repository, with the existing reference and hero project available:

```powershell
.venv/Scripts/python.exe scripts/benchmark_manifest.py
.venv/Scripts/python.exe scripts/reconstruction_pilot.py --prepare-only
.venv/Scripts/python.exe scripts/fit_pilot_materials.py
.venv/Scripts/python.exe scripts/render_pilot.py --quality standard
.venv/Scripts/python.exe scripts/score_pilot.py
.venv/Scripts/python.exe scripts/publish_pilot.py
.venv/Scripts/python.exe scripts/browser_pilot_check.py
.venv/Scripts/python.exe -m pytest -q
```

Rendering creates a new directory under `outputs/reconstruction-pilot/renders/`. `finished-render.json` identifies the last successfully verified and packaged render; `published-job.json` identifies its library entry. `acceptance.json` contains every frame's diagnostics, actual resolution, limitations, and an explicit false visual-acceptance flag. Standard renders are 404×720; native final output is 1080×1920. Standard renders cannot establish native-resolution acceptance.

## Remaining gates

1. Correct pilot anatomy, material/reflection appearance, particle shape/occlusion, and provisional lower-boundary measurements. Inspect all 30 frames; current appearance is visibly approximate.
2. Replace partial outline diagnostics with validated per-object masks/landmarks and calibrated appearance/motion gates. Current contour threshold can confuse hair occlusion with a boundary; reported outliers must remain visible until measurement is corrected.
3. Render the corrected pilot at native resolution and obtain visual acceptance. No full-video grind before this gate.
4. Reconstruct all remaining segments, exact captions/actions, card-flip transition, and camera motion. Verify all 910 frames at 30000/1001 fps.
5. Extend reusable assets/rigs and arbitrary-video fitting; prove generalization on separate clips.

The benchmark scripts currently depend on this reference and its existing authored hero scene. They are not an automatic 1:1 solution for arbitrary uploads. No full-video completion is claimed.

## Verified result

- Local library job: `41b0b77b0f20`; app at `http://127.0.0.1:4331/#41b0b77b0f20`.
- Render: `outputs/reconstruction-pilot/renders/edaaa34148c2`, 30 frames at 404×720, exact export rate 30000/1001.
- Native verification: 660 sampled control-mesh vertices, 120 material-color samples, transform tracks, nine caption layers, packed font.
- Portable ZIP rebuilt independently in `outputs/export-check-62bcd041`; rebuilt file reopened and passed the same native checks.
- 158 backend tests pass. Five responsive browser widths pass. Real pilot seeking, flicker, quarter speed, asset loading, and desktop/mobile layout pass; screenshots inspected.
- Upper-boundary diagnostic mean 1.32 source pixels, worst 88 pixels; mean color delta E 15.74. These are partial diagnostics, not calibrated acceptance gates. Materials, anatomy, and particle segmentation visibly differ. Visual acceptance remains false.
