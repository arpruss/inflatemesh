from __future__ import division
from inflateutils.surface import *
import svgpath.shader as shader
import svgpath.parser as parser
import sys
import getopt
from inflateutils.exportmesh import *

quiet = False

def getBounds(lines):
    bottom = min(min(l[0].imag,l[1].imag) for l in lines)
    left = min(min(l[0].real,l[1].real) for l in lines)
    top = max(max(l[0].imag,l[1].imag) for l in lines)
    right = max(max(l[0].real,l[1].real) for l in lines)
    return left,bottom,right,top

def rasterizePolygon(polygon, gridSize, shadeMode=shader.Shader.MODE_EVEN_ODD, hex=False):
    """
    Returns boolean raster of strict interior as well as coordinates of lower-left corner.
    """
    left,bottom,right,top = getBounds(polygon)
    
    width = right-left
    height = top-bottom
    
    spacing = max(width,height) / gridSize

    if hex:
        meshData = HexMeshData(right-left,top-bottom,Vector(left,bottom),spacing)
    else:
        meshData = RectMeshData(right-left,top-bottom,Vector(left,bottom),spacing)
        
    # TODO: not really optimal but simple -- the wraparound is the inoptimality
    
    phases = [0] + list(sorted( cmath.phase(l[1]-l[0]) % math.pi for l in polygon if l[1] != l[0] ) ) + [math.pi]
    bestSpacing = 0
    bestPhase = 0.
    for i in range(1,len(phases)):
        if phases[i]-phases[i-1] > bestSpacing:
            bestPhase = 0.5 * (phases[i] + phases[i-1])
            bestSpacing = phases[i]-phases[i-1]
            
    rotate = cmath.exp(-1j * bestPhase)
    
    lines = tuple((l[0] * rotate, l[1] * rotate) for l in polygon)
    
    for col in range(meshData.cols):
        for row in range(meshData.rows):
            z = meshData.getCoordinates(col,row).toComplex() * rotate
            sum = 0
            for l in lines:
                a = l[0] - z
                b = l[1] - z
                if a.imag <= 0 <= b.imag or b.imag <= 0 <= a.imag:
                    mInv = (b.real-a.real)/(b.imag-a.imag)
                    if -a.imag * mInv + a.real >= 0:
                        if shadeMode == shader.Shader.MODE_EVEN_ODD:
                            sum += 1
                        else:
                            if a.imag < b.imag:
                                sum += 1
                            else:
                                sum -= 1
            if (shadeMode == shader.Shader.MODE_EVEN_ODD and sum % 2) or (shadeMode != shader.Shader.MODE_EVEN_ODD and sum != 0):
                meshData.mask[col][row] = True

    return meshData
    
def message(string):
    if not quiet:
        sys.stderr.write(string + "\n")
    
def inflatePolygon(polygon, gridSize=30, shadeMode=shader.Shader.MODE_EVEN_ODD, inflationParams=None,
        center=False, twoSided=False, color=None):
    # polygon is described by list of (start,stop) pairs, where start and stop are complex numbers
    message("Rasterizing")
    meshData = rasterizePolygon(polygon, gridSize, shadeMode=shadeMode, hex=inflationParams.hex)
    
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
                if (l0.real <= 0 and l1.real >= 0) or (l1.real <= 0 and l0.real >= 0):
                    return 0.
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

    message("Making edge distance map")
    deltas = meshData.normalizedDeltas
    deltasComplex = tuple( v.toComplex() for v in deltas )
    map = [[[1. for i in range(len(deltas))] for row in range(meshData.rows)] for col in range(meshData.cols)]
    
    for col in range(meshData.cols):
        for row in range(meshData.rows):
            v = meshData.getCoordinates(col,row)

            for i in range(len(deltasComplex)):
                map[col][row][i] = distanceToEdge( v.toComplex(), deltasComplex[i] )
            
    message("Inflating")
    
    def distanceFunction(col, row, i, map=map):
        return map[col][row][i]
    
    inflateRaster(meshData, inflationParams=inflationParams, distanceToEdge=distanceFunction)
    message("Meshing")
   
    mesh0 = meshData.getMesh(twoSided=twoSided, color=color)
    
    def fixFace(face, polygon):
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
            else:
                return stop
    
        outsideCount = sum(1 for v in face if not meshData.insideCoordinates(v))
        if outsideCount == 3:
            # should not ever happen
            return []
        elif outsideCount == 0:
            return [face]
        elif outsideCount == 2:
            if meshData.insideCoordinates(face[1]):
                face = (face[1], face[2], face[0])
            elif meshData.insideCoordinates(face[2]):
                face = (face[2], face[0], face[1])
            # now, the first vertex is inside and the others are outside
            return [ (face[0], trimLine(face[0], face[1]), trimLine(face[0], face[2])) ]
        else: # outsideCount == 1
            if not meshData.insideCoordinates(face[0]):
                face = (face[1], face[2], face[0])
            elif not meshData.insideCoordinates(face[1]):
                face = (face[2], face[0], face[1])
            # now, the first two vertices are inside, and the third is outside
            closest0 = trimLine(face[0], face[2])
            closest1 = trimLine(face[1], face[2])
            if closest0 != closest1:
                return [ (face[0], face[1], closest0), (closest0, face[1], closest1) ]
            else:
                return [ (face[0], face[1], closest0) ]

    message("Fixing outer faces")
    mesh = []
    for rgb,face in mesh0:
        for face2 in fixFace(face, polygon):
            mesh.append((rgb, face2))
            
    return mesh
    
def sortedApproximatePaths(paths,error=0.1):
    paths = [path.linearApproximation(error=error) for path in paths if len(path)]
    
    def key(path):
        top = min(min(line.start.imag,line.end.imag) for line in path)
        left = min(min(line.start.real,line.end.real) for line in path)
        return (top,left)
        
    return sorted(paths, key=key)

def inflateLinearPath(path, gridSize=30, inflationParams=None, ignoreColor=False, offset=0j):
    lines = []
    for line in path:
        lines.append((line.start+offset,line.end+offset))
    mode = shader.Shader.MODE_NONZERO if path.svgState.fillRule == 'nonzero' else shader.Shader.MODE_EVEN_ODD
    return inflatePolygon(lines, gridSize=gridSize, inflationParams=inflationParams, twoSided=twoSided, 
                color=None if ignoreColor else path.svgState.fill, shadeMode=mode) 

class InflatedData(object):
    pass
                
def inflatePaths(paths, gridSize=30, inflationParams=None, twoSided=False, ignoreColor=False, inflate=True, baseName="path", offset=0j):
    data = InflatedData()
    data.meshes = []

    paths = sortedApproximatePaths( paths, error=0.1 )
    
    for i,path in enumerate(paths):
        inflateThis = inflate and path.svgState.fill is not None
        if inflateThis:
            mesh = inflateLinearPath(path, gridSize=gridSize, inflationParams=inflationParams, ignoreColor=ignoreColor, offset=offset)
            name = "inflated_" + baseName
            if len(paths)>1:
                name += "_" + str(i+1)
            data.meshes.append( (name, mesh) )

    return data
    
def recenterMesh(mesh):
    leftX = float("inf")
    rightX = float("-inf")
    topX = float("-inf")
    bottomX = float("inf")
    
    for rgb,triangle in mesh:
        for vertex in triangle:
            leftX = min(leftX, vertex[0])
            rightX = max(rightX, vertex[0])
            bottomX = min(bottomX, vertex[1])
            topX = max(topX, vertex[1])

    newMesh = []
    
    center = Vector(0.5*(leftX+rightX),0.5*(bottomX+topX),0.)
    
    for rgb,triangle in mesh:
        newMesh.append((rgb, tuple(v-center for v in triangle)))
        
    return newMesh, center.x, center.y, rightX-leftX, topX-bottomX
    
if __name__ == '__main__':
    import cmath
    
    params = InflationParams()
    output = "stl"
    twoSided = False
    outfile = None
    gridSize = 30
    baseName = "svg"
    centerPage = False
    
    def help(exitCode=0):
        help = """python inflate.py [options] filename.svg"""
        if exitCode:
            sys.stderr.write(help + "\n")
        else:
            print(help)
        sys.exit(exitCode)
    
    try:
        opts, args = getopt.getopt(sys.argv[1:], "h", 
                        ["tab=", "help", "stl", "rectangular", "mesh=", "flatness=", "name=", "thickness=", 
                        "exponent=", "resolution=", "format=", "iterations=", "width=", "xtwo-sided=", "two-sided", 
                        "output=", "center-page", "xcenter-page="])
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
                params.flatness = float(arg)
            elif opt == '--thickness':
                params.thickness = float(arg)
            elif opt == '--resolution':
                gridSize = int(arg)
            elif opt == '--rectangular':
                params.hex = False
            elif opt == '--mesh':
                params.hex = arg.lower()[0] == 'h'
            elif opt == '--format' or opt == "--tab":
                if opt == "--tab":
                    quiet = True
                format = arg.replace('"','').replace("'","")
            elif opt == "--stl":
                format = "stl"
            elif opt == '--iterations':
                params.iterations = int(arg)
            elif opt == '--width':
                width = float(arg)
            elif opt == '--xtwo-sided':
                twoSided = (arg == "true" or arg == "1")
            elif opt == '--two-sided':
                twoSided = True
            elif opt == "--name":
                baseName = arg
            elif opt == "--exponent":
                params.exponent = float(arg)
            elif opt == "--output":
                outfile = arg
            elif opt == "--center-page":
                centerPage = True
            elif opt == "--xcenter-page":
                centerPage = (arg == "true" or arg == "1")
            i += 1
                
    except getopt.GetoptError as e:
        sys.stderr.write(str(e)+"\n")
        help(exitCode=1)
        sys.exit(2)
        
    if twoSided:
        params.thickness *= 0.5
        
    paths, lowerLeft, upperRight = parser.getPathsFromSVGFile(args[0])
    
    if centerPage:
        offset = -0.5*(lowerLeft+upperRight)
    else:
        offset = 0
        
    data = inflatePaths(paths, inflationParams=params, gridSize=gridSize, twoSided=twoSided, baseName=baseName, offset=offset)
    
    if format == 'stl':
        mesh = [datum for name,mesh in data.meshes for datum in mesh]
        saveSTL(outfile, mesh, quiet=quiet)
    else:
        scad = ""
        for name,mesh in data.meshes:
            mesh,centerX,centerY,width,height = recenterMesh(mesh)
            scad += name + "_center = [%.5f,%.5f];\n" % (centerX,centerY)
            scad += name + "_size = [%.5f,%.5f];\n\n" % (width,height)
            scad += toSCADModule(mesh, moduleName=name, coordinateFormat="%.5f")
            scad += "\n"
        
        for name,_ in data.meshes:
            scad += "translate(%s_center) %s();\n" % (name,name)
            
        if outfile:
            with open(outfile, "w") as f: f.write(scad)
        else:
            print(scad)    
