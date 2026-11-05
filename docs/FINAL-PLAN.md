# Final plan: frame-accurate reconstruction

Written 2026-09-13, revised the same day after checking every assumption against the repo, the reference, and the machine. The previous direction ("better assets and repeated calibration") had no order, gates, or definition of done. This plan does.

## Status (2026-09-13)

**Superseded status:** The current user-approved target is the existing splinter video, beginning with original frames **420–449**, followed by all **910 frames**. The earlier owned-clip restriction and pilot range below do not apply. Captions are reconstructed as editable text; source pixels are not used as scene textures. See [current implementation and remaining work](IMPLEMENTATION.md). The pilot remains approximate and has not passed visual acceptance.

- **Phase 0: done.** Preview/final pipeline finished and wired to the frame audit; 60 tests pass.
- **Phase 1: partly done.** Scoring, decode, worst-tile metrics, calibration, and the project-page score are built and proven on original content. Object masks, LPIPS, and a usable motion gate remain. Evidence in [FIDELITY-LOG.md](FIDELITY-LOG.md).
- **Target changed.** The pilot and segment grind (Phases 2 and 6) run on original or owned clips, not the splinter Short. A frame-for-frame rebuild of another creator's video is a copy of their work. Wherever this plan says "splinter" as the thing to match, read "a representative owned clip"; the splinter measurements above remain useful as a description of what hard material looks like.
- **Next:** pick an owned clip (for example one of the maintainer's own 3D or motion-graphics renders), recalibrate on it, then run the Phase 2 pilot on one second of it.

## Facts this plan is built on (measured, not assumed)

| Fact | Value | Why it matters |
| --- | --- | --- |
| Reference stream | H.264 1080×1920, 30000/1001 fps, 910 frames, yuv420p, **BT.709 limited (tv) range**, ~1.84 Mbps | Comparisons must decode color correctly and account for YouTube compression softening |
| Reference style | Stylized glossy CG: blue gradient background, shallow depth of field, dense thin detail (vessels, nerves, cell rows, fat lobules), yellow particles, word-group captions | Fine random detail is the hardest part to match; see Phase 4 |
| Captions | 2D overlay. During the card flip (frames 150–155) the captions stay flat while the picture rotates | Captions are a separate screen layer, not scene text |
| Card flip | Picture on a rotating plane over black, with motion blur, frames ~146–161 | Needs pre-rendered shot faces, not a cut |
| GPU | GTX 1650 SUPER, 4 GB | Limits fitting models and render speed |
| Disk | 41 GB free on C: (92% full) | A native PNG render is ~3–4 GB; iterations must be pruned |
| Render speed | Last Eevee render: 729 frames at 406×720 in ~14 min (≈1.15 s/frame) | Native 1080×1920 estimate: 5–10 s/frame, 1.3–2.5 h for 910 frames |
| Tests | 47 pass, 4 fail. Three fail because `app.pipeline` never imports the new `app.reference` audit; one because the 8-job queue cap isn't implemented | Phase 0 is *finishing wiring*, not fixing tests |
| Geometry | `app/geometry.py` and `app/anatomy.py` produce vertices and faces in plain Python before Blender runs | Silhouette fitting can run without Blender, which is far faster |
| Frame audit table | Ranges have gaps (294–309, 481–491) and an overlap (240–248) | Segments must be re-cut into a contiguous partition first |

## What "1:1" means here

A pixel-identical copy is not a reachable or testable goal for a rebuilt 3D scene. Two different renders of "the same" skin texture never align pixel-for-pixel. Setting a per-pixel gate like SSIM ≥ 0.90 would force the only thing that can pass it: copying source pixels.

So "1:1" is defined as:

1. **Timing exact:** same frame count and rate; every cut, transition, grasp, release, and caption change on the same frame.
2. **Layout exact:** every visible object in the same place, size, silhouette, and pose on every frame, within the gates below.
3. **Look indistinguishable at playback:** color, lighting, focus, texture, and motion pass the calibrated perceptual gates.
4. **the maintainer watches it and can't tell.** Agents produce evidence; only the maintainer's viewing counts as the visual pass. (Agents have over-claimed visual quality on other projects.)

### Hard rules

- The remake is built from geometry, materials, lights, and animation. Source pixels are never used as textures, projections, compositor plates, or fallback frames. The validator rejects any texture that perceptually matches a source frame. A pixel-copying remake is a fake pass.
- The model never writes executable Python; new abilities go into the trusted schema and compiler.
- Thresholds are frozen after calibration. A failing segment is fixed, never passed by loosening a gate.
- **Third-party references (including the splinter Short) are private local benchmarks.** They measure the engine. Their remakes stay on this machine: exports carry no source audio, and captions are masked out of scoring instead of retyped. The output the engine is built to ship is reconstruction of footage the maintainer owns (Phase 7).

---

## Phase 0: Finish what's half-built (1 day)

1. Confirm nothing else is editing the repo. A Codex session started 2026-09-13 18:24; repo files haven't changed since 2026-09-12 11:16, so it's likely elsewhere, but check before committing.
2. Wire `app.reference` into `app/pipeline.py` (the full frame audit → contact sheets → `ai.observe` → `ai.generate(observations=...)`), and add the 8-job queue cap. That makes the 4 failing tests pass for the right reason.
3. Commit the observation pipeline as one reviewed change.
4. Re-cut the frame audit into a contiguous segment partition (resolve 240–248, assign 294–309 and 481–491) from the existing per-frame change/flow data, and save it as `data/references/splinter/segments.json`. Segments follow camera continuity; action ranges become keyed events inside them.
5. Re-render the existing splinter plan at native 29.97 fps, 910 frames. This is the "before" baseline.

**Exit:** 51/51 tests pass; baseline has exactly 910 frames; segments cover 0–909 with no gaps or overlaps.

## Phase 1: Fidelity harness (3 days), before any new art

Nothing gets improved until it can be measured correctly.

### 1a. Decode correctly

- Read source frames straight from `source.mp4`, never from the JPEG contact-sheet frames (JPEG adds its own artifacts).
- Convert BT.709 limited range → full-range RGB with an explicit ffmpeg filter; verify with a known gray.
- Before scoring, encode each render through H.264 at the source bitrate (~1.84 Mbps, yuv420p, BT.709 tv) and decode it back. Otherwise the render loses points only for being sharper than YouTube's copy. Score both versions; gate on the encoded one.

### 1b. Metrics, multi-scale on purpose

| Level | Measure | What it catches |
| --- | --- | --- |
| Timing | Frame count, per-frame change curve vs. source (cross-correlation), transition frames | Late/early events, missing cuts |
| Layout | Mask IoU per tracked object (SAM 2 small, video mode, CPU-offloaded state), tracked point error, blob positions for particles | Wrong place/size/shape/pose |
| Coarse look | SSIM and CIEDE2000 on 1/8-scale blurred frames, per-mask mean color | Wrong color, lighting, exposure, focus |
| Fine look | LPIPS (AlexNet) on the full frame and per mask; texture-statistics distance (Gram matrix) inside texture regions | Wrong texture character, gloss, grain |
| Motion | RAFT-small optical flow, endpoint error between source flow and render flow at 540 px | Wrong speed, easing, drift |
| Stability | Render change curve vs. source change curve | Flicker, pops |

Captions are masked out of every metric on third-party references.

### 1c. Calibrate thresholds (then freeze them)

Measure what *invisible* differences score, using the source against slightly altered copies of itself: 1 px shift, 0.5 px blur, re-encode at 80% bitrate, +1% exposure, 1-frame offset. That gives a noise floor for each metric. Separately, render the same Blender scene twice with different sampling seeds. Set each gate just above the larger of those floors, inspect the heatmaps at those levels with the maintainer, then freeze the numbers in `app/fidelity_gates.json`.

The earlier fixed numbers (LPIPS ≤ 0.10, SSIM ≥ 0.90, IoU ≥ 0.95, ΔE ≤ 5, ≤ 19 px, flow ≤ 2 px) are starting guesses only; calibration replaces them.

### 1d. Evidence output

- `fidelity.json` per render: every metric per frame, per segment, pass/fail, worst 20 frames.
- Review video: source | render | difference heatmap | mask overlay, with frame numbers. This is what gets looked at.
- `scripts/fidelity_check.py PROJECT_ID [--segment N]`.

**Exit:** a remake scored against itself passes perfectly; each deliberate perturbation fails on the right metric; the Phase 0 baseline has a per-segment score.

## Phase 2: Pilot one second before building everything (3–4 days). Go/no-go.

The full plan is weeks of work. Prove the method can actually reach the gates on a small, representative piece first.

**Pilot range:** cutaway frames 162–191 (1 s). Camera nearly still, and it contains the hardest recurring material: glossy tissue, cell row, hair follicles, thin vessels/nerves, fat lobules, blue background, depth of field.

Do it with whatever mix of fitting and hand work gets there, and record everything that had to be done by hand. Outcomes:

- **Passes:** the method works; the hand steps become the automation list for Phase 4; the time taken sets the real schedule.
- **Layout passes, look fails:** the ceiling is material/asset quality; extend Phase 5 before scaling.
- **Layout fails:** the representation is wrong (for example, needs traced detail geometry); fix Phase 3 before anything else.

**Exit:** a written go/no-go in `docs/FIDELITY-LOG.md` with the pilot's scores and a timeline re-estimate.

## Phase 3: Schema and compiler upgrades (5–7 days)

Each item ships with a contract test and a renderer test, and must stay editable in the exported `.blend`.

1. **Dense animation tracks.** Per-frame values for any animatable property (transform, shape key, bone, light, lens, focus, material scalar). Sparse keys can't hold fitted motion.
2. **Armatures.** Bones, rest pose, per-frame rotations, automatic skin weights in the trusted compiler. For finger curl and tweezer jaw flex.
3. **Traced detail geometry.** Curves and instanced blobs placed from measured 2D positions lifted onto a fitted surface (see Phase 4.2). Needed because vessel, nerve, cell, and particle layouts must match element by element; a random procedural pattern never will.
4. **Trusted asset import.** GLB/FBX only from an allowlisted `assets/` folder, each with a provenance file (source, license). Plans can't fetch anything.
5. **Image textures (non-source).** Authored, generated, or licensed only, with provenance and the perceptual-hash check against source frames.
6. **Transitions.** Card flip: pre-render the outgoing and incoming shot faces, map them onto a rotating plane over black, with motion blur. Also cross-dissolve and continuous surface ↔ cutaway morph (animated cut plane plus shape keys). Pipeline renders dependency shots first.
7. **Caption layer.** Screen-space text strips (font, size, stroke, shadow, anchor, per-frame visibility) composited after the 3D render. Text comes from the user's own script. Not used on third-party benchmarks.
8. **Lens and film.** Animated focus distance and f-stop, motion blur, grain, vignette, view transform/look/exposure.
9. **Particles as tracked instances.** Each particle is an instance with its own per-frame position/scale track (from Phase 4.3), not a random emitter.
10. **Persistent Blender worker.** One long-running repository-owned Blender process that accepts validated param patches and renders a frame or crop over a local socket. It avoids ~5 s startup per evaluation. It accepts data only, never code.

**Exit:** a test scene using every feature renders, exports, reopens editable, and rebuilds from the ZIP.

## Phase 4: Measure-and-fit tooling (6–8 days)

Fitters turn measurements into scene values and write them back into the validated plan with a before/after report. Run per segment in this order; each stage locks before the next.

1. **Camera.** Only relative camera-to-object motion is visible, so fix a convention: static set, moving camera, unless an object visibly moves against its surroundings. Solve focal length and pose from tracked points on static features (OpenCV PnP once rough 3D positions exist; Blender's tracker where there's parallax). Zoom vs. dolly is decided by perspective change across the segment, not per frame.
2. **Surfaces and silhouettes.** Fit asset recipe parameters (finger profile, shard shape, tweezer dimensions, layer thicknesses, swelling shape) by projecting the Python-generated geometry through the camera and rasterizing masks with OpenCV. No Blender needed, so thousands of evaluations are cheap. Finish with a few Blender Workbench renders to account for bevel/subdivision.
3. **Traced detail.** Segment thin structures (vessels, nerves, cell outlines, lobules) by color/edge in the source at their clearest frame, skeletonize to centerlines, and lift them onto the fitted section surface as curves with measured widths. Track them through the segment to follow camera drift and deformation. This is the step that makes dense detail match; it's geometry from measurement, not copied pixels.
4. **Particles.** Detect yellow blobs per frame (color threshold plus blob detection), link them across frames (Hungarian assignment with motion prediction), handle births and deaths, and write per-instance tracks.
5. **Pose and motion.** Rigid tools: per-frame 6-DoF from point tracks, smoothed with a small jerk penalty. Finger and jaws: per-frame bone/shape-key values fitted to mask contours, warm-started from the previous frame. No MediaPipe: it's unreliable on CG close-ups of a single finger. Human-clicked landmarks on a few key frames are allowed where tracking fails, and are logged.
6. **Materials and lighting.** With layout locked, fit base color, subsurface, roughness, clearcoat, pattern scale, and light energy/color/position against coarse ΔE plus masked LPIPS, rendering 270×480 crops in the persistent worker. CMA-ES (`cma`, BSD) or Optuna. Budget: ~1,800 evaluations × 4 frames × ~0.3 s ≈ 35 min per material group.
7. **Lens and film.** Fit focus and f-stop to blur-sensitive regions, then grain and view transform to fine-look metrics.
8. **Timing snap.** Put every event on its audited frame.

**Exit:** on the pilot range, running the fitters unattended matches or beats the hand-made pilot result.

## Phase 5: Asset quality (in parallel with Phase 4, 5–8 days)

Fitters can only reach what assets can express. Priorities come from the pilot's worst metrics, but expected:

1. **Tissue:** wet clearcoat, layered subsurface, cell-row geometry driven by traced outlines, swelling color gradient tied to the swelling shape key.
2. **Finger/hand:** a licensed or CC0 rigged base mesh (checked license, logged provenance), nail and crease detail, subsurface skin.
3. **Wood, shard, tweezers:** textures with provenance, bevels and wear, shard fibers.
4. Versioned recipes so old plans still compile.

**Exit:** each asset, fitted alone on its clearest reference frame, passes the frozen layout and look gates.

## Phase 6: Segment loop (main grind; length set by the pilot)

For each segment in `segments.json`, cutaway-heavy segments first (they share the most assets and cover ~45% of the video):

1. Build from fitted outputs; run fitters.
2. Render at 540 px, score.
3. If failing: send the worst 5 frames' heatmaps and metric table to Astra via the existing Codex bridge and ask for a **diagnosis as structured data** (which object, which parameter group, which frames, which direction). Astra diagnoses; fitters change numbers. Apply only schema-valid changes. Cap 8 iterations.
4. Still failing: log the concrete blocker in `docs/FIDELITY-LOG.md`, fix the capability or asset, resume. Never lower the gate.
5. Passing: render native 1080×1920, score again, lock the segment.
6. Continuity: each boundary frame is scored in both adjacent segments with shared asset instances.

Storage: keep only the current iteration's frames and locked native renders; delete older iteration frames after scoring (reports stay). Check free space before each native render and stop below 10 GB.

**Exit:** every segment locked at native resolution.

## Phase 7: Full-video acceptance

1. One editable Blender project, one timeline, all segments.
2. Final render: 910 frames, 1080×1920, 30000/1001 fps (overnight).
3. Harness on the full render: every frame passes every frozen gate.
4. **the maintainer's review:** side-by-side at 1×, at 0.25×, then an A/B flip on 20 random frames. Any visible difference sends that segment back to Phase 6.
5. Engineering: `.blend` reopens with everything editable; ZIP rebuilds independently; the anti-copy texture check passes; export contains no source audio.
6. Update `docs/ACCEPTANCE.md` with the real numbers.

## Phase 8: Automatic for new videos, gated on footage the maintainer owns

Splinter gets there with a human-assisted loop. One-click 1:1 on arbitrary video is a research-grade problem; treat each step as unproven until measured.

1. Wire audit → segments → tracks → fitters → segment loop → final render → acceptance report into `app/pipeline.py`, with per-segment caching and retry.
2. UI: per-segment pass/fail, heatmap review video, iteration log. A job says "1:1 pass" only when Phase 7 criteria pass; otherwise "approximate" with failing segments listed. Verify desktop + narrow screenshots.
3. Benchmark set, all through the same frozen harness:
   - 2–3 clips the maintainer owns (his own motion-graphics or 3D renders). These are the gating benchmarks and the legitimate output case.
   - One synthetic Blender scene with exact ground truth (regression guard).
   - The splinter Short (private stress test).
4. Success = a new owned clip of similar complexity reaches "1:1 pass" with no hand-authored steps.

---

## Order and schedule

| Step | Estimate |
| --- | --- |
| Phase 0 | 1 day |
| Phase 1 | 3 days |
| Phase 2 pilot + go/no-go | 3–4 days |
| Phases 3–5 | ~3 weeks (parallel where possible) |
| Phase 6 | Set by the pilot; rough guess 2–3 weeks |
| Phase 7 | 2–3 days |
| Phase 8 | 2+ weeks |

Only the first three phases are estimated with confidence. The pilot replaces the rest of this table with measured numbers.

## Risks

- **Organic realism is the ceiling.** Wet tissue and skin are the hardest CG. If assets can't reach frozen gates, the log says so plainly.
- **Dense detail.** Matching every vessel and particle is labor-intensive even with tracing; the pilot measures how much.
- **4 GB GPU.** SAM 2 small with CPU offload and RAFT-small fit; large segmentation or image-to-3D models don't. Fitting avoids Blender wherever possible.
- **Disk.** 41 GB free. Pruning in Phase 6 is mandatory, not optional.
- **Dependency licenses.** OK: SAM 2 (Apache 2.0), RAFT/torchvision (BSD), LPIPS (BSD), `cma` (BSD), Optuna (MIT). Avoid: CoTracker (non-commercial), MANO-based hand models (restricted).
- **Publishing.** A 1:1 remake of someone else's video is still their video. Third-party remakes stay local; the engine and the maintainer's own clips are what ship.
