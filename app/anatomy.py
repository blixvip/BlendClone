"""Editable anatomical illustration assets, developed against the splinter reference.

These are stylized procedural assets, not medically validated anatomy.
The compact recipes expand into ordinary meshes, curves, materials and shape keys.
"""
import math
import random
from .models import Material, Object, Plan
from .geometry import loft, heightfield, ellipsoid_cloud, ribbon


def palette():
    return [
        Material(id='skin_top',color='#D98779',detail_color='#EDAD99',pattern='skin',texture_scale=8,bump=.35,subsurface=.22,roughness=.4,coat=.1),
        Material(id='skin_finger',color='#D4877D',detail_color='#EDB2A1',pattern='skin',texture_scale=22,bump=.13,subsurface=.3,roughness=.46),
        Material(id='skin_macro',color='#D98779',detail_color='#EDAD99',pattern='wound',texture_scale=.8,bump=.7,subsurface=.22,roughness=.35,coat=.18),
        Material(id='skin_red',color='#C82F32',detail_color='#EF4545',pattern='skin',texture_scale=13,bump=.2,subsurface=.18,roughness=.27,coat=.32),
        Material(id='dermis',color='#B12F32',detail_color='#EF6561',pattern='noise',texture_scale=3,bump=.25,stretch=(1,1,2.8),subsurface=.17,roughness=.3,coat=.26),
        Material(id='epidermis',color='#AD3E43',detail_color='#E57473',pattern='noise',texture_scale=5,bump=.1,subsurface=.25,roughness=.23,coat=.3),
        Material(id='epidermis_light',color='#B84C4B',detail_color='#DF8D82',pattern='noise',texture_scale=8,bump=.1,subsurface=.2,roughness=.28,coat=.2),
        Material(id='fat',color='#E69824',detail_color='#FFD778',pattern='noise',texture_scale=3,subsurface=.23,roughness=.28,coat=.18),
        Material(id='fat_light',color='#F6AA3D',detail_color='#FFDC94',pattern='noise',subsurface=.23,roughness=.26,coat=.2),
        Material(id='hair',color='#201312',roughness=.28,coat=.25),
        Material(id='follicle_rim',color='#A44349',roughness=.25,subsurface=.25,coat=.2),
        Material(id='vessel',color='#25132C',roughness=.22,coat=.4),
        Material(id='nerve',color='#F3C5A0',emission=.14,roughness=.33),
        Material(id='wound',color='#6D191B',detail_color='#B93527',pattern='noise',texture_scale=5,bump=.2,roughness=.26,coat=.2),
        Material(id='splinter',color='#292D20',detail_color='#716545',pattern='wood',stretch=(8,8,.3),texture_scale=7,bump=.48,roughness=.57),
        Material(id='steel',color='#BDD0D3',metallic=.92,roughness=.2,coat=.25),
        Material(id='nail',color='#E1B3A4',detail_color='#F0D4C2',pattern='noise',texture_scale=20,subsurface=.12,roughness=.28,coat=.35),
        Material(id='crease',color='#A86057',roughness=.58),
        Material(id='pus',color='#C8E329',emission=1.5,subsurface=.2,roughness=.3),
        Material(id='pus_bright',color='#EDF888',emission=3,roughness=.35),
        Material(id='arrow',color='#BBCDFF',emission=2.4,roughness=.3),
        Material(id='wood_board',color='#727369',detail_color='#B5B5A2',pattern='wood',stretch=(7,2,.14),texture_scale=8,bump=.7,roughness=.85),
    ]


def mesh(name, vertices, faces, material, **kwargs):
    return Object(id=name,kind='mesh',vertices=vertices,faces=faces,material=material,**kwargs)


def tube(name, points, material, thickness=.02, radii=None, **kwargs):
    return Object(id=name,kind='curve',points=points,material=material,thickness=thickness,radii=radii or [],**kwargs)


def skin_section(seed):
    rng=random.Random(seed); objects=[]
    depression=lambda x: -.55*math.exp(-((x-.15)/.7)**2)
    top=lambda x,y: .006*math.sin(x*4+y*3)
    vertices,faces=heightfield(8,4,96,32,top,y_start=0)
    # A closed skin envelope: the lower rim remains anchored while the top inflates.
    upper_count=len(vertices)
    boundary=list(range(97))+[j*97+96 for j in range(1,33)]+list(range(32*97+95,32*97-1,-1))+[j*97 for j in range(31,0,-1)]
    for index in boundary:
        x,y,z=vertices[index];vertices.append((x,y,-.15))
    for i,index in enumerate(boundary):
        nxt=(i+1)%len(boundary)
        faces.append([index,upper_count+i,upper_count+nxt,boundary[nxt]])
    objects.append(mesh('skin_cap',vertices,faces,'skin_top'))
    base_vertices=[];base_faces=[]
    for i in range(97):
        x=-4+8*i/96
        base_vertices.extend([(x,.04,-.1),(x,.04,-.66+depression(x))])
    for i in range(96):base_faces.append([i*2,i*2+1,i*2+3,i*2+2])
    objects.append(mesh('epidermis_backing',base_vertices,base_faces,'epidermis'))
    vertices=[];faces=[]
    for j in range(41):
        t=j/40
        for i in range(97):
            x=-4+8*i/96
            z=-4.1*(1-t)+(-.5+depression(x))*t
            y=.05+.07*math.sin(x*3+z*4)*math.sin(z*5+x)
            vertices.append((x,y,z))
    for j in range(40):
        for i in range(96):
            a=j*97+i;faces.append([a,a+97,a+98,a+1])
    objects.append(mesh('dermis_wall',vertices,faces,'dermis'))
    # Packed epidermal cells form a real scalloped layer rather than a flat texture.
    batches=[[],[]]
    for row in range(4):
        for i in range(39):
            x=-4.15+i*.22+(row%2)*.11
            z=-.1-row*.135+depression(x)*(.25+.75*row/3)
            batches[(i+row)%2].append(((x,-.015+rng.uniform(-.035,.025),z),(.125+rng.uniform(-.014,.014),.14,.085)))
    for n,batch in enumerate(batches):
        v,f=ellipsoid_cloud(batch,12,8);objects.append(mesh(f'epidermis_cells_{n}',v,f,'epidermis' if n==0 else 'epidermis_light'))
    # Cut edge and tissue layer are curved, not rectangular slabs.
    line=[(-4+8*i/40,-.17,-.58+depression(-4+8*i/40)) for i in range(41)]
    objects.append(tube('basement_membrane',line,'nerve',.012))
    for band in range(2):
        batch=[]
        for row in range(12):
            for i in range(20):
                x=-4.2+i*.45+(row%2)*.21
                batch.append(((x,.08+band*.14,-3.94-row*.24+rng.uniform(-.1,.1)),(.24+rng.uniform(-.04,.04),.21,.2+rng.uniform(-.03,.02))))
        v,f=ellipsoid_cloud(batch,12,8);objects.append(mesh(f'fat_lobules_{band}',v,f,'fat' if band==0 else 'fat_light'))
    # Wound tract follows the embedded shard through the dermis.
    v,f=loft([(-2.65,.015,.01),(-2.3,.18,.035),(-1.6,.27,.035),(-.9,.31,.04),(-.45,.23,.04)],32,
             centers=[(-.42,-.12),(-.3,-.13),(-.1,-.14),(.12,-.14),(.2,-.14)])
    objects.append(mesh('wound_tract',v,f,'dermis'))
    for n,(x,bottom,tip) in enumerate([(-1.35,-1.45,1.75),(.95,-1.12,1.5)]):
        profile=[(bottom,.005,.005),(bottom+.09,.1,.07),(bottom+.24,.13,.09),(bottom+.47,.07,.055),(-.2,.023,.02),(0,.022,.018),(tip,.001,.001)]
        v,f=loft(profile,24);objects.append(mesh(f'follicle_{n}',v,f,'hair',location=(x,-.21,0)))
        outline=[(x-.12,-.18,bottom+.27),(x,-.18,bottom-.015),(x+.13,-.18,bottom+.25),(x+.055,-.18,-.18)]
        objects.append(tube(f'follicle_rim_{n}',outline,'follicle_rim',.025))
        if n==0:
            for k,dx in enumerate([-.14,.13]):
                objects.append(tube(f'hair_cluster_{k}',[(x,-.2,-.4),(x+dx*.4,-.2,.1),(x+dx,-.2,tip+.15)],'hair',.016,[1,.7,0]))
    for i in range(14):
        x=rng.uniform(-4,4);y=rng.uniform(.6,3.8);z=top(x,y)
        objects.append(tube(f'background_hair_{i}',[(x,y,z),(x+.025,y,z+.5),(x+.08,y,z+rng.uniform(.8,1.4))],'hair',.014,[1,.65,0]))
    # Branching nerve and vessel networks in front of the exposed tissue.
    for i in range(15):
        x=rng.uniform(-4,4);z=rng.uniform(-3.8,-.85)
        points=[(x,-.19,z),(x+.2,-.19,z+.17),(x+.28,-.2,z+.45),(x+.65,-.18,z+.7)]
        objects.append(tube(f'nerve_{i}',points,'nerve',.01,[1,1,.8,.15]))
        objects.append(tube(f'nerve_branch_{i}',[points[1],(x-.07,-.19,z+.32),(x-.2,-.2,z+.64)],'nerve',.008,[1,.8,0]))
    artery=[(-4,-.33,-3.55),(-2.7,-.35,-3.2),(-1.4,-.34,-3.38),(0,-.34,-3.48),(1.8,-.34,-3.23),(4,-.32,-3.25)]
    artery=[(x,y,z-.9) for x,y,z in artery]
    objects.append(tube('vessel_main',artery,'vessel',.09,[1,1,1,.85,.6,.3]))
    for i in range(8):
        x=-3.6+i*.95;z=-4.2+rng.uniform(-.1,.2)
        points=[(x,-.34,z),(x-.25,-.29,z+.4),(x-.07,-.28,z+.8),(x-.24,-.26,z+1.15)]
        objects.append(tube(f'vessel_{i}',points,'vessel',.045,[1,.8,.4,0]))
        objects.append(tube(f'vessel_branch_{i}',[points[1],(x+.17,-.27,z+.55),(x+.5,-.24,z+.68)],'vessel',.025,[1,.6,0]))
    return objects


def skin_surface(seed):
    rng=random.Random(seed);objects=[]
    seeds=[(i*.9+rng.uniform(-.3,.3),j*.9+rng.uniform(-.3,.3)) for i in range(-11,12) for j in range(-11,12)]
    def surface(x,y):
        nearest=sorted((x-a)**2+(y-b)**2 for a,b in seeds)[:2]
        edge=min(1,(nearest[1]-nearest[0])/.13)
        return .065*edge*edge*(3-2*edge)-.13*math.exp(-(x*x+y*y)*5)
    v,f=heightfield(18,18,180,180,surface)
    objects.append(mesh('skin_surface',v,f,'skin_macro',subdivision=1))
    for i in range(78):
        x=rng.uniform(-7.5,7.5);y=rng.uniform(-6,8)
        if x*x+y*y<2:continue
        z=surface(x,y);h=rng.uniform(.45,1.15)
        objects.append(tube(f'hair_{i}',[(x,y,z),(x+.03,y,z+h*.5),(x+.06,y+.04,z+h)],'hair',.016,[1,.7,0]))
    return objects


def finger(seed):
    profile=[(0,.44,.44),(.18,.49,.47),(.8,.48,.46),(1.2,.49,.46),(1.4,.45,.43),(1.65,.47,.45),(2.25,.44,.43),(2.55,.45,.43),(2.7,.41,.41),(3.25,.41,.41),(3.55,.39,.39),(3.75,.32,.34),(3.9,.21,.24),(3.97,.09,.12),(4,.001,.001)]
    v,f=loft(profile,64)
    objects=[mesh('finger_skin',v,f,'skin_finger',subdivision=1)]
    for joint in [1.38,1.5,2.58,2.7]:
        points=[]
        for i in range(13):
            a=math.pi+math.pi*i/12
            points.append((.455*math.cos(a),.449*math.sin(a)-.007,joint+.025*math.cos(a*2)))
        objects.append(tube('crease_'+str(int(joint*100)),points,'crease',.006))
    return objects


def hand(seed):
    objects=[]
    v,f=loft([(-2,.48,.35),(-1,.48,.35),(-.5,.5,.36),(0,.65,.4),(.5,.8,.4),(1,.82,.4),(1.5,.72,.35),(1.9,.45,.28),(2,.18,.12)],48)
    objects.append(mesh('palm',v,f,'skin_finger',subdivision=1))
    index=finger(seed)
    for o in index:
        o.id='index_'+o.id;o.location=(-.34,0,1.25);o.scale=(.66,.66,.7)
    objects.extend(index)
    for n,x in enumerate([.22,.63,.99]):
        profile=[(0,.23,.23),(.4,.26,.25),(.9,.25,.25),(1.3,.23,.23),(1.6,.2,.21),(1.83,.07,.09),(1.87,.001,.001)]
        centers=[(0,0),(0,0),(-.05,-.1),(-.12,-.38),(-.2,-.65),(-.27,-.74),(-.27,-.74)]
        v,f=loft(profile,32,centers)
        objects.append(mesh(f'curled_finger_{n}',v,f,'skin_finger',location=(x,0,.65-n*.14),scale=(1,1,1-n*.12),subdivision=1))
    v,f=loft([(0,.24,.23),(.4,.26,.25),(.85,.27,.25),(1.2,.22,.23),(1.45,.12,.14),(1.5,.001,.001)],32,centers=[(-.6,0),(-.85,-.1),(-.91,-.3),(-.73,-.5),(-.5,-.62),(-.48,-.64)])
    objects.append(mesh('thumb',v,f,'skin_finger',location=(0,0,.25),subdivision=1))
    return objects


def tweezers(seed):
    objects=[]
    for side in [-1,1]:
        path=[(side*.16,0,0),(side*.39,0,.55),(side*.32,0,2.4),(side*.11,0,3.5),(0,0,3.65)]
        v,f=ribbon(path,.08,.055)
        objects.append(mesh('jaw_left' if side<0 else 'jaw_right',v,f,'steel',bevel=.022))
    return objects


def splinter(seed):
    rng=random.Random(seed);profile=[];centers=[]
    for j,(z,r) in enumerate([(0,.001),(.08,.025),(.65,.055),(1.4,.064),(2.25,.044),(2.7,.013),(2.9,.001)]):
        profile.append((z,r,r*.45));centers.append((.16*z/2.9+rng.uniform(-.008,.008),0))
    v,f=loft(profile,9,centers)
    return [mesh('wood_shard',v,f,'splinter',smooth=False)]


BUILDERS={'skin_section':skin_section,'skin_surface':skin_surface,'finger':finger,'hand':hand,'tweezers':tweezers,'splinter':splinter}


def expand_assets(plan):
    result=plan.model_copy(deep=True)
    known={m.id for m in result.materials}
    for material in palette():
        if material.id not in known:result.materials.append(material)
    for shot in result.shots:
        expanded=[]
        for obj in shot.objects:
            if obj.kind!='asset':
                expanded.append(obj);continue
            root=obj.model_copy(deep=True)
            root.kind='empty';root.asset='';root.shapes=[]
            expanded.append(root)
            for child in BUILDERS[obj.asset](obj.seed):
                deformable=child.kind=='mesh' and child.id.startswith('skin_')
                child.id=(obj.id+'_'+child.id)[:60]
                child.parent=obj.id
                if deformable:
                    child.shapes=[s.model_copy(deep=True) for s in obj.shapes]
                    if obj.asset=='skin_section':
                        for shape in child.shapes:shape.radius=(shape.radius[0],shape.radius[1],.06)
                if obj.material and child.material.startswith('skin_'):child.material=obj.material
                expanded.append(child)
        shot.objects=expanded
    return Plan.model_validate(result.model_dump())
