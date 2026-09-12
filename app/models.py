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
    t: Annotated[float, Field(ge=0, le=30, allow_inf_nan=False)]
    property: Literal['location', 'rotation', 'scale']
    value: Vec3
    interpolation: Literal['LINEAR', 'BEZIER', 'CONSTANT'] = 'BEZIER'


class Material(Model):
    id: Annotated[str, Field(pattern=r'^[a-zA-Z0-9_-]{1,60}$')]
    color: Color
    roughness: Annotated[float, Field(ge=0, le=1)] = .45
    metallic: Annotated[float, Field(ge=0, le=1)] = 0
    emission: Annotated[float, Field(ge=0, le=10)] = 0


class Object(Model):
    id: Annotated[str, Field(pattern=r'^[a-zA-Z0-9_-]{1,60}$')]
    kind: Literal['cube', 'sphere', 'cylinder', 'cone', 'torus', 'plane', 'mesh', 'curve', 'empty', 'text']
    material: str = ''
    parent: str = ''
    location: Vec3 = (0, 0, 0)
    rotation: Vec3 = (0, 0, 0)
    scale: Vec3 = (1, 1, 1)
    vertices: Annotated[list[Vec3], Field(max_length=12000)] = []
    faces: Annotated[list[list[Annotated[int, Field(ge=0)]]], Field(max_length=12000)] = []
    points: Annotated[list[Vec3], Field(max_length=2000)] = []
    thickness: Annotated[float, Field(ge=.001, le=10)] = .04
    text: Annotated[str, Field(max_length=500)] = ''
    bevel: Annotated[float, Field(ge=0, le=2)] = 0
    subdivision: Annotated[int, Field(ge=0, le=2)] = 0
    smooth: bool = True
    keys: Annotated[list[Key], Field(max_length=240)] = []

    @model_validator(mode='after')
    def geometry(self):
        if self.kind == 'mesh':
            if not self.vertices or not self.faces:
                raise ValueError('mesh requires vertices and faces')
            for face in self.faces:
                if not 3 <= len(face) <= 32 or max(face) >= len(self.vertices):
                    raise ValueError('mesh face references an invalid vertex')
        if self.kind == 'curve' and len(self.points) < 2:
            raise ValueError('curve requires at least two points')
        return self


class Camera(Model):
    location: Vec3 = (6, -9, 5)
    target: Vec3 = (0, 0, 1)
    lens: Annotated[float, Field(ge=10, le=250)] = 50
    orthographic: bool = False
    ortho_scale: Annotated[float, Field(ge=.1, le=100)] = 8
    keys: Annotated[list[Key], Field(max_length=120)] = []
    target_keys: Annotated[list[Key], Field(max_length=120)] = []


class Light(Model):
    kind: Literal['AREA', 'POINT', 'SUN', 'SPOT'] = 'AREA'
    location: Vec3
    target: Vec3 = (0, 0, 0)
    color: Color = '#ffffff'
    energy: Annotated[float, Field(ge=0, le=20000)] = 800
    size: Annotated[float, Field(ge=.01, le=100)] = 5


class Shot(Model):
    name: Annotated[str, Field(min_length=1, max_length=100)]
    start: Annotated[float, Field(ge=0, le=30, allow_inf_nan=False)]
    end: Annotated[float, Field(gt=0, le=30, allow_inf_nan=False)]
    description: Annotated[str, Field(max_length=2000)]
    background: Color = '#181b20'
    camera: Camera
    lights: Annotated[list[Light], Field(min_length=1, max_length=12)]
    objects: Annotated[list[Object], Field(min_length=1, max_length=240)]

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


class Plan(Model):
    title: Annotated[str, Field(min_length=1, max_length=100)]
    summary: Annotated[str, Field(max_length=4000)]
    limitations: Annotated[list[Annotated[str, Field(max_length=1000)]], Field(max_length=30)]
    materials: Annotated[list[Material], Field(min_length=1, max_length=100)]
    shots: Annotated[list[Shot], Field(min_length=1, max_length=12)]

    @model_validator(mode='after')
    def material_references(self):
        ids = {m.id for m in self.materials}
        if len(ids) != len(self.materials):
            raise ValueError('material IDs must be unique')
        if sum(len(s.objects) for s in self.shots) > 600:
            raise ValueError('project exceeds 600 objects')
        for shot in self.shots:
            for obj in shot.objects:
                if obj.material and obj.material not in ids:
                    raise ValueError(f'unknown material: {obj.material}')
        return self


def validate_timing(plan: Plan, duration: float):
    cursor = 0.0
    for shot in plan.shots:
        if abs(shot.start - cursor) > .002 or shot.end <= shot.start:
            raise ValueError('shots must cover the clip consecutively without gaps or overlaps')
        for keys in [shot.camera.keys, shot.camera.target_keys, *(o.keys for o in shot.objects)]:
            for key in keys:
                if key.t > shot.end - shot.start + .002:
                    raise ValueError('keyframe extends beyond its shot')
        if any(k.property != 'location' for k in shot.camera.target_keys):
            raise ValueError('camera target keyframes must animate location')
        cursor = shot.end
    if abs(cursor - duration) > .05:
        raise ValueError('shots must cover the complete reference duration')


def strict_schema():
    schema = Plan.model_json_schema()
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
