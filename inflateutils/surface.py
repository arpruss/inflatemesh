from __future__ import division
from vector import *
from exportmesh import *
import itertools
import os.path
import math

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

def inflateRaster(raster, thickness=10., flatness=1., iterations=None, 
        deltas=(Vector(-1,0),Vector(1,0),Vector(0,1),Vector(0,-1),Vector(-1,-1),Vector(1,1),Vector(-1,1),Vector(1,-1)), 
        distanceToEdge=lambda (row,col,i): 1. if i<4 else 1.414, eps=0.000001 ):
    """
    raster is a boolean matrix.
    
    flatness varies from 0 for a very gradual profile to something around 2-10 for a very flat top.
    
    Here's a way to visualize how inflateImage() works. The white or transparent areas 
    of the image are cold, clamped at temperature 0. Above the image, there is a layer of
    insulation, and above that there is a flat heater at a fixed positive temperature. So, 
    the clamped areas stay at the fixed temperature, but away from the clamped areas, the image
    heats up. How the heat profile looks depends on how effective the layer of insulation is.
    The effectiveness of the layer of insulation is measured by the flatness parameter.
    When this parameter is high, the unclamped areas all get to close to the heater
    temperature, resulting in a very sharp heat gradient near the image boundaries, and flatness
    further away from the boundaries. When the parameter is close to 0, the insulation is more
    effective, and the temperature rise away from the boundaries is more gradual. The result is
    a smoother change in the gradient.
    
    Finally, the temperatures are scaled to be between 0 and thickness to generate the inflated
    height map. 
    """
    
    deltaLengths = tuple(delta.norm() for delta in deltas)
    
    width = len(raster)
    height = len(raster[0])
        
    alpha = 500 * len(deltaLengths) * flatness /  max(width,height)**2
    
    if not iterations:
        iterations = 25 * max(width,height) # 60 ?
        
    data = [ [0. for y in range(height)] for x in range(width) ]
    
    def weight(x,y,i):
        d = distanceToEdge(x,y,i)
        if d < deltaLengths[i]:
            return 1. / d
        else:
            return 1. / deltaLengths[i]
    
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
                    w = alpha
                    
                    for i in range(len(deltas)):
                        d = distanceToEdge(x,y,i)
                        if d >= (1-eps) * deltaLengths[i]:
                            s += z(deltas[i].x, deltas[i].y) / deltaLengths[i]
                            w += 1. / deltaLengths[i]
                        else:
                            w += 1. / max(d, eps)
                            
                    newData[x][y] = (alpha / w if alpha > 0.0 else 1.0) + s / w

        data = newData
        
    maxZ = max(max(col) for col in data)
    
    return [ [datum / maxZ * thickness for datum in col] for col in data ]


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
    