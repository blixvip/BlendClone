import pytest
from app.models import Material,Object,Plan,fixture_plan


def mesh(**extra):
    return Object(id='layer',kind='mesh',vertices=[(0,0,0),(1,0,0),(0,1,0),(1,1,0)],faces=[[0,1,2],[1,3,2]],**extra)


def test_distinct_surface_materials_survive_plan_roundtrip():
    plan=fixture_plan()
    plan.shots[0].objects.append(mesh(face_materials=['coral','chalk']))
    assert Plan.model_validate_json(plan.model_dump_json()).shots[0].objects[-1].face_materials==['coral','chalk']


def test_face_materials_must_match_topology():
    with pytest.raises(ValueError,match='face material'):
        mesh(face_materials=['coral'])


def test_unknown_face_material_is_rejected():
    plan=fixture_plan()
    plan.shots[0].objects.append(mesh(face_materials=['coral','missing']))
    with pytest.raises(ValueError,match='material'):
        Plan.model_validate(plan.model_dump())
