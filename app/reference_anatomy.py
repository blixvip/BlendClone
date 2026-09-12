"""Reference-measured cutaway geometry. Every visible part is an editable mesh/curve."""
import math
import random
from .models import Material,Object,Key
from .geometry import loft,ellipsoid_cloud
from .anatomy import mesh,tube


def world(pixel):
    x,y=pixel
    return ((x/1080-.5)*4.5,(.5-y/1920)*8-1.1)


def lower_cap(x):return .08-.36*math.exp(-((x-.25)/1.5)**2)


def wall_y(x,z):
    tract=.22*math.exp(-((x-(.1+.23*(z+.6)))/.42)**2)
    lobes=sum(.32*math.exp(-((x-cx)/.78)**2-((z-cz)/.8)**2) for cx,cz in [(-1.25,-2.55),(.95,-2.3),(-2.6,-1.6),(2.6,-1.8)])
    return -.02-lobes+.015*math.sin(x*12+z*17)+tract


def materials():
    return [
        Material(id='hero_cap',color='#EE151D',detail_color='#FF4146',pattern='skin',texture_scale=22,bump=.13,roughness=.34,coat=.2,subsurface=0),
        Material(id='hero_dermis',color='#CF1921',detail_color='#F45C57',pattern='noise',texture_scale=1.4,bump=.1,roughness=.23,coat=.5,subsurface=.06),
        Material(id='hero_cells',color='#A90610',detail_color='#E33931',pattern='noise',texture_scale=3,bump=.08,roughness=.15,coat=.7,subsurface=.07),
        Material(id='hero_fat',color='#ED830F',detail_color='#FFCF82',pattern='noise',texture_scale=2,roughness=.19,coat=.6,subsurface=.16),
        Material(id='hero_fat_light',color='#F5A33E',detail_color='#FFE3AD',pattern='noise',texture_scale=3,roughness=.18,coat=.65,subsurface=.18),
        Material(id='hero_hair',color='#1C0C0D',roughness=.18,coat=.7),
        Material(id='hero_nerve',color='#FFE7DC',roughness=.22,emission=.3),
        Material(id='hero_vessel',color='#200A1A',roughness=.15,coat=.9),
        Material(id='hero_shard',color='#203624',detail_color='#758E77',pattern='wood',texture_scale=12,stretch=(9,9,.17),bump=.25,roughness=.36),
        Material(id='hero_pus',color='#C9E52E',emission=2.5,roughness=.34),
        Material(id='hero_pus_hot',color='#EDFF99',emission=6,roughness=.3),
        Material(id='hero_blue',color='#48B5E7',unlit=True,emission=1,camera_only=True),
    ]


def cutaway(duration=3):
    rng=random.Random(718);objects=[]
    # Thick rounded cap, with its own rounded front edge and a curved lower boundary.
    vertices=[];faces=[];nx=160;ring=72
    for i in range(nx+1):
        x=-3+6*i/nx
        top=.32+1.62*math.exp(-abs((x-.3)/1.6)**2.7)
        bottom=lower_cap(x)
        for j in range(ring):
            a=math.tau*j/ring
            y=1.15+1.34*math.copysign(abs(math.cos(a))**.2,math.cos(a))
            z=(top+bottom)/2+(top-bottom)/2*math.sin(a)
            vertices.append((x,y,z+.018*math.sin(x*9+y*2)))
    for i in range(nx):
        for j in range(ring):
            a=i*ring+j;b=i*ring+(j+1)%ring
            faces.append([a,b,b+ring,a+ring])
    objects.append(mesh('rounded_inflamed_cap',vertices,faces,'hero_cap'))
    # Exposed dermis has sculpted relief rather than a flat backing wall.
    vertices=[];faces=[];nx=160;nz=120
    for j in range(nz+1):
        t=j/nz
        for i in range(nx+1):
            x=-3+6*i/nx;top=lower_cap(x)-.34
            bottom=-3.8+.16*math.sin(x*2)+.1*math.cos(x*5)
            z=bottom*(1-t)+top*t
            vertices.append((x,wall_y(x,z),z))
    for j in range(nz):
        for i in range(nx):
            a=j*(nx+1)+i;faces.append([a,a+nx+1,a+nx+2,a+1])
    objects.append(mesh('sculpted_dermis',vertices,faces,'hero_dermis'))
    # Irregular, angular epidermal cells tucked under the rounded skin cap.
    cells=[]
    for row in range(3):
        for i in range(31):
            x=-3.1+i*.205+(row%2)*.1+rng.uniform(-.035,.035)
            z=lower_cap(x)-.055-row*.115+rng.uniform(-.025,.025)
            cells.append(((x,-.045,z),(.115+rng.uniform(-.02,.02),.13,.08+rng.uniform(-.015,.02))))
    v,f=ellipsoid_cloud(cells,12,8)
    for k,(center,scale) in enumerate(cells):
        for n in range(108):
            index=k*108+n;co=v[index]
            unit=[(co[a]-center[a])/scale[a] for a in range(3)]
            v[index]=tuple(center[a]+scale[a]*math.copysign(abs(unit[a])**.55,unit[a]) for a in range(3))
    objects.append(mesh('irregular_epidermal_cells',v,f,'hero_cells',subdivision=1))
    # Fat lobules overlap and vary in size; warm tissue fills behind them.
    objects.append(Object(id='fat_backing',kind='cube',material='hero_fat',location=(0,.3,-4.8),scale=(4,.3,1.25)))
    for band in range(2):
        cells=[]
        for j in range(9):
            for i in range(27):
                x=-3.2+i*.25+rng.uniform(-.08,.08)
                z=-3.9-j*.2+.13*math.sin(x*3)+rng.uniform(-.08,.08)
                r=rng.uniform(.12,.21)
                cells.append(((x,-.1+band*.19,z),(r,r*.8,r*.83)))
        v,f=ellipsoid_cloud(cells,16,10)
        objects.append(mesh(f'fat_lobules_{band}',v,f,'hero_fat' if band else 'hero_fat_light'))
    # Source-measured main follicles and their hair shafts.
    for i,(px,py,tip) in enumerate([(178,1020,2.18),(758,967,-.35)]):
        x,z=world((px,py))
        profile=[(z,.005,.005),(z+.04,.075,.05),(z+.13,.13,.07),(z+.25,.135,.075),(z+.4,.075,.055),(z+.75,.035,.028),(tip,.005,.005)]
        v,f=loft(profile,36)
        objects.append(mesh(f'hair_follicle_{i}',v,f,'hero_hair',location=(x,-.24,0)))
        rim=[(x-.15,-.17,z+.34),(x-.13,-.18,z+.03),(x,-.19,z-.06),(x+.14,-.18,z+.1),(x+.095,-.17,z+.4)]
        objects.append(tube(f'follicle_rim_{i}',rim,'hero_nerve',.012))
        if i==0:
            for k,dx in enumerate([-.045,.04]):
                objects.append(tube(f'follicle_hair_{k}',[(x,-.17,z+.5),(x+dx,-.16,1.3),(x+dx*2,-.15,2.25+k*.08)],'hero_hair',.013,[1,.6,0]))
    for i in range(16):
        x=rng.uniform(-3,3);y=rng.uniform(1.8,4)
        objects.append(tube(f'distant_hair_{i}',[(x,y,.2),(x+.025,y,1),(x+.04,y,rng.uniform(1.4,2.1))],'hero_hair',.012,[1,.7,0]))
    # Trace the visible branching networks in image coordinates, then place on relief.
    nerve_paths=[
        [(0,1055),(105,1085),(190,1110),(260,1100),(318,1120),(390,1050),(423,976),(468,998),(527,1115),(614,1095),(693,1036),(753,969),(839,999),(936,945),(1035,1025),(1080,1030)],
        [(0,1510),(140,1480),(280,1510),(360,1450),(430,1508),(530,1580),(630,1500),(750,1430),(900,1370),(1080,1240)],
        [(10,1660),(150,1610),(240,1510),(280,1380),(388,1290),(403,1170),(365,1040),(340,938),(265,838)],
        [(485,1690),(495,1530),(493,1440),(525,1370),(569,1250),(675,1210),(746,1120),(837,1085),(842,966),(820,861)],
        [(1050,1500),(963,1413),(920,1320),(964,1200),(990,1080),(950,1000),(987,890)],
        [(320,1120),(294,1190),(230,1210),(186,1235),(95,1202),(10,1230)],
        [(527,1115),(595,1176),(655,1175),(674,1210)],
        [(750,1430),(740,1340),(800,1240),(827,1190)],
        [(403,1170),(468,1150),(470,1078),(450,1020)],
        [(1080,800),(1002,817),(974,873),(910,901),(832,861)],
    ]
    for i,path in enumerate(nerve_paths):
        points=[]
        for j in range(len(path)-1):
            a,b=path[j],path[j+1]
            for k in range(4):
                t=k/4;x,z=world((a[0]*(1-t)+b[0]*t+rng.uniform(-5,5),a[1]*(1-t)+b[1]*t+rng.uniform(-5,5)))
                points.append((x,wall_y(x,z)-.026,z))
        x,z=world(path[-1]);points.append((x,wall_y(x,z)-.026,z))
        objects.append(tube(f'nerve_trace_{i}',points,'hero_nerve',.0065))
    vessel_paths=[
        ([(0,1560),(104,1630),(157,1688),(257,1740),(390,1735),(470,1750),(563,1740),(684,1710),(816,1650),(980,1620),(1080,1600)],.055),
        ([(0,1840),(149,1900),(310,1920),(440,1900),(555,1850),(680,1810),(809,1780),(945,1800),(1080,1770)],.05),
        ([(445,1900),(483,1760),(564,1620),(617,1530),(646,1460),(687,1360),(760,1280),(765,1210)],.047),
        ([(157,1688),(183,1540),(176,1430),(132,1370),(110,1290),(154,1210),(199,1160)],.034),
        ([(110,1290),(51,1330),(0,1380)],.021),
        ([(132,1370),(233,1374),(335,1288),(405,1280)],.021),
        ([(564,1620),(510,1515),(491,1420),(430,1330)],.029),
        ([(617,1530),(738,1490),(782,1390),(822,1320),(825,1230)],.023),
        ([(1080,1510),(957,1430),(928,1360),(958,1300),(948,1210)],.034),
        ([(928,1360),(861,1350),(813,1280)],.018),
    ]
    for i,(path,r) in enumerate(vessel_paths):
        points=[]
        for px,py in path:
            x,z=world((px,py));points.append((x,min(-.34,wall_y(x,z)-.07),z))
        radii=[max(.04,1-j/(len(path)-1)) if i>1 else 1 for j in range(len(path))]
        objects.append(tube(f'vessel_trace_{i}',points,'hero_vessel',r,radii))
    # Irregular shard, with visible longitudinal ridges.
    v,f=loft([(0,.004,.003),(.25,.039,.022),(1.3,.064,.03),(2.6,.054,.025),(3.1,.013,.007)],12,centers=[(0,0),(.04,0),(.23,0),(.56,0),(.68,0)])
    objects.append(mesh('embedded_shard',v,f,'hero_shard',location=(-.68,-.39,-3.62),smooth=False))
    for i in range(44):
        z=rng.uniform(-3.8,-.65);x=-.68+.22*(z+3.62)+rng.uniform(-.32,.32);r=rng.uniform(.032,.084)
        objects.append(Object(id=f'pressure_particle_{i}',kind='sphere',material='hero_pus_hot' if i%3==0 else 'hero_pus',location=(x,-.48,z),scale=(r,r*.65,r*rng.uniform(.8,1.4)),
            keys=[Key(t=0,property='location',value=(x,-.48,z)),Key(t=duration,property='location',value=(x+.09*math.sin(i),-.48,z+.16))]))
    objects.append(Object(id='blue_backdrop',kind='plane',material='hero_blue',location=(0,12,0),rotation=(90,0,0),scale=(100,100,100)))
    return objects
