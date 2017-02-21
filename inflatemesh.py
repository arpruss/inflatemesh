from __future__ import division
from inflateutils.surface import *
import svgpath.shader as shader
import svgpath.parser as parser
import sys
import getopt
from inflateutils.exportmesh import *

quiet = False

def rasterizePolygon(polygon, spacing, shadeMode=shader.Shader.MODE_EVEN_ODD):
    """
    Returns boolean raster of strict interior as well as coordinates of lower-left corner.
    """
    spacing = float(spacing)
    lines = shader.Shader.shadePolygon(polygon, 0, spacing, avoidOutline=True, mode=shadeMode, alternate=False)
    height = len(lines)
    bottom = min(z[0].imag for z in lines)
    left = min(z[0].real for z in lines) - 0.5 * spacing
    right = max(z[1].real for z in lines)
    width = int((right-left) / spacing+1)

    raster = [[False for y in range(height)] for x in range(width)]

    for line in lines:
        y = int((line[0].imag - bottom) / spacing + 0.5)
        x = int((line[0].real - left) / spacing)
        while left + x * spacing < line[1].real:
            if line[0].real < left + x * spacing:
                raster[x][y] = True
            x += 1
    
    return raster,complex(left,bottom)
    
def message(string):
    if not quiet:
        sys.stderr.write(string + "\n")
    
def inflatePolygon(polygon, spacing=1., shadeMode=shader.Shader.MODE_EVEN_ODD, thickness=10., flatness=0., 
        iterations=None, center=False, twoSided=False, color=None, trim=True, fastDistanceMap=False):
    # polygon is described by list of (start,stop) pairs, where start and stop are complex numbers
    message("Rasterizing")
    raster,bottomLeft = rasterizePolygon(polygon, spacing, shadeMode=shadeMode)
    rasterWidth = len(raster)
    rasterHeight = len(raster[0])
    bottomLeftV = Vector(bottomLeft)
    
    def distanceToEdge(z0, direction):
        direction = direction / abs(direction)
        rotate = 1. / direction
        
        class State(object): pass
        state = State()
        state.changed = False
        state.bestLength = float("inf")
        
        for line in polygon:
            def update(x):
                if 0 <= x < state.bestLength:
                    state.changed = True
                    state.bestLength = x
        
            l0 = rotate * (line[0]-z0)
            l1 = rotate * (line[1]-z0)
            if l0.imag == l1.imag and l0.imag == 0.:
                if l0.real <= 0 and l1.real >= 0:
                    return start
                update(l0.real)
                update(l1.real)
            elif l0.imag <= 0 <= l1.imag or l1.imag <= 0 <= l0.imag:
                # crosses real line
                mInv = (l1.real-l0.real)/(l1.imag-l0.imag)
                # (x - l0.real) / mInv = y - l0.imag
                # so for y = 0: 
                x = -l0.imag * mInv + l0.real
                update(x)
        return state.bestLength

    def inside(v):
        if v[0] < 0 or v[0] >= rasterWidth or v[1] < 0 or v[1] >= rasterHeight:
            return False
        return raster[v[0]][v[1]]
        
    message("Making edge distance map")
    deltas = (Vector(-1,0), Vector(1,0), Vector(0,-1), Vector(0,1)) # , Vector(-1,-1), Vector(1,1), Vector(-1,1), Vector(1,-1))
    deltasComplex = tuple( v.toComplex() for v in deltas )
    deltaLengths = tuple( abs(d) for d in deltasComplex )
    map = [[[1. for i in range(len(deltas))] for row in range(rasterHeight)] for col in range(rasterWidth)]
    for col in range(rasterWidth):
        for row in range(rasterHeight):
            v = spacing * Vector(col,row) + bottomLeftV
            for i in range(len(deltasComplex)):
                if not fastDistanceMap or inside(deltas[i]+(col,row)):
                    map[col][row][i] = distanceToEdge( v.toComplex(), deltasComplex[i] ) / spacing
                else:
                    map[col][row][i] = deltaLengths[i] / spacing
            
    message("Inflating")
    
    def distanceFunction(col, row, i, map=map):
        return map[col][row][i]
    
    surface = inflateRaster(raster, thickness=thickness, flatness=flatness, iterations=iterations, 
                    deltas=deltas, distanceToEdge=distanceFunction)
    message("Meshing")
    mesh0 = surfaceToMesh(surface, center=False, twoSided=twoSided, color=color)
    
    def fixFace(face, polygon, trim=True):
        def scaleFace(face):
            return tuple(Vector(v.x*spacing+bottomLeftV.x, v.y*spacing+bottomLeftV.y, v.z) for v in face)

        if not trim:
            return [scaleFace(face)]

        # TODO: optimize by using cached data from the distance map
        def trimLine(start, stop):
            delta = (stop - start).toComplex() # projects to 2D
            if delta == 0j:
                return stop
            length = abs(delta)
            z0 = start.toComplex()
            distance = distanceToEdge(z0, delta)
            if distance < length:
                z = z0 + distance * delta / length
                return Vector(z.real, z.imag, 0)
    
        outsideCount = sum(1 for v in face if not inside(v))
        if outsideCount == 3:
            return []
        elif outsideCount == 0:
            return [scaleFace(face)]
        elif outsideCount == 2:
            if inside(face[1]):
                face = (face[1], face[2], face[0])
            elif inside(face[2]):
                face = (face[2], face[0], face[1])
            # now, the first vertex is inside and the others are outside
            face = scaleFace(face)
            return [ (face[0], trimLine(face[0], face[1]), trimLine(face[0], face[2])) ]
        else: # outsideCount == 1
            if not inside(face[0]):
                face = (face[1], face[2], face[0])
            elif not inside(face[1]):
                face = (face[2], face[0], face[1])
            # now, the first two vertices are inside, and the third is outside
            face = scaleFace(face)
            closest0 = trimLine(face[0], face[2])
            closest1 = trimLine(face[1], face[2])
            if closest0 != closest1:
                return [ (face[0], face[1], closest0), (closest0, face[1], closest1) ]
            else:
                return [ (face[0], face[1], closest0) ]

    message("Fixing outer faces")
    mesh = []
    for rgb,face in mesh0:
        for face2 in fixFace(face, polygon, trim=trim):
            mesh.append((rgb, face2))
    return mesh
    
def sortedApproximatePaths(paths,error=0.1):
    paths = [path.linearApproximation(error=error) for path in paths if len(path)]
    
    def key(path):
        top = min(min(line.start.imag,line.end.imag) for line in path)
        left = min(min(line.start.real,line.end.real) for line in path)
        return (top,left)
        
    return sorted(paths, key=key)

def inflateLinearPath(path, spacing=1., thickness=10., flatness=0., iterations=None, ignoreColor=False):
    lines = []
    for line in path:
        lines.append((line.start,line.end))
    mode = shader.Shader.MODE_NONZERO if path.svgState.fillRule == 'nonzero' else shader.Shader.MODE_EVEN_ODD
    return inflatePolygon(lines, spacing=spacing, thickness=thickness, flatness=flatness, 
                iterations=iterations, twoSided=twoSided, color=None if ignoreColor else path.svgState.fill, shadeMode=mode, trim=trim) 

class InflatedData(object):
    pass
                
def inflateSVGFile(svgFile, spacing=1., thickness=10., flatness=0., iterations=None, twoSided=False, trim=True, ignoreColor=False, inflate=True, baseName="path"):
    data = InflatedData()
    data.meshes = []
    data.pointLists = []
    data.uninflatedPointLists = []

    paths = sortedApproximatePaths( parser.getPathsFromSVGFile(svgFile)[0], error=spacing*0.1 )
    
    for i,path in enumerate(paths):
        inflateThis = inflate and path.svgState.fill is not None
        if inflateThis:
            mesh = inflateLinearPath(path, spacing=spacing, thickness=thickness, flatness=flatness, iterations=iterations, ignoreColor=ignoreColor)
            data.meshes.append( ("inflated_" + baseName + "_" + str(i), mesh) )
        for j,subpath in enumerate(path.breakup()):
            points = [subpath[0].start]
            for line in subpath:
                points.append(line.end)
            if subpath.closed and points[0] != points[-1]:
                points.append(points[0])
            data.pointLists.append(( "points_" + baseName + "_" + str(i) + "_" + str(j), points) )
            if not inflateThis:
                data.uninflatedPointLists.append(data.pointsLists[-1])

    return data
    
if __name__ == '__main__':
    import cmath
    
    flatness = 0.
    thickness = 10.
    spacing = 1.
    output = "stl"
    iterations = None
    width = 0.5 # TODO
    twoSided = False
    trim = True
    outfile = None
    inflate = True
    baseName = "path"
    
    def help(exitCode=0):
        help = """python inflate.py [options] filename.svg"""
        if exitCode:
            sys.stderr.write(help + "\n")
        else:
            print(help)
        sys.exit(exitCode)
    
    try:
        opts, args = getopt.getopt(sys.argv[1:], "h", 
                        ["tab=", "help", "stl", "flatness=", "name=", "thickness=", "resolution=", "format=", "iterations=", "width=", "xtwo-sided=", "two-sided", "output=", "trim=", "no-inflate", "xinflate="])
        # TODO: support width for ribbon-thin stuff

        if len(args) == 0:
            raise getopt.GetoptError("invalid commandline")

        i = 0
        while i < len(opts):
            opt,arg = opts[i]
            if opt in ('-h', '--help'):
                help()
                sys.exit(0)
            elif opt == '--flatness':
                flatness = float(arg)
            elif opt == '--thickness':
                thickness = float(arg)
            elif opt == '--resolution':
                spacing = float(arg)
            elif opt == '--format' or opt == "--tab":
                if opt == "--tab":
                    quiet = True
                format = arg.replace('"','').replace("'","")
            elif opt == "--stl":
                format = "stl"
            elif opt == '--iterations':
                iterations = int(arg)
            elif opt == '--width':
                width = float(arg)
            elif opt == '--xtwo-sided':
                twoSided = (arg == "true" or arg == "1")
            elif opt == '--xinflate':
                inflate = bool(int(arg))
            elif opt == '--no-inflate':
                inflate = False
            elif opt == '--two-sided':
                twoSided = True
            elif opt == "--name":
                baseName = arg
            elif opt == "--trim":
                trim = bool(int(arg))
            elif opt == "--output":
                outfile = arg
                
            i += 1
                
    except getopt.GetoptError as e:
        sys.stderr.write(str(e)+"\n")
        help(exitCode=1)
        sys.exit(2)
        
    if twoSided:
        thickness *= 0.5
        
    data = inflateSVGFile(args[0], thickness=thickness, flatness=flatness, iterations=iterations, spacing=spacing, 
        twoSided=twoSided, trim=trim, inflate=inflate, baseName=baseName)
    
    if format == 'stl':
        mesh = [datum for name,mesh in data.meshes for datum in mesh]
        saveSTL(outfile, mesh)
    else:
        scad = "polygonHeight = 1;\n\n"
        
        for name,points in data.pointLists:
            scad += name + " = [ " + ','.join('[%.9f,%.9f]' % (point.real,point.imag) for point in points) + " ];\n"
            
        scad += "\n";
        
        for name,mesh in data.meshes:
            scad += toSCADModule(mesh, moduleName=name)
            scad += "\n"
        
        for name,_ in data.meshes:
            scad += name + "();\n"
            
        if data.uninflatedPointLists:
            scad += "module polygon_%s() {\n" % baseName
            scad += "  linear_extrude(height=polygonHeight) {\n";
            for name,points in data.uninflatedPointLists:
                if points[0] == points[-1]:
                    scad += "  polygon(points="+name+");\n";
                else:
                    "// "+name+" is not closed\n"
            scad += "  }\n"
            scad += "}\n"
            
            scad += "polygon_%s();\n" % baseName
            
        if outfile:
            with open(outfile, "w") as f: f.write(scad)
        else:
            print(scad)    
