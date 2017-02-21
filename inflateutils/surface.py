from __future__ import division
from vector import *
from exportmesh import *
import itertools
import os.path
import math

class InflationParams(object):
    def __init__(self, thickness=10., flatness=0., exponent=2., iterations=None):
        self.thickness = thickness
        self.flatness = flatness
        self.exponent = exponent
        self.iterations = iterations

def surfaceToMesh(data, center=False, twoSided=False, zClip=None, tolerance=0., color=None):
    # if center is False, the mesh coordinates are guaranteed to be integers corresponding exactly
    # to the points in the data, plus a layer of neighboring points.
    width = len(data)
    height = len(data[0])
    xMin = width - 1
    xMax = 0
    yMin = height - 1
    yMax = 0
        
    def getValue(*args):
        if len(args) == 1:
            x,y = args[0]
        else:
            x,y = args
            
        if x < 0 or x >= width or y < 0 or y >= height:
            return 0.
        else:
            if data[x][y] <= tolerance:
                return 0.
            elif zClip is None:
                return data[x][y]
            else:
                return min(data[x][y],zClip)

    for x in range(width):
        for y in range(height):
            if getValue(x,y) > 0.: 
                xMin = min(xMin, x)
                xMax = max(xMax, x)
                yMin = min(yMin, y)
                yMax = max(yMax, y)
    
    if center:
        offset = Vector( -0.5 * (xMin + xMax), -0.5 * (yMin + yMax) )
    else:
        offset = Vector( 0, 0 )
        
    mesh = []
    
    # this code could be made way more efficient
    
    for x in range(xMin - 1, xMax + 1):
        for y in range(yMin - 1, yMax + 1):
            v = Vector(x,y)
            numPoints = sum(1 for delta in ((0,0), (1,0), (0,1), (1,1)) if getValue(v+delta) > 0.)

            def triangles(d1, d2, d3):
                v1,v2,v3 = v+d1,v+d2,v+d3
                z1,z2,z3 = map(getValue, (v1,v2,v3))
                if (z1,z2,z3) == (0.,0.,0.):
                    return []
                v1 += offset
                v2 += offset
                v3 += offset
                output = [(color,(Vector(v1.x,v1.y,z1), Vector(v2.x,v2.y,z2), Vector(v3.x,v3.y,z3)))]
                if not twoSided:
                    z1,z2,z3 = 0.,0.,0.
                output.append ( (color,(Vector(v3.x,v3.y,-z3), Vector(v2.x,v2.y,-z2), Vector(v1.x,v1.y,-z1))) )
                return output
            
            if numPoints > 0:
                if getValue(v+(0,0)) == 0. and getValue(v+(1,1)) == 0.:
                    mesh += triangles((0,0), (1,0), (1,1))
                    mesh += triangles((1,1), (0,1), (0,0))
                else:
                    mesh += triangles((0,0), (1,0), (0,1))
                    mesh += triangles((1,0), (1,1), (0,1))

    return mesh

def inflateRaster(raster, inflationParams=InflationParams(), 
        deltas=(Vector(-1,0),Vector(1,0),Vector(0,1),Vector(0,-1),Vector(-1,-1),Vector(1,1),Vector(-1,1),Vector(1,-1)), distanceToEdge=None):
    """
    raster is a boolean matrix.
    
    flatness varies from 0 for a very gradual profile to something around 2-10 for a very flat top.
    
    Here's a rough way to visualize how inflateRaster() works. A random walk starts inside the region
    defined by the raster. If flatness is zero and exponent=1, it moves around randomly, and if T is the amount of time 
    to exit the region, then (E[T^p])^(1/p) will then yield the inflation height. If flatness is non-zero, in each time
    step it also has a chance of death proportional to the flatness, and death is deemed to also count as an
    exit. So if the flatness parameter is big, then well within the region, the process will tend to exit via death, 
    and so points well within the region will get similar height. 
    
    The default exponent value of 1.0 looks pretty good, but you can get nice rounding effects at exponent=2 and larger,
    and some interesting edge-flattening effects for exponents close to zero.
    
    The flatness parameter is scaled to be approximately invariant across spatial resolution changes,
    and some weighting of the process is used to reduce edge effects via the use of the distanceToEdge 
    function which measures how far a raster point is from the edge in a given direction in the case of
    a region not aligned perfectly with the raster.
    """
    
    deltaLengths = tuple(delta.norm() for delta in deltas)
    if distanceToEdge == None:
        distanceToEdge = lambda (x,y,i) : deltaLengths[i]
    
    width = len(raster)
    height = len(raster[0])

    k = len(deltas)
    alpha = 500 * inflationParams.flatness /  max(width,height)**2
    exponent = inflationParams.exponent
    invExponent = 1. / exponent
    
    if not inflationParams.iterations:
        iterations = 25 * max(width,height) 
    else:
        iterations = inflationParams.iterations
        
    data = [ [0. for y in range(height)] for x in range(width) ]
    
    for iter in range(iterations):
        newData = [ [0. for y in range(height)] for x in range(width) ]
        for x in range(width):
            for y in range(height):
                def z(dx,dy):
                    x1 = x+dx
                    y1 = y+dy
                    if x1 < 0 or x1 >= width or y1 < 0 or y1 >= height:
                        return 0.
                    else:
                        return data[x1][y1]
                        
                if raster[x][y]:
                    s = 0
                    w = 0
                    
                    for i in range(k):
                        d = min(distanceToEdge(x,y,i) / deltaLengths[i], 1.)
                        weight = 1./ d
                        w += weight
                        s += (z(deltas[i].x, deltas[i].y)**invExponent+d)**exponent * weight
                            
                    newData[x][y] = (1-alpha) * s / w

        data = newData
        
    data = [[point**invExponent for point in col] for col in data]
    maxZ = max(max(col) for col in data)
    
    return [ [datum / maxZ * inflationParams.thickness for datum in col] for col in data ]


if __name__ == '__main__':
    from PIL import Image

    inPath = sys.argv[1]
    outPath = os.path.splitext(inPath)[0] + ".scad"
    baseName = os.path.splitext(os.path.basename(outPath))[0]
    
    thickness = 10.
    flatness = 0.
    iterations = None
    if len(sys.argv)>2:
        thickness = float(sys.argv[2])
    if len(sys.argv)>3:
        flatness = float(sys.argv[3])
    if len(sys.argv)>4:
        iterations = int(sys.argv[4])

    image = Image.open(inPath).convert('RGBA')
    
    def inside(x,y):
        rgb = image.getpixel((x,image.size[1]-1-y))
        if len(rgb) > 3 and rgb[3] == 0:
            return False
        return rgb[0:3] != (255,255,255)

    raster = [ [ inside(x,y) for y in range(image.size[1]) ] for x in range(image.size[0]) ]
    
    print("Inflating...")
    data = inflateRaster(raster,thickness=thickness,flatness=flatness,iterations=iterations)
    
    scadModule = toSCADModule(surfaceToMesh(data, twoSided=False, center=True), baseName+"_raw")
    scadModule += """

module %s() {
     render(convexity=2)
     translate([0,0,-%f])
     intersection() {
        %s_raw();
        translate([-%d/2,-%d/2,%f]) cube([%d,%d,%f]);
     }
}

%s();
""" % (baseName, thickness / 20., baseName, image.size[0], image.size[1], thickness / 20., image.size[0]+2, image.size[1]+2, thickness+1., baseName)
    
    print("Saving "+outPath)
    with open(outPath, "w") as f: f.write(scadModule)
    