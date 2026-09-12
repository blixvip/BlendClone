"""Read-only native Blender verification: run after a benchmark .blend is saved."""
import json
import math
import sys
from pathlib import Path
import bpy

scene=bpy.context.scene
assert scene.frame_end == 729
assert len(scene.timeline_markers) == 7
section=next(c for c in scene.collection.children if c.name.startswith('06 '))
cap=next(o for o in section.objects if o.name.startswith('section_skin_cap'))
blocks=cap.data.shape_keys.key_blocks
assert len(blocks) == 3
# Both shape keys must be offsets from Basis, never from the preceding mixed shape.
for name,cx in [('swelling_left',-.45),('swelling_right',.45)]:
    key=blocks[name]
    for i in range(0,len(key.data),113):
        base=blocks['Basis'].data[i].co
        distance=((base.x-cx)/1.8)**2+(base.y/2.5)**2+(base.z/.06)**2
        expected=base.z+.78*math.exp(-2*distance)
        assert abs(key.data[i].co.z-expected)<1e-5
scene.frame_set(1+round(14.5*24))
assert not cap.hide_render
assert .9 <= blocks['swelling_left'].value <= 1.1
assert .9 <= blocks['swelling_right'].value <= 1.1
assert scene.camera.name == 'Camera 6'
surface_collection=next(c for c in scene.collection.children if c.name.startswith('05 '))
surface=next(o for o in surface_collection.objects if o.name.startswith('surface_skin_surface'))
scene.frame_set(1+round(8*24));before=surface.data.shape_keys.key_blocks['swelling'].value
assert not surface.hide_render
scene.frame_set(1+round(12.6*24));after=surface.data.shape_keys.key_blocks['swelling'].value
assert after > before+.5
final_collection=next(c for c in scene.collection.children if c.name.startswith('07 '))
shard=next(o for o in final_collection.objects if o.name.startswith('sliver') and o.type=='EMPTY')
scene.frame_set(1+round(27*24));before_z=shard.location.z
scene.frame_set(729);assert shard.location.z > before_z+2
assert scene.camera.name == 'Camera 7'
result=dict(frames=scene.frame_end,shots=7,independent_shape_keys=True,swelling_animates=True,extraction_animates=True,camera_cuts=True)
if '--' in sys.argv:
    Path(sys.argv[sys.argv.index('--')+1]).write_text(json.dumps(result,indent=2),encoding='utf-8')
print('NATIVE SPLINTER CHECK PASSED',json.dumps(result))
