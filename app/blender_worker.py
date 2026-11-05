"""Repository-owned persistent Blender renderer. JSON input, PNG/result-file output."""
import json
import sys
import traceback
from pathlib import Path

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parent))
from blender_scene import material_nodes, rgba


def main():
    folder = Path(sys.argv[sys.argv.index('--') + 1]).resolve()
    for line in sys.stdin:
        request = json.loads(line)
        index = int(request['id'])
        if not 0 <= index <= 1000000:
            raise ValueError('Invalid request ID')
        result = folder / f'{index:06d}.json'
        try:
            scene = bpy.context.scene
            for spec in request.get('materials', []):
                mat = bpy.data.materials.get(spec['id'])
                if mat is None:
                    raise ValueError('Unknown material')
                mat.node_tree.animation_data_clear()
                mat.node_tree.nodes.clear()
                mat.node_tree.nodes.new('ShaderNodeBsdfPrincipled')
                mat.node_tree.nodes.new('ShaderNodeOutputMaterial')
                mat.node_tree.links.new(mat.node_tree.nodes.get('Principled BSDF').outputs['BSDF'], mat.node_tree.nodes.get('Material Output').inputs['Surface'])
                material_nodes(mat, spec)
            for index_light, spec in enumerate(request.get('lights', [])):
                obj = bpy.data.objects.get(f'Light 1.{index_light + 1}')
                if obj is None:
                    raise ValueError('Unknown light')
                obj.location = spec['location']
                from mathutils import Vector
                obj.rotation_euler = (Vector(spec['target']) - obj.location).to_track_quat('-Z', 'Y').to_euler()
                obj.data.energy = spec['energy']
                obj.data.type = spec['kind']
                obj.data.color = rgba(spec['color'])[:3]
                if obj.data.type == 'AREA':
                    obj.data.size = spec['size']
            scene.render.resolution_x, scene.render.resolution_y = request['size']
            scene.cycles.samples = request.get('samples', 12)
            scene.frame_set(request['frame'] + 1)
            scene.render.filepath = str(folder / f'{index:06d}.png')
            bpy.ops.render.render(write_still=True)
            payload = {'ok': True, 'image': f'{index:06d}.png'}
        except Exception:
            payload = {'ok': False, 'error': traceback.format_exc()}
        pending = result.with_suffix('.tmp')
        pending.write_text(json.dumps(payload), encoding='utf-8')
        pending.replace(result)


if __name__ == '__main__':
    main()
