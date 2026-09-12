"""Deterministic Blender compiler. Run with Blender --background --python this_file -- config.json.

Only this repository-owned Python executes. The model supplies validated JSON.
"""
import json
import math
import sys
from pathlib import Path
import bpy
from mathutils import Vector


def rgba(hex_color):
    # Convert input sRGB into Blender's linear material colors.
    rgb = [int(hex_color[i:i+2], 16)/255 for i in (1, 3, 5)]
    return tuple(c/12.92 if c <= .04045 else ((c+.055)/1.055)**2.4 for c in rgb) + (1,)


def curves(obj):
    animation = obj.animation_data
    if not animation or not animation.action:
        return []
    action = animation.action
    if hasattr(action, 'fcurves'):
        return action.fcurves
    found = []
    for layer in action.layers:
        for strip in layer.strips:
            if hasattr(strip, 'channelbag'):
                bag = strip.channelbag(animation.action_slot)
                if bag:
                    found.extend(bag.fcurves)
    return found


def animate(obj, keys, start, fps):
    for key in sorted(keys, key=lambda k: k['t']):
        prop = 'rotation_euler' if key['property'] == 'rotation' else key['property']
        value = tuple(math.radians(v) for v in key['value']) if prop == 'rotation_euler' else key['value']
        setattr(obj, prop, value)
        frame = 1 + round((start + key['t']) * fps)
        obj.keyframe_insert(data_path=prop, frame=frame)
        for curve in curves(obj):
            if curve.data_path == prop:
                for point in curve.keyframe_points:
                    if abs(point.co.x - frame) < .01:
                        point.interpolation = key['interpolation']


def visible_during(obj, start, end, fps):
    first = 1 + round(start * fps)
    last = 1 + round(end * fps)
    for frame, hidden in [(0, True), (first, False), (last, True)]:
        obj.hide_render = hidden
        obj.hide_viewport = hidden
        obj.keyframe_insert(data_path='hide_render', frame=frame)
        obj.keyframe_insert(data_path='hide_viewport', frame=frame)
    for curve in curves(obj):
        if curve.data_path in ('hide_render', 'hide_viewport'):
            for point in curve.keyframe_points:
                point.interpolation = 'CONSTANT'


def move_to_collection(obj, collection):
    for old in list(obj.users_collection):
        old.objects.unlink(obj)
    collection.objects.link(obj)


def make_object(spec, collection, materials):
    kind = spec['kind']
    makers = {
        'cube': lambda: bpy.ops.mesh.primitive_cube_add(size=2),
        'sphere': lambda: bpy.ops.mesh.primitive_uv_sphere_add(segments=32, ring_count=20, radius=1),
        'cylinder': lambda: bpy.ops.mesh.primitive_cylinder_add(vertices=48, radius=1, depth=2),
        'cone': lambda: bpy.ops.mesh.primitive_cone_add(vertices=48, radius1=1, radius2=0, depth=2),
        'torus': lambda: bpy.ops.mesh.primitive_torus_add(major_radius=1, minor_radius=.25, major_segments=48, minor_segments=16),
        'plane': lambda: bpy.ops.mesh.primitive_plane_add(size=2),
    }
    if kind in makers:
        makers[kind]()
        obj = bpy.context.object
    elif kind == 'mesh':
        mesh = bpy.data.meshes.new(spec['id'])
        mesh.from_pydata(spec['vertices'], [], spec['faces'])
        mesh.update()
        obj = bpy.data.objects.new(spec['id'], mesh)
    elif kind == 'curve':
        data = bpy.data.curves.new(spec['id'], 'CURVE')
        data.dimensions = '3D'
        data.bevel_depth = spec['thickness']
        data.bevel_resolution = 4
        data.use_fill_caps = True
        spline = data.splines.new('BEZIER')
        spline.bezier_points.add(len(spec['points'])-1)
        for point, co in zip(spline.bezier_points, spec['points']):
            point.co = co
            point.handle_left_type = point.handle_right_type = 'AUTO'
        obj = bpy.data.objects.new(spec['id'], data)
    elif kind == 'text':
        data = bpy.data.curves.new(spec['id'], 'FONT')
        data.body = spec['text']
        data.align_x = 'CENTER'
        data.align_y = 'CENTER'
        data.extrude = .008
        obj = bpy.data.objects.new(spec['id'], data)
    else:
        obj = bpy.data.objects.new(spec['id'], None)
    obj.name = spec['id']
    move_to_collection(obj, collection)
    obj.location = spec['location']
    obj.rotation_euler = [math.radians(v) for v in spec['rotation']]
    obj.scale = spec['scale']
    if spec['material'] and obj.data and hasattr(obj.data, 'materials'):
        obj.data.materials.append(materials[spec['material']])
    if obj.type == 'MESH':
        for poly in obj.data.polygons:
            poly.use_smooth = spec['smooth']
        if spec['bevel']:
            mod = obj.modifiers.new('Edge bevel', 'BEVEL')
            mod.width, mod.segments = spec['bevel'], 3
        if spec['subdivision']:
            mod = obj.modifiers.new('Subdivision', 'SUBSURF')
            mod.levels = mod.render_levels = spec['subdivision']
    return obj


def build(config):
    folder = Path(config['folder']).resolve()
    plan = json.loads((folder / config.get('plan', 'plan.json')).read_text(encoding='utf-8'))
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.name = plan['title']
    fps = config['fps']
    scene.render.fps = fps
    scene.frame_start = 1
    scene.frame_end = max(1, round(config['duration'] * fps))
    scene.render.engine = 'CYCLES'
    scene.cycles.samples = config.get('samples', 16)
    scene.cycles.use_denoising = True
    scene.cycles.device = 'CPU'
    # Use an available GPU when Cycles exposes one; CPU remains a portable fallback.
    try:
        prefs = bpy.context.preferences.addons['cycles'].preferences
        for backend in ('OPTIX', 'CUDA', 'HIP', 'ONEAPI', 'METAL'):
            try:
                prefs.compute_device_type = backend
                prefs.get_devices()
                if any(d.type != 'CPU' for d in prefs.devices):
                    for device in prefs.devices:
                        device.use = device.type != 'CPU'
                    scene.cycles.device = 'GPU'
                    break
            except Exception:
                continue
    except Exception:
        pass
    scene.render.resolution_x = config['width']
    scene.render.resolution_y = config['height']
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = 'PNG'
    scene.render.image_settings.color_mode = 'RGB'
    scene.view_settings.view_transform = 'AgX'
    world = bpy.data.worlds.new('Shot environments')
    world.use_nodes = True
    scene.world = world
    background = world.node_tree.nodes.get('Background')
    background.inputs['Strength'].default_value = .35
    materials = {}
    for spec in plan['materials']:
        mat = bpy.data.materials.new(spec['id'])
        mat.diffuse_color = rgba(spec['color'])
        mat.use_nodes = True
        node = mat.node_tree.nodes.get('Principled BSDF')
        node.inputs['Base Color'].default_value = rgba(spec['color'])
        node.inputs['Roughness'].default_value = spec['roughness']
        node.inputs['Metallic'].default_value = spec['metallic']
        node.inputs['Emission Color'].default_value = rgba(spec['color'])
        node.inputs['Emission Strength'].default_value = spec['emission']
        materials[spec['id']] = mat
    for index, shot in enumerate(plan['shots']):
        collection = bpy.data.collections.new(f'{index+1:02d} · {shot["name"]}')
        scene.collection.children.link(collection)
        objects = {spec['id']: make_object(spec, collection, materials) for spec in shot['objects']}
        for spec in shot['objects']:
            obj = objects[spec['id']]
            if spec['parent']:
                obj.parent = objects[spec['parent']]
            animate(obj, spec['keys'], shot['start'], fps)
            visible_during(obj, shot['start'], shot['end'], fps)
        camera_spec = shot['camera']
        camera_data = bpy.data.cameras.new(f'Camera {index+1}')
        camera_data.lens = camera_spec['lens']
        camera_data.clip_end = 1000
        if camera_spec['orthographic']:
            camera_data.type = 'ORTHO'
            camera_data.ortho_scale = camera_spec['ortho_scale']
        camera = bpy.data.objects.new(camera_data.name, camera_data)
        collection.objects.link(camera)
        camera.location = camera_spec['location']
        target = bpy.data.objects.new(f'Camera target {index+1}', None)
        collection.objects.link(target)
        target.location = camera_spec['target']
        constraint = camera.constraints.new('TRACK_TO')
        constraint.target, constraint.track_axis, constraint.up_axis = target, 'TRACK_NEGATIVE_Z', 'UP_Y'
        animate(camera, camera_spec['keys'], shot['start'], fps)
        animate(target, camera_spec['target_keys'], shot['start'], fps)
        if index == 0:
            scene.camera = camera
        marker = scene.timeline_markers.new(shot['name'], frame=1+round(shot['start']*fps))
        marker.camera = camera
        for light_index, spec in enumerate(shot['lights']):
            data = bpy.data.lights.new(f'Light {index+1}.{light_index+1}', spec['kind'])
            data.energy = spec['energy']
            data.color = rgba(spec['color'])[:3]
            if spec['kind'] == 'AREA':
                data.shape = 'DISK'
                data.size = spec['size']
            light = bpy.data.objects.new(data.name, data)
            collection.objects.link(light)
            light.location = spec['location']
            direction = Vector(spec['target']) - light.location
            if direction.length > .0001:
                light.rotation_euler = direction.to_track_quat('-Z', 'Y').to_euler()
            visible_during(light, shot['start'], shot['end'], fps)
        background.inputs['Color'].default_value = rgba(shot['background'])
        background.inputs['Color'].keyframe_insert('default_value', frame=1+round(shot['start']*fps))
    for curve in curves(world.node_tree):
        for point in curve.keyframe_points:
            point.interpolation = 'CONSTANT'
    scene.frame_set(1)
    scene.render.filepath = '//frames/'
    notes = bpy.data.texts.new('ABOUT THIS REMAKE')
    notes.write(plan['summary'] + '\n\nKnown approximations:\n' + '\n'.join(plan['limitations']))
    bpy.ops.wm.save_as_mainfile(filepath=str(folder / 'remake.blend'))
    inventory = dict(objects=len(scene.objects), meshes=sum(o.type == 'MESH' for o in scene.objects), cameras=sum(o.type == 'CAMERA' for o in scene.objects), frames=scene.frame_end, fps=fps, shots=len(plan['shots']), animated_objects=sum(bool(o.animation_data) for o in scene.objects), device=scene.cycles.device)
    (folder / 'inventory.json').write_text(json.dumps(inventory, indent=2), encoding='utf-8')
    preview = folder / 'previews'
    preview.mkdir(exist_ok=True)
    if config['mode'] == 'preview':
        for i, t in enumerate(config['times']):
            scene.frame_set(min(scene.frame_end, 1+round(t*fps)))
            scene.render.filepath = str(preview / f'{i:03d}.png')
            bpy.ops.render.render(write_still=True)
    elif config['mode'] == 'animation':
        frames = folder / 'frames'
        frames.mkdir(exist_ok=True)
        scene.render.filepath = str(frames / 'frame-')
        bpy.ops.render.render(animation=True)


if __name__ == '__main__':
    build(json.loads(Path(sys.argv[sys.argv.index('--')+1]).read_text(encoding='utf-8')))
