"""The AI produces scene data, never executable code."""
import math
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

Number = Annotated[float, Field(allow_inf_nan=False, ge=-100000, le=100000)]
Vec3 = tuple[Number, Number, Number]
Color = Annotated[str, Field(pattern=r'^#[0-9a-fA-F]{6}$')]


class Model(BaseModel):
    model_config = ConfigDict(extra='forbid')


class Key(Model):
    t: Annotated[float, Field(ge=0, le=60, allow_inf_nan=False)]
    property: Literal['location', 'rotation', 'scale']
    value: Vec3
    interpolation: Literal['LINEAR', 'BEZIER', 'CONSTANT'] = 'BEZIER'


class Timeline(Model):
    fps_num: Annotated[int, Field(ge=1, le=240000)] = 30000
    fps_den: Annotated[int, Field(ge=1, le=10000)] = 1001
    frame_count: Annotated[int, Field(ge=1, le=14400)]
    source_start_frame: Annotated[int, Field(ge=0, le=10000000)] = 0

    @model_validator(mode='after')
    def rate(self):
        if not 1 <= self.fps_num / self.fps_den <= 240:
            raise ValueError('timeline frame rate must be between 1 and 240')
        return self


class FrameKey(Model):
    frame: Annotated[int, Field(ge=0, le=14399)]
    property: Literal['location', 'rotation', 'scale']
    value: Vec3
    interpolation: Literal['LINEAR', 'BEZIER', 'CONSTANT'] = 'LINEAR'


class MeshSample(Model):
    frame: Annotated[int, Field(ge=0, le=14399)]
    vertices: Annotated[list[Vec3], Field(min_length=1, max_length=150000)]


class MaterialSample(Model):
    frame: Annotated[int, Field(ge=0, le=14399)]
    color: Color


class Material(Model):
    id: Annotated[str, Field(pattern=r'^[a-zA-Z0-9_-]{1,60}$')]
    color: Color
    roughness: Annotated[float, Field(ge=0, le=1)] = .45
    metallic: Annotated[float, Field(ge=0, le=1)] = 0
    emission: Annotated[float, Field(ge=0, le=10)] = 0
    subsurface: Annotated[float, Field(ge=0, le=1)] = 0
    coat: Annotated[float, Field(ge=0, le=1)] = 0
    transmission: Annotated[float, Field(ge=0, le=1)] = 0
    pattern: Literal['solid', 'noise', 'skin', 'cells', 'wood', 'wound', 'gradient'] = 'solid'
    detail_color: Color = '#ffffff'
    texture_scale: Annotated[float, Field(gt=0, le=1000)] = 8
    bump: Annotated[float, Field(ge=0, le=1)] = 0
    stretch: Vec3 = (1,1,1)
    unlit: bool = False
    camera_only: bool = False
    color_samples: Annotated[list[MaterialSample], Field(max_length=14400)] = []

    @model_validator(mode='after')
    def animated_color(self):
        if self.color_samples and self.pattern != 'solid':
            raise ValueError('material color samples require a solid pattern')
        return self


class ShapeKey(Model):
    name: Annotated[str, Field(pattern=r'^[a-zA-Z0-9_-]{1,60}$')]
    center: Vec3 = (0,0,0)
    radius: Vec3 = (1,1,1)
    displacement: Vec3 = (0,0,1)
    keys: Annotated[list[Key], Field(max_length=120)]


class Object(Model):
    id: Annotated[str, Field(pattern=r'^[a-zA-Z0-9_-]{1,60}$')]
    kind: Literal['cube', 'sphere', 'cylinder', 'cone', 'torus', 'plane', 'mesh', 'curve', 'empty', 'text', 'asset']
    asset: Literal['', 'skin_section', 'skin_surface', 'finger', 'hand', 'tweezers', 'splinter'] = ''
    seed: Annotated[int, Field(ge=0, le=100000)] = 7
    material: str = ''
    parent: str = ''
    location: Vec3 = (0, 0, 0)
    rotation: Vec3 = (0, 0, 0)
    scale: Vec3 = (1, 1, 1)
    vertices: Annotated[list[Vec3], Field(max_length=150000)] = []
    faces: Annotated[list[list[Annotated[int, Field(ge=0)]]], Field(max_length=150000)] = []
    face_materials: Annotated[list[Annotated[str, Field(min_length=1, max_length=60)]], Field(max_length=150000)] = []
    points: Annotated[list[Vec3], Field(max_length=2000)] = []
    thickness: Annotated[float, Field(ge=.001, le=10)] = .04
    radii: Annotated[list[Annotated[float, Field(ge=0, le=20)]], Field(max_length=2000)] = []
    shapes: Annotated[list[ShapeKey], Field(max_length=12)] = []
    text: Annotated[str, Field(max_length=500)] = ''
    bevel: Annotated[float, Field(ge=0, le=2)] = 0
    subdivision: Annotated[int, Field(ge=0, le=2)] = 0
    smooth: bool = True
    keys: Annotated[list[Key], Field(max_length=240)] = []
    frame_keys: Annotated[list[FrameKey], Field(max_length=43200)] = []
    mesh_samples: Annotated[list[MeshSample], Field(max_length=120)] = []

    @model_validator(mode='after')
    def geometry(self):
        if self.face_materials and (self.kind != 'mesh' or len(self.face_materials) != len(self.faces)):
            raise ValueError('face materials must match the explicit mesh faces')
        if self.shapes and self.mesh_samples:
            raise ValueError('sampled mesh animation cannot combine with relative shape deformations')
        if self.mesh_samples and (self.kind != 'mesh' or any(len(s.vertices) != len(self.vertices) for s in self.mesh_samples)):
            raise ValueError('mesh samples must preserve the explicit mesh vertex count')
        if self.kind == 'mesh':
            if not self.vertices or not self.faces:
                raise ValueError('mesh requires vertices and faces')
            for face in self.faces:
                if not 3 <= len(face) <= 32 or max(face) >= len(self.vertices):
                    raise ValueError('mesh face references an invalid vertex')
        if self.kind == 'curve' and len(self.points) < 2:
            raise ValueError('curve requires at least two points')
        if self.radii and (self.kind != 'curve' or len(self.radii) != len(self.points)):
            raise ValueError('curve radii must match points')
        if self.shapes and self.kind not in ('mesh','asset'):
            raise ValueError('shape deformation requires an explicit mesh')
        if (self.kind == 'asset') != bool(self.asset):
            raise ValueError('asset kind requires a named asset recipe')
        return self


class Camera(Model):
    location: Vec3 = (6, -9, 5)
    target: Vec3 = (0, 0, 1)
    lens: Annotated[float, Field(ge=10, le=250)] = 50
    orthographic: bool = False
    ortho_scale: Annotated[float, Field(ge=.1, le=100)] = 8
    aperture: Annotated[float, Field(ge=0, le=64)] = 0
    keys: Annotated[list[Key], Field(max_length=120)] = []
    target_keys: Annotated[list[Key], Field(max_length=120)] = []
    frame_keys: Annotated[list[FrameKey], Field(max_length=43200)] = []
    target_frame_keys: Annotated[list[FrameKey], Field(max_length=14400)] = []


class Light(Model):
    kind: Literal['AREA', 'POINT', 'SUN', 'SPOT'] = 'AREA'
    location: Vec3
    target: Vec3 = (0, 0, 0)
    color: Color = '#ffffff'
    energy: Annotated[float, Field(ge=0, le=20000)] = 800
    size: Annotated[float, Field(ge=.01, le=100)] = 5


class Shot(Model):
    name: Annotated[str, Field(min_length=1, max_length=100)]
    start: Annotated[float, Field(ge=0, le=60, allow_inf_nan=False)]
    end: Annotated[float, Field(gt=0, le=60, allow_inf_nan=False)]
    description: Annotated[str, Field(max_length=2000)]
    background: Color = '#181b20'
    camera: Camera
    lights: Annotated[list[Light], Field(min_length=1, max_length=12)]
    objects: Annotated[list[Object], Field(min_length=1, max_length=600)]

    @model_validator(mode='after')
    def relationships(self):
        ids = {o.id for o in self.objects}
        if len(ids) != len(self.objects):
            raise ValueError('object IDs must be unique within a shot')
        parents = {o.id: o.parent for o in self.objects}
        for obj in self.objects:
            seen = {obj.id}
            current = obj.parent
            while current:
                if current not in ids or current in seen:
                    raise ValueError('invalid or cyclic object parent')
                seen.add(current)
                current = parents[current]
        return self


class Caption(Model):
    text: Annotated[str, Field(min_length=1, max_length=500)]
    first_frame: Annotated[int, Field(ge=0, le=14399)]
    end_frame: Annotated[int, Field(ge=1, le=14400)]
    x: Annotated[float, Field(ge=0, le=1)] = .5
    y: Annotated[float, Field(ge=0, le=1)] = .8
    width: Annotated[float, Field(gt=0, le=1)] = .5
    height: Annotated[float, Field(gt=0, le=.5)] = .035
    stroke: Annotated[float, Field(ge=0, le=.02)] = .0015


class Plan(Model):
    schema_version: Literal[1, 2] = 1
    timeline: Timeline | None = None
    captions: Annotated[list[Caption], Field(max_length=300)] = []
    engine: Literal['auto', 'CYCLES', 'BLENDER_EEVEE'] = 'auto'
    view_transform: Literal['AgX', 'Standard'] = 'AgX'
    title: Annotated[str, Field(min_length=1, max_length=100)]
    summary: Annotated[str, Field(max_length=4000)]
    limitations: Annotated[list[Annotated[str, Field(max_length=1000)]], Field(max_length=30)]
    materials: Annotated[list[Material], Field(min_length=1, max_length=100)]
    shots: Annotated[list[Shot], Field(min_length=1, max_length=12)]

    @model_validator(mode='after')
    def material_references(self):
        for material in self.materials:
            frames = [sample.frame for sample in material.color_samples]
            if frames and (not self.timeline or max(frames) >= self.timeline.frame_count or len(frames) != len(set(frames))):
                raise ValueError('material color samples require unique frames inside the timeline')
        for caption in self.captions:
            if not self.timeline or not caption.first_frame < caption.end_frame <= self.timeline.frame_count:
                raise ValueError('caption must have a valid frame interval inside the timeline')
        ids = {m.id for m in self.materials}
        if len(ids) != len(self.materials):
            raise ValueError('material IDs must be unique')
        if sum(len(s.objects) for s in self.shots) > 3000:
            raise ValueError('project exceeds 3000 objects')
        if sum(len(o.vertices) for s in self.shots for o in s.objects) > 1000000:
            raise ValueError('project exceeds one million explicit vertices')
        for shot in self.shots:
            tracks = [shot.camera.frame_keys, shot.camera.target_frame_keys]
            tracks.extend(o.frame_keys for o in shot.objects)
            if any(k.property != 'location' for k in shot.camera.target_frame_keys):
                raise ValueError('camera target frame keys must animate location')
            for track in tracks:
                if track and self.timeline is None:
                    raise ValueError('frame keys require a timeline')
                seen = set()
                for key in track:
                    if key.frame >= self.timeline.frame_count:
                        raise ValueError('frame key is outside the timeline')
                    identity = (key.frame, key.property)
                    if identity in seen:
                        raise ValueError('duplicate frame key')
                    seen.add(identity)
            for obj in shot.objects:
                if obj.material and obj.material not in ids:
                    raise ValueError(f'unknown material: {obj.material}')
                if any(name not in ids for name in obj.face_materials):
                    raise ValueError('unknown face material')
                if obj.mesh_samples:
                    if self.timeline is None:
                        raise ValueError('mesh samples require a timeline')
                    frames = [s.frame for s in obj.mesh_samples]
                    if len(frames) != len(set(frames)) or max(frames) >= self.timeline.frame_count:
                        raise ValueError('duplicate or out-of-range mesh sample')
                if obj.keys and obj.frame_keys:
                    raise ValueError('use either seconds or frame keys for an object')
            if (shot.camera.keys and shot.camera.frame_keys) or (shot.camera.target_keys and shot.camera.target_frame_keys):
                raise ValueError('use either seconds or frame keys for a camera track')
        if sum(len(s.vertices) for shot in self.shots for o in shot.objects for s in o.mesh_samples) > 3000000:
            raise ValueError('project exceeds three million sampled vertices')
        return self


def validate_timing(plan: Plan, duration: float):
    if plan.timeline and abs(plan.timeline.frame_count * plan.timeline.fps_den / plan.timeline.fps_num - duration) > 1e-6:
        raise ValueError('duration must match the exact timeline frame count and rate')
    cursor = 0.0
    for shot in plan.shots:
        if abs(shot.start - cursor) > .002 or shot.end <= shot.start:
            raise ValueError('shots must cover the clip consecutively without gaps or overlaps')
        for keys in [shot.camera.keys, shot.camera.target_keys, *(o.keys for o in shot.objects), *(shape.keys for o in shot.objects for shape in o.shapes)]:
            for key in keys:
                if key.t > shot.end - shot.start + .002:
                    raise ValueError('keyframe extends beyond its shot')
        if any(k.property != 'location' for k in shot.camera.target_keys):
            raise ValueError('camera target keyframes must animate location')
        cursor = shot.end
    if abs(cursor - duration) > .05:
        raise ValueError('shots must cover the complete reference duration')


class ObjectAdjustment(Model):
    shot: Annotated[int, Field(ge=0, le=11)]
    object_id: Annotated[str, Field(min_length=1, max_length=60)]
    translation: Vec3 = (0,0,0)
    scale_multiplier: tuple[Annotated[float, Field(gt=0, le=10)], Annotated[float, Field(gt=0, le=10)], Annotated[float, Field(gt=0, le=10)]] = (1,1,1)


class LightAdjustment(Model):
    shot: Annotated[int, Field(ge=0, le=11)]
    index: Annotated[int, Field(ge=0, le=11)]
    light: Light


class MeasuredRevision(Model):
    materials: Annotated[list[Material], Field(max_length=100)] = []
    adjustments: Annotated[list[ObjectAdjustment], Field(max_length=600)] = []
    lights: Annotated[list[LightAdjustment], Field(max_length=144)] = []
    limitations: Annotated[list[Annotated[str, Field(max_length=1000)]], Field(max_length=20)] = []


def strict_schema(model=Plan):
    schema = model.model_json_schema()
    def visit(value):
        if isinstance(value, dict):
            value.pop('default', None)
            if 'prefixItems' in value:
                value['items'] = value.pop('prefixItems')[0]
            if value.get('type') == 'object':
                value['additionalProperties'] = False
                value['required'] = list(value.get('properties', {}))
            for item in value.values():
                visit(item)
        elif isinstance(value, list):
            for item in value:
                visit(item)
    visit(schema)
    return schema


def fixture_plan():
    return Plan(title='Ball drop · pipeline test', summary='Authored test scene: a coral sphere drops onto a circular plinth. This is a renderer fixture, not an AI remake.', limitations=['Synthetic pipeline test; does not measure reference reconstruction fidelity.'], materials=[Material(id='coral', color='#f16f45'), Material(id='chalk', color='#c7c9c2'), Material(id='floor', color='#323a3c')], shots=[Shot(name='The drop', start=0, end=2, description='A ball drops and rebounds on a studio plinth.', camera=Camera(location=(5, -8, 4), target=(0, 0, 1.1), lens=48), lights=[Light(location=(2, -4, 7), energy=1200), Light(location=(-4, 1, 4), color='#a9d9ed', energy=900)], objects=[Object(id='ball', kind='sphere', material='coral', scale=(.52, .52, .52), location=(0, 0, 2.6), keys=[Key(t=0, property='location', value=(0, 0, 2.6)), Key(t=.8, property='location', value=(0, 0, .9)), Key(t=1.15, property='location', value=(0, 0, 1.5)), Key(t=1.65, property='location', value=(0, 0, .9)), Key(t=2, property='location', value=(0, 0, .9))]), Object(id='plinth', kind='cylinder', material='chalk', location=(0, 0, .2), scale=(1.5, 1.5, .2), bevel=.06), Object(id='ground', kind='plane', material='floor', scale=(200, 200, 200))])])
