import pytest
from app.models import Material, Object, Plan, fixture_plan, validate_timing
from app.geometry import loft, heightfield, ellipsoid_cloud, deform_vertices
from app.media import download_arguments


def test_split_youtube_streams_are_supported():
    args = download_arguments('https://www.youtube.com/shorts/example', 'source.bin')
    selection = args[args.index('-f')+1]
    assert 'bestvideo' in selection and '+bestaudio' in selection
    assert '--merge-output-format' in args


def test_full_short_duration_is_preserved():
    plan = fixture_plan()
    plan.shots[0].end = 30.363667
    parsed = Plan.model_validate(plan.model_dump())
    validate_timing(parsed, 30.363667)


def test_loft_has_closed_caps_and_distinct_profile():
    vertices, faces = loft([(0, .2, .3), (1, .6, .5), (2, .1, .2)], sides=16)
    assert len(vertices) > 32 and len(faces) > 32
    assert max(v[2] for v in vertices) == 2
    assert all(0 <= i < len(vertices) for face in faces for i in face)


def test_swelling_deforms_surface_without_changing_topology():
    vertices, faces = heightfield(4, 4, 20, 20)
    changed = deform_vertices(vertices, center=(0,0,0), radius=(1,1,1), displacement=(0,0,1))
    assert len(changed) == len(vertices)
    assert max(v[2] for v in changed) > .9
    assert abs(changed[0][2]) < .001


def test_cells_are_one_editable_mesh():
    vertices, faces = ellipsoid_cloud([((0,0,0),(1,1,1)), ((2,0,0),(.5,.5,.5))], sides=12, rings=8)
    assert max(v[0] for v in vertices) >= 2.49
    assert len(faces) > 100
    Object(id='cells',kind='mesh',vertices=vertices,faces=faces)


def test_material_and_curve_radius_parameters_are_bounded():
    mat = Material(id='skin',color='#c88471',subsurface=.3,coat=.4,pattern='skin',bump=.18)
    assert mat.subsurface == .3
    with pytest.raises(ValueError):
        Material(id='skin',color='#c88471',subsurface=5)
    with pytest.raises(ValueError, match='radii'):
        Object(id='hair',kind='curve',points=[(0,0,0),(0,0,1)],radii=[1])
