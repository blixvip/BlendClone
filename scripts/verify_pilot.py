"""Read-only Blender verification of frame-indexed tracks and sampled mesh deformation."""
import json
import sys
from pathlib import Path

import bpy

folder=Path(sys.argv[sys.argv.index('--')+1])
plan=json.loads((folder/'expanded_plan.json').read_text(encoding='utf-8'))
scene=bpy.context.scene
timeline=plan['timeline']
assert scene.frame_end == timeline['frame_count']
# Blender stores fps_base as single precision; integer frame indices and export use the exact rational.
assert abs(scene.render.fps/scene.render.fps_base-timeline['fps_num']/timeline['fps_den']) < 3e-6
config=json.loads((folder/'animation.config.json').read_text())
assert (scene.render.resolution_x,scene.render.resolution_y)==(config['width'],config['height'])
assert scene.render.engine == plan['engine']
checked=0
for spec in plan['shots'][0]['objects']:
    obj=bpy.data.objects[spec['id']]
    if spec.get('mesh_samples'):
        assert obj.data.shape_keys and not obj.data.shape_keys.use_relative
        # Samples describe the control cage. Subdivision changes its vertex positions
        # and topology, so validate deformation before the authored modifiers.
        modifier_visibility=[(modifier,modifier.show_viewport) for modifier in obj.modifiers]
        for modifier,_ in modifier_visibility:
            modifier.show_viewport=False
        for sample in [spec['mesh_samples'][0],spec['mesh_samples'][-1]]:
            scene.frame_set(sample['frame']+1)
            evaluated=obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
            mesh=evaluated.to_mesh()
            try:
                for index in range(0,len(sample['vertices']),101):
                    actual=mesh.vertices[index].co
                    error=max(abs(actual[i]-sample['vertices'][index][i]) for i in range(3))
                    assert error < 1e-4, f"{spec['id']} frame {sample['frame']} vertex {index}: error {error}; modifiers {[(m.type,m.show_viewport) for m in obj.modifiers]}"
                    checked+=1
            finally:evaluated.to_mesh_clear()
        for modifier,visible in modifier_visibility:
            modifier.show_viewport=visible
    for key in spec.get('frame_keys',[])[::max(1,len(spec.get('frame_keys',[]))//4)]:
        scene.frame_set(key['frame']+1)
        if key['property'] in ('location','scale'):
            actual=getattr(obj,key['property'])
            assert max(abs(actual[i]-key['value'][i]) for i in range(3)) < 1e-4
captions=[obj for obj in scene.objects if obj.type=='FONT']
material_samples_checked=0
for material in plan['materials']:
    samples=material.get('color_samples',[])
    if not samples:
        continue
    tree=bpy.data.materials[material['id']].node_tree
    socket=next(node for node in tree.nodes if node.type=='EMISSION').inputs['Color'] if material['unlit'] else tree.nodes.get('Principled BSDF').inputs['Base Color']
    for sample in (samples[0],samples[-1]):
        scene.frame_set(sample['frame']+1)
        rgb=[int(sample['color'][n:n+2],16)/255 for n in (1,3,5)]
        expected=[v/12.92 if v<=.04045 else ((v+.055)/1.055)**2.4 for v in rgb]
        assert max(abs(socket.default_value[n]-expected[n]) for n in range(3)) < 1e-5
        material_samples_checked+=1
assert captions and all(obj.data.font.packed_file for obj in captions)
scene.frame_set(1)
assert any(not obj.hide_render for obj in captions)
scene.frame_set(timeline['frame_count']+1)
assert all(obj.hide_render for obj in captions)
(folder/'native-verification.json').write_text(json.dumps(dict(frames=scene.frame_end,sampled_vertices_checked=checked,
    captions=len(captions),font_packed=True,frame_tracks=True,material_samples_checked=material_samples_checked,engine=scene.render.engine,
    resolution=[scene.render.resolution_x,scene.render.resolution_y])),encoding='utf-8')
print('NATIVE PILOT VERIFIED',checked,'sampled vertices')
