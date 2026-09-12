"""Compact, deterministic mesh construction. No Blender dependency; usable by planners."""
import math


def loft(profile, sides=40, centers=None):
    vertices, faces = [], []
    for n, (z, rx, ry) in enumerate(profile):
        cx, cy = centers[n] if centers else (0, 0)
        for i in range(sides):
            a = i * math.tau / sides
            vertices.append((cx + rx*math.cos(a), cy + ry*math.sin(a), z))
    for j in range(len(profile)-1):
        for i in range(sides):
            a, b = j*sides+i, j*sides+(i+1)%sides
            faces.append([a,b,b+sides,a+sides])
    # Triangulated caps avoid oversized polygons and preserve smooth side topology.
    for row, reverse in [(0,True),(len(profile)-1,False)]:
        ring = vertices[row*sides:(row+1)*sides]
        center = tuple(sum(v[k] for v in ring)/sides for k in range(3))
        index = len(vertices); vertices.append(center)
        for i in range(sides):
            tri = [index,row*sides+i,row*sides+(i+1)%sides]
            faces.append(tri[::-1] if reverse else tri)
    return vertices, faces


def heightfield(width, depth, nx=64, ny=48, height=None, y_start=None):
    vertices, faces = [], []
    start = -depth/2 if y_start is None else y_start
    for j in range(ny+1):
        y = start + depth*j/ny
        for i in range(nx+1):
            x = -width/2 + width*i/nx
            vertices.append((x,y,height(x,y) if height else 0))
    for j in range(ny):
        for i in range(nx):
            a = j*(nx+1)+i
            faces.append([a,a+1,a+nx+2,a+nx+1])
    return vertices, faces


def deform_vertices(vertices, center, radius, displacement):
    result = []
    for vertex in vertices:
        distance = sum(((vertex[i]-center[i])/max(.001,radius[i]))**2 for i in range(3))
        influence = math.exp(-distance*2)
        result.append(tuple(vertex[i]+displacement[i]*influence for i in range(3)))
    return result


def ellipsoid_cloud(instances, sides=12, rings=8):
    vertices, faces = [], []
    for center, scale in instances:
        offset = len(vertices)
        for j in range(rings+1):
            theta = math.pi * (j+.001)/(rings+.002)
            for i in range(sides):
                phi = math.tau*i/sides
                unit = (math.sin(theta)*math.cos(phi),math.sin(theta)*math.sin(phi),math.cos(theta))
                vertices.append(tuple(center[k]+unit[k]*scale[k] for k in range(3)))
        for j in range(rings):
            for i in range(sides):
                a=offset+j*sides+i; b=offset+j*sides+(i+1)%sides
                faces.append([a,a+sides,b+sides,b])
    return vertices, faces


def ribbon(points, width=.1, depth=.06):
    """Closed beveled-tool blank along a path in X/Z."""
    vertices, faces = [], []
    for x,y,z in points:
        vertices.extend([(x-width/2,y-depth/2,z),(x+width/2,y-depth/2,z),(x+width/2,y+depth/2,z),(x-width/2,y+depth/2,z)])
    for j in range(len(points)-1):
        for i in range(4):
            a=j*4+i;b=j*4+(i+1)%4
            faces.append([a,b,b+4,a+4])
    faces.extend([[3,2,1,0],list(range((len(points)-1)*4,len(points)*4))])
    return vertices,faces
