# Roadmap

## Now: reconstruction fidelity

Finish what [FINAL-PLAN.md](FINAL-PLAN.md) lays out:

- Recalibrate the fidelity gates on an owned clip. The motion gate is currently too loose on compression noise.
- Match the renderer (Eevee vs Cycles) between the reference and the remake before scoring.
- Add object masks and a perceptual metric (LPIPS) next to SSIM and ΔE.
- Run a one-second pilot that passes every gate, then extend it.

## Next: stylized character shorts

North-star target: a 1–2 minute stylized 3D short. Picture soft-lit toy-like box characters with simple pixel faces and props (glasses, a bow tie, a beret) in a beach scene with a sandcastle, water, palm trees and bunting. Story beats include an egg hatching, characters reacting, confetti, and a moving camera with depth of field.

To get there, the scene contract needs:

| Capability | Today | Needed |
|---|---|---|
| Characters | Rigid primitives + parenting | Simple armature rigs (body squash/stretch, limbs, hop/walk cycles) |
| Faces | — | Swappable face textures or shape keys driven by expression keys (happy, blink, surprised) |
| Props / attachments | Parenting | Socketed accessories (hat, glasses) that follow the rig |
| Environment | Primitives, procedural textures | Sand/water/sky presets, scattered set dressing, cloud cards |
| Effects | — | Particle bursts (confetti, sand puffs), cracking shell pieces |
| Direction | Rebuilt from a reference | Prompt → beat sheet → shots → camera moves (no reference needed) |
| Rendering | Eevee/Cycles per project | Stylized look preset (warm key, soft shadows, bloom, shallow DOF) |

Constraint: keep it declarative. The planner writes validated scene data, and repository-owned code builds every rig, face and effect. Model-written Python still never runs.

Hardware note: the dev PC has a GTX 1650 (4 GB), so plan around Eevee previews and short Cycles finals.
