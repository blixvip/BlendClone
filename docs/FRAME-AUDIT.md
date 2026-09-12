# Frame audit: 1:1 target

The supplied reference has 910 frames at 30000/1001 fps, 1080 by 1920 pixels. Every decoded frame is preserved with its timestamp, adjacent-frame image difference, and optical-flow summary in `data/references/splinter/frame-audit`. All 31 consecutive contact sheets were visually inspected. Full-resolution frames remain available for landmark measurements.

The previous 24 fps, seven-shot approximation does not meet the requested 1:1 target. It substitutes simple models, omits captions and a flip transition, and replaces continuous camera/surface transitions with cuts. Rendering successfully does not establish fidelity.

| Source frames (zero based) | Observed action |
| --- | --- |
| 0-14 | Hand touching vertical wood; slight motion |
| 15-36 | Fast recoil, wrist rotation, bent index straightens |
| 37-49 | Continuous camera push into fingertip |
| 50-74 | Finger and exposed splinter hold |
| 75-95 | Tweezers descend toward shard |
| 96-101 | Jaws close on shard |
| 102-113 | Extraction, tool and shard leave frame |
| 114-145 | Finger holds, subtle camera/subject drift |
| 146-161 | Vertical-axis card flip on black into cutaway |
| 162-216 | Cutaway moves and embedded shard sinks farther |
| 217-248 | Continuous transition from section into surface view |
| 240-266 | Tweezers enter and approach wound |
| 267-281 | Tool cannot reach shard |
| 282-293 | Tweezers retract |
| 310-363 | Wound reddens and swells gradually |
| 364-389 | Surface opens into anatomical cutaway; particles begin |
| 390-480 | Swollen cutaway holds; particles accumulate and move |
| 492-508 | Pressure arrows enter from both sides |
| 509-665 | Particles move and decrease; shard rises; camera drifts |
| 666-707 | Continuous transition back above skin |
| 708-747 | Swelling begins to subside |
| 748-788 | Shard emerges through shrinking red bump |
| 789-829 | Exposed shard holds |
| 830-852 | Tweezers descend and grasp shard |
| 853-885 | Tool pulls shard out and exits |
| 886-909 | Final skin view holds |

These are measured review ranges, not claims that the current reconstruction reproduces them. Fine boundaries are available in the numbered frames. The reference also uses caption changes, local skin deformations, tool jaw flex, shallow focus, irregular glossy tissue, and lighting that the first implementation did not reproduce.

The cutaway test at local project `c9b5a17f3a64` rebuilds layer geometry and networks, but its visible material, surface, and shape differences still fail the 1:1 requirement. It is intentionally left unfinished. Native inspection confirms 90 frames for its 3.003-second reference at 29.97002997 fps. Frame-rate preservation, outward cell normals, and existing backend behavior pass 25 tests. These engineering checks do not constitute visual acceptance.

Next renders must be compared at matching original frame times. Asset silhouettes, screen-space landmarks, layer boundaries, color, lighting and motion must be judged independently. No similarity score should be presented as a guarantee of 1:1 fidelity.
