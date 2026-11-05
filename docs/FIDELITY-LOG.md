# Fidelity log

Evidence only. Newest first.

## BlendClone: native resolution, persistent renderer, measured outline pilot

User requested the BlendClone name and renewed the 1:1 target. No new reference was supplied; the existing splinter benchmark was used for this local experiment.

- New imports retain native dimensions; final renders use reference dimensions. Before: 1080x1920 became 608x1080 at import and final. Previously cached references remain unchanged.
- Scene plans now save the selected Cycles/Eevee engine through asset expansion, preview, final and export.
- The one-frame pilot at original frame 420 (14.014 s) fits the upper skin outline as editable mesh geometry. No source pixels are embedded in the Blender scene.
- Verified before/after renders: mean outline error 35.00 -> 3.47 original pixels; maximum 197.33 -> 26.67. Metric covers the central 90% of the upper outline using the same benchmark-specific segmentation on both renders. It excludes all other geometry and appearance.
- Visually inspected `outputs/cutaway-fit/comparison.png`: outline improves; skin highlights, internal structures, particle appearance and placement, lower skin boundary, and background still differ substantially. No full motion reconstruction or 1:1 pass is claimed.
- Both renders used Cycles GPU, 99 objects, 154075 vertices. Script: `scripts/fit_cutaway.py`. Artifacts: `outputs/cutaway-fit/{before,after}/remake.blend`, plus report and comparison image.

## 2026-09-13: harness built, calibrated on original content

### Pipeline (Phase 0)

- `app/pipeline.py` now runs preview and final as separate phases in immutable `runs/<id>/` folders. A failed run never replaces the last good downloads; unreferenced runs are pruned.
- The full frame audit (`app/reference.py`) and sequence observations (`ai.observe`) are wired into the preview phase. The final phase reuses the reviewed `plan.json` with no model calls.
- The 8-project queue cap is enforced in `Pipeline.submit`.
- Tests: 60 pass (51 existing including the 4 that were failing, plus 9 new fidelity tests). One test fixture was fixed to write `plan.json` as UTF-8, matching the app.

### Harness (Phase 1, partial)

`app/fidelity.py` scores every frame after each final render and writes `fidelity.json`; the project page shows the verdict.

- Decode: both videos go through one explicit range/matrix conversion; the render is first encoded at the reference bitrate.
- Per frame: coarse structure (SSIM, worst tile of a 6-column grid), color (CIEDE2000, worst tile), motion (DIS optical-flow difference, worst tile), plus full-frame SSIM for information.
- Timing: frame count, fps, and change-curve lag must match exactly.
- CIEDE2000 matches 5 published Sharma et al. reference pairs to 1e-4.

**Whole-frame averages were wrong.** First run: a ball recolored coral → blue passed 44/48 frames because the ball is a small part of the frame. Switching to worst-tile scoring made it fail 48/48.

### Calibration (`scripts/calibrate_fidelity.py`)

Invisible changes on the synthetic ball-drop reference, worst frame:

| Change | Coarse SSIM | ΔE | Flow |
| --- | --- | --- | --- |
| Identical re-render | 0.974 | 2.65 | 8.74 |
| Re-encode at 80% bitrate | 0.950 | 2.79 | 7.12 |
| +1% brightness | 0.952 | 0.84 | 1.83 |
| 0.5 px blur | 0.998 | 0.70 | 1.37 |

Frozen gates (floor × 1.25): coarse SSIM ≥ 0.9381, ΔE ≤ 3.483, flow ≤ 10.919, lag = 0.

Sensitivity check under those gates: identical rebuild 48/48 pass; ball moved 0/48; recolored 0/48; bounce 3 frames late fails timing (lag −3).

### Open problems found

1. **Motion gate is too loose to matter.** Compression noise on the fast bounce pushes worst-tile flow error to ~9 px even for an identical render, so the gate sits at 10.9. Timing lag, not flow, caught the late bounce. Needs flow measured only on textured regions, or per-object tracks.
2. **Renderer must be matched.** The same ball-drop plan rendered through the app picked Cycles (no assets) while the reference was Eevee. It scored 0/48 (worst layout 0.840). Frame 8 confirms a visible difference: hard contact shadow and darker ball shading in Eevee versus soft Cycles lighting. Engine and sampling are fidelity parameters, not defaults.
3. **Calibration is content-specific.** Floors come from a simple synthetic scene. Recalibrate on a representative owned clip before trusting a pass on dense or glossy material.
4. **Not yet measured:** per-object masks, a learned perceptual metric (LPIPS needs torch), per-object tracks.

### Scope decision

The frame-accurate rebuild target is no longer the Zack D. Films splinter Short. Matching another creator's video frame for frame, including tracing their exact vessel layouts and particle positions, produces a copy of their work. The engine is developed and gated on original content (the synthetic scenes) and on clips the maintainer owns. The splinter project stays as-is from earlier work.
