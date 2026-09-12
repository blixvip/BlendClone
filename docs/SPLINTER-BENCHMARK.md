# Splinter reference benchmark

Reference: Zack D. Films, [How Splinters Get Unstuck](https://www.youtube.com/shorts/yGw0nhlUtkQ). Source duration 30.363667 seconds; normalized output 30.375 seconds at 24 fps.

This is a reference-specific reconstruction authored by the agent after inspecting the actual video at multiple timestamps. It is not a fresh, unattended run of the app's Astra scene-generation prompt. The reusable asset recipes and compiler capabilities are available to that prompt.

## Shot plan

| Time | Rebuilt content |
| --- | --- |
| 0–0.7 s | Hand against weathered wood |
| 0.7–1.7 s | Raised index finger and exposed shard |
| 1.7–5.1 s | Finger close-up and shallow extraction |
| 5.1–7.7 s | Layered skin cutaway and embedded splinter |
| 7.7–12.8 s | Skin surface, failed reach, growing swelling |
| 12.8–23 s | Deforming skin cap, particles, pressure arrows, rising shard |
| 23–end | Swelling subsides and tweezers extract the shard |

The assets are ordinary editable geometry: layered epidermal cells, dermis, fat lobules, branching vessels and nerves, follicles and hair, skin surface, hand, finger, wood, and tweezers. Swelling uses animated native shape keys. Camera changes and timing are explicit, with original audio retained in the video exports.

## Visual observations

The cutaway carries the main anatomical structure and action of the reference. The hand is visibly procedural; it lacks sculpted joints, integrated anatomy, and fine skin detail. Skin cells, tissue color, highlights, particles, camera framing, and extraction trajectories still differ. The surface texture is an approximation. The original captions and brief flip transition are omitted.

The tissue and particles are illustrative geometry and keyframes, not a medical or physical simulation. A completed render demonstrates that this complexity can be edited and animated in Blender. It does not establish creator-level visual fidelity or automatic reconstruction quality.

## Reproduce

Run `scripts/splinter_reference.py` with the repository's Python environment for representative keyframes. Add `--animate` for the full sequence. The script downloads the public source if absent, stores a project under `data/projects`, and writes its ID to `data/references/splinter/rebuild-job.json`. Run it only when that project is idle.

After inspecting previews, Retry in the app renders the saved plan through the same persistent pipeline used by imported projects. `scripts/export_check.py PROJECT_ID` extracts the final ZIP, recompiles it independently, reopens the native file, and captures the actual comparison.

Source media and generated outputs stay local and are excluded from Git. The exported ZIP excludes the source footage and contains both the compact recipe plan and expanded geometry, plus a standalone Blender compiler.
