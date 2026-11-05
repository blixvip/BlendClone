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


def animate_frames(obj, keys):
    for key in sorted(keys, key=lambda k: k['frame']):
        prop = 'rotation_euler' if key['property'] == 'rotation' else key['property']
        value = tuple(math.radians(v) for v in key['value']) if prop == 'rotation_euler' else key['value']
        setattr(obj, prop, value)
        obj.keyframe_insert(data_path=prop, frame=key['frame'] + 1)
    interpolation = {(key['frame'] + 1, 'rotation_euler' if key['property'] == 'rotation' else key['property']): key['interpolation'] for key in keys}
    for curve in curves(obj):
        for point in curve.keyframe_points:
            method = interpolation.get((round(point.co.x), curve.data_path))
            if method:
                point.interpolation = method


def sampled_mesh(obj, samples):
    """Absolute native shape keys retain measured topology at each sampled frame."""
    if not samples:
        return
    obj.shape_key_add(name='Basis')
    data = obj.data.shape_keys
    data.use_relative = False
    for sample in sorted(samples, key=lambda s: s['frame']):
        block = obj.shape_key_add(name=f"Measured frame {sample['frame']}")
        block.data.foreach_set('co', [v for point in sample['vertices'] for v in point])
        block.interpolation = 'KEY_LINEAR'
        data.eval_time = block.frame
        data.keyframe_insert(data_path='eval_time', frame=sample['frame'] + 1)
    for curve in curves(data):
        for key in curve.keyframe_points:
            key.interpolation = 'LINEAR'


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
        for i, (point, co) in enumerate(zip(spline.bezier_points, spec['points'])):
            point.co = co
            point.handle_left_type = point.handle_right_type = 'AUTO'
            if spec.get('radii'):
                point.radius = spec['radii'][i]
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
        if spec.get('face_materials'):
            slots = {mat.name:index for index,mat in enumerate(obj.data.materials)}
            for name in dict.fromkeys(spec['face_materials']):
                if name not in slots:
                    slots[name] = len(obj.data.materials)
                    obj.data.materials.append(materials[name])
            for polygon,name in zip(obj.data.polygons,spec['face_materials']):
                polygon.material_index = slots[name]
        for poly in obj.data.polygons:
            poly.use_smooth = spec['smooth']
        if spec['bevel']:
            mod = obj.modifiers.new('Edge bevel', 'BEVEL')
            mod.width, mod.segments = spec['bevel'], 3
        if spec['subdivision']:
            mod = obj.modifiers.new('Subdivision', 'SUBSURF')
            mod.levels = mod.render_levels = spec['subdivision']
    return obj


def material_color_track(tree, sockets, samples):
    for sample in samples:
        for socket in sockets:
            socket.default_value = rgba(sample['color'])
            socket.keyframe_insert('default_value', frame=sample['frame'] + 1)
    for curve in curves(tree):
        for point in curve.keyframe_points:
            point.interpolation = 'LINEAR'


def material_nodes(mat, spec):
    tree = mat.node_tree
    node = tree.nodes.get('Principled BSDF')
    if spec.get('unlit'):
        emission=tree.nodes.new('ShaderNodeEmission')
        emission.inputs['Color'].default_value=rgba(spec['color'])
        emission.inputs['Strength'].default_value=max(.01,spec.get('emission',1))
        material_color_track(tree, [emission.inputs['Color']], spec.get('color_samples', []))
        if spec.get('pattern') == 'gradient':
            coord = tree.nodes.new('ShaderNodeTexCoord')
            center = tree.nodes.new('ShaderNodeVectorMath'); center.operation = 'SUBTRACT'
            center.inputs[1].default_value = (.52, .8, 0)
            tree.links.new(coord.outputs['Window'], center.inputs[0])
            scale = tree.nodes.new('ShaderNodeVectorMath'); scale.operation = 'MULTIPLY'
            scale.inputs[1].default_value = spec.get('stretch', (1.8, 1.1, 0))
            tree.links.new(center.outputs[0], scale.inputs[0])
            distance = tree.nodes.new('ShaderNodeVectorMath'); distance.operation = 'LENGTH'
            tree.links.new(scale.outputs[0], distance.inputs[0])
            ramp = tree.nodes.new('ShaderNodeValToRGB')
            ramp.color_ramp.elements[0].color = rgba(spec['color'])
            ramp.color_ramp.elements[1].color = rgba(spec['detail_color'])
            tree.links.new(distance.outputs['Value'], ramp.inputs[0])
            tree.links.new(ramp.outputs['Color'], emission.inputs['Color'])
        output=emission.outputs[0]
        if spec.get('camera_only'):
            path=tree.nodes.new('ShaderNodeLightPath')
            transparent=tree.nodes.new('ShaderNodeBsdfTransparent')
            mix=tree.nodes.new('ShaderNodeMixShader')
            tree.links.new(path.outputs['Is Camera Ray'],mix.inputs[0])
            tree.links.new(transparent.outputs[0],mix.inputs[1]);tree.links.new(output,mix.inputs[2])
            output=mix.outputs[0]
        tree.links.new(output,tree.nodes.get('Material Output').inputs['Surface'])
        return
    node.inputs['Base Color'].default_value = rgba(spec['color'])
    node.inputs['Roughness'].default_value = spec['roughness']
    node.inputs['Metallic'].default_value = spec['metallic']
    node.inputs['Emission Color'].default_value = rgba(spec['color'])
    node.inputs['Emission Strength'].default_value = spec['emission']
    node.inputs['Subsurface Weight'].default_value = spec.get('subsurface', 0)
    node.inputs['Subsurface Radius'].default_value = (1,.35,.18)
    node.inputs['Coat Weight'].default_value = spec.get('coat',0)
    node.inputs['Coat Roughness'].default_value = .24
    node.inputs['Transmission Weight'].default_value = spec.get('transmission',0)
    if spec.get('pattern','solid') == 'solid':
        material_color_track(tree, [node.inputs['Base Color'], node.inputs['Emission Color']], spec.get('color_samples', []))
        return
    coord=tree.nodes.new('ShaderNodeTexCoord')
    scale=tree.nodes.new('ShaderNodeVectorMath');scale.operation='MULTIPLY'
    scale.inputs[1].default_value=spec.get('stretch',(1,1,1))
    tree.links.new(coord.outputs['Object'],scale.inputs[0])
    tex=tree.nodes.new('ShaderNodeTexNoise')
    tex.inputs['Scale'].default_value=spec.get('texture_scale',8)
    tex.inputs['Detail'].default_value=3.5
    tex.inputs['Roughness'].default_value=.7
    tree.links.new(scale.outputs[0],tex.inputs['Vector'])
    ramp=tree.nodes.new('ShaderNodeValToRGB')
    ramp.color_ramp.elements[0].position=.2
    ramp.color_ramp.elements[0].color=rgba(spec['color'])
    ramp.color_ramp.elements[1].position=.8
    ramp.color_ramp.elements[1].color=rgba(spec.get('detail_color',spec['color']))
    tree.links.new(tex.outputs['Fac'],ramp.inputs[0]);tree.links.new(ramp.outputs[0],node.inputs['Base Color'])
    source=tex.outputs['Fac']
    if spec['pattern'] == 'wound':
        distance=tree.nodes.new('ShaderNodeVectorMath');distance.operation='LENGTH'
        tree.links.new(coord.outputs['Object'],distance.inputs[0])
        fade=tree.nodes.new('ShaderNodeMapRange');fade.clamp=True
        fade.inputs['From Min'].default_value=.1;fade.inputs['From Max'].default_value=1.1
        tree.links.new(distance.outputs['Value'],fade.inputs['Value'])
        mix=tree.nodes.new('ShaderNodeMixRGB');mix.inputs[1].default_value=rgba('#C8544B')
        tree.links.new(fade.outputs[0],mix.inputs[0]);tree.links.new(ramp.outputs[0],mix.inputs[2])
        tree.links.new(mix.outputs[0],node.inputs['Base Color'])
    if spec['pattern'] in ('skin','cells','wound'):
        pores=tree.nodes.new('ShaderNodeTexVoronoi');pores.feature='DISTANCE_TO_EDGE'
        pores.inputs['Scale'].default_value=spec.get('texture_scale',8)*3
        tree.links.new(scale.outputs[0],pores.inputs['Vector'])
        source=pores.outputs['Distance']
    bump=tree.nodes.new('ShaderNodeBump')
    bump.inputs['Strength'].default_value=spec.get('bump',0)
    bump.inputs['Distance'].default_value=.025 if spec['pattern']!='wood' else .08
    tree.links.new(source,bump.inputs['Height']);tree.links.new(bump.outputs[0],node.inputs['Normal'])


def shape_animation(obj, shapes, start, fps):
    if not shapes:
        return
    obj.shape_key_add(name='Basis')
    for spec in shapes:
        key=obj.shape_key_add(name=spec['name'],from_mix=False)
        for vertex in key.data:
            co=vertex.co.copy()
            distance=sum(((co[i]-spec['center'][i])/max(.001,spec['radius'][i]))**2 for i in range(3))
            influence=math.exp(-distance*2)
            vertex.co=tuple(co[i]+spec['displacement'][i]*influence for i in range(3))
        key.slider_min=-3;key.slider_max=3
        for point in spec['keys']:
            key.value=point['value'][0]
            key.keyframe_insert('value',frame=1+round((start+point['t'])*fps))
        for curve in curves(obj.data.shape_keys):
            if curve.data_path == key.path_from_id('value'):
                for point in curve.keyframe_points:
                    local_time=(point.co.x-1)/fps-start
                    closest=min(spec['keys'],key=lambda item:abs(item['t']-local_time))
                    point.interpolation=closest['interpolation']


def caption_objects(scene, captions, cameras, fps, folder):
    if not captions:
        return
    font_file = folder / 'fonts' / 'arialbd.ttf'
    if not font_file.is_file():
        font_file = Path('C:/Windows/Fonts/arialbd.ttf')
    if not font_file.is_file():
        raise ValueError('Caption font Arial Bold is missing')
    font = bpy.data.fonts.load(str(font_file))
    font.pack()
    palette = {}
    for name, color in [('Caption white','#ffffff'),('Caption stroke','#000000')]:
        material = bpy.data.materials.new(name)
        material.use_nodes = True
        material_nodes(material, dict(unlit=True,color=color,emission=1))
        palette[name] = material
    for camera, start, end in cameras:
        depth = 1.0
        height = camera.data.ortho_scale if camera.data.type == 'ORTHO' else 2 * depth * math.tan(camera.data.angle_y / 2)
        width = height * scene.render.resolution_x / scene.render.resolution_y
        for index, caption in enumerate(captions):
            first, last = max(caption['first_frame'], round(start*fps)), min(caption['end_frame'], round(end*fps))
            if first >= last:
                continue
            for layer, (dx,dy) in enumerate([(x,y) for x,y in [(-1,0),(1,0),(0,-1),(0,1),(-.7,-.7),(-.7,.7),(.7,-.7),(.7,.7),(0,0)]]):
                data = bpy.data.curves.new(f'Caption {index} text', 'FONT')
                data.body, data.font, data.align_x, data.align_y = caption['text'], font, 'CENTER', 'CENTER'
                obj = bpy.data.objects.new(f'Caption {index} layer {layer}',data)
                scene.collection.objects.link(obj)
                obj.parent = camera
                obj.location = ((caption['x']-.5)*width + dx*caption['stroke']*height,
                                (.5-caption['y'])*height + dy*caption['stroke']*height,
                                -depth - (.001 if layer < 8 else 0))
                data.materials.append(palette['Caption stroke' if layer < 8 else 'Caption white'])
                bpy.context.view_layer.update()
                obj.scale = (caption['width']*width/max(obj.dimensions.x,1e-6),caption['height']*height/max(obj.dimensions.y,1e-6),1)
                obj.visible_shadow = False
                obj.visible_diffuse = False
                obj.visible_glossy = False
                visible_during(obj,first/fps,last/fps,fps)


def build(config):
    folder = Path(config['folder']).resolve()
    plan = json.loads((folder / config.get('plan', 'plan.json')).read_text(encoding='utf-8'))
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.name = plan['title']
    fps = config['fps']/config.get('fps_base',1)
    scene.render.fps = config['fps']
    scene.render.fps_base = config.get('fps_base',1)
    scene.frame_start = 1
    scene.frame_end = config.get('frame_count') or max(1, round(config['duration'] * fps))
    scene.render.engine = config.get('engine','CYCLES')
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
    scene.view_settings.view_transform = plan.get('view_transform','AgX')
    world = bpy.data.worlds.new('Shot environments')
    world.use_nodes = True
    scene.world = world
    background = world.node_tree.nodes.get('Background')
    background.inputs['Strength'].default_value = 1
    materials = {}
    for spec in plan['materials']:
        mat = bpy.data.materials.new(spec['id'])
        mat.diffuse_color = rgba(spec['color'])
        mat.use_nodes = True
        material_nodes(mat,spec)
        materials[spec['id']] = mat
    cameras = []
    for index, shot in enumerate(plan['shots']):
        collection = bpy.data.collections.new(f'{index+1:02d} · {shot["name"]}')
        scene.collection.children.link(collection)
        objects = {spec['id']: make_object(spec, collection, materials) for spec in shot['objects']}
        for spec in shot['objects']:
            obj = objects[spec['id']]
            if spec['parent']:
                obj.parent = objects[spec['parent']]
            animate(obj, spec['keys'], shot['start'], fps)
            animate_frames(obj, spec.get('frame_keys', []))
            shape_animation(obj,spec.get('shapes',[]),shot['start'],fps)
            sampled_mesh(obj, spec.get('mesh_samples', []))
            visible_during(obj, shot['start'], shot['end'], fps)
        camera_spec = shot['camera']
        camera_data = bpy.data.cameras.new(f'Camera {index+1}')
        camera_data.lens = camera_spec['lens']
        camera_data.clip_end = 1000
        if camera_spec['orthographic']:
            camera_data.type = 'ORTHO'
            camera_data.ortho_scale = camera_spec['ortho_scale']
        camera = bpy.data.objects.new(camera_data.name, camera_data)
        cameras.append((camera, shot['start'], shot['end']))
        collection.objects.link(camera)
        camera.location = camera_spec['location']
        target = bpy.data.objects.new(f'Camera target {index+1}', None)
        collection.objects.link(target)
        target.location = camera_spec['target']
        if camera_spec.get('aperture'):
            camera_data.dof.use_dof=True
            camera_data.dof.focus_object=target
            camera_data.dof.aperture_fstop=camera_spec['aperture']
        constraint = camera.constraints.new('TRACK_TO')
        constraint.target, constraint.track_axis, constraint.up_axis = target, 'TRACK_NEGATIVE_Z', 'UP_Y'
        animate(camera, camera_spec['keys'], shot['start'], fps)
        animate(target, camera_spec['target_keys'], shot['start'], fps)
        animate_frames(camera, camera_spec.get('frame_keys', []))
        animate_frames(target, camera_spec.get('target_frame_keys', []))
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
    caption_objects(scene, plan.get('captions', []), cameras, fps, folder)
    scene.frame_set(1)
    scene.render.filepath = '//frames/'
    notes = bpy.data.texts.new('ABOUT THIS REMAKE')
    notes.write(plan['summary'] + '\n\nKnown approximations:\n' + '\n'.join(plan['limitations']))
    bpy.ops.wm.save_as_mainfile(filepath=str(folder / 'remake.blend'))
    inventory = dict(objects=len(scene.objects), meshes=sum(o.type == 'MESH' for o in scene.objects), cameras=sum(o.type == 'CAMERA' for o in scene.objects), frames=scene.frame_end, fps=fps, shots=len(plan['shots']), animated_objects=sum(bool(o.animation_data) for o in scene.objects), device=scene.cycles.device)
    inventory.update(engine=scene.render.engine, shape_keys=sum(len(o.data.shape_keys.key_blocks)-1 for o in scene.objects if o.type=='MESH' and o.data.shape_keys), vertices=sum(len(o.data.vertices) for o in scene.objects if o.type=='MESH'))
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
        # Resuming after a crash (e.g. a GPU driver reset): keep frames that already finished.
        scene.render.use_overwrite = not config.get('resume', False)
        bpy.ops.render.render(animation=True)


if __name__ == '__main__':
    build(json.loads(Path(sys.argv[sys.argv.index('--')+1]).read_text(encoding='utf-8')))
