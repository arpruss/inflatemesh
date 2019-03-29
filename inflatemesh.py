from __future__ import division
from inflateutils.surface import *
import inflateutils.svgpath.shader as shader
import inflateutils.svgpath.parser as parser
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
    
    for x,y in meshData.getPoints(useMask=False):
        z = meshData.getCoordinates(x,y).toComplex() * rotate
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
            meshData.mask[x][y] = True

    return meshData
    
def message(string):
    if not quiet:
        sys.stderr.write(string + "\n")
    
def inflatePolygon(polygon, gridSize=15, shadeMode=shader.Shader.MODE_EVEN_ODD, inflationParams=None,
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
    deltasComplex = tuple( v.toComplex() for v in meshData.normalizedDeltas )
    map = tuple(tuple([1. for i in range(len(deltasComplex))] for row in range(meshData.rows)) for col in range(meshData.cols))
    
    for x,y in meshData.getPoints():
        v = meshData.getCoordinates(x,y)

        for i in range(len(deltasComplex)):
            map[x][y][i] = distanceToEdge( v.toComplex(), deltasComplex[i] )
            
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

def inflateLinearPath(path, gridSize=15, inflationParams=None, ignoreColor=False, offset=0j):
    lines = []
    for line in path:
        lines.append((line.start+offset,line.end+offset))
    mode = shader.Shader.MODE_NONZERO if path.svgState.fillRule == 'nonzero' else shader.Shader.MODE_EVEN_ODD
    return inflatePolygon(lines, gridSize=gridSize, inflationParams=inflationParams, twoSided=twoSided, 
                color=None if ignoreColor else path.svgState.fill, shadeMode=mode) 

class InflatedData(object):
    pass
                
def inflatePaths(paths, gridSize=15, inflationParams=None, twoSided=False, ignoreColor=False, baseName="path", offset=0j, colors=True):
    data = InflatedData()
    data.meshes = []

    paths = sortedApproximatePaths( paths, error=0.1 )
    
    for i,path in enumerate(paths):
        inflateThis = path.svgState.fill is not None
        if inflateThis:
            mesh = inflateLinearPath(path, gridSize=gridSize, inflationParams=inflationParams, ignoreColor=not colors, offset=offset)
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
    
def getColorFromMesh(mesh):
    return mesh[0][0]
    
if __name__ == '__main__':
    import cmath
    
    params = InflationParams()
    output = "stl"
    twoSided = False
    outfile = None
    gridSize = 15
    baseName = "svg"
    colors = True
    centerPage = False
    
    def help(exitCode=0):
        help = """python inflatemesh.py [options] filename.svg
options:
--help:         this message        
--stl:          output to STL (default: OpenSCAD)
--rectangular:  use mesh over rectangular grid (default: hexagonal)
--flatness=x:   make the top flatter; reasonable range: 0.0-10.0 (default: 0.0)
--height=x:     make the inflated stuff have height (or thickness) x millimeters (default: 10)
--exponent=x:   controls how rounded the inflated image is; must be bigger than 0.0 (default: 0.0)
--resolution=n: approximate mesh resolution along the larger dimension (default: 15)
--iterations=n: number of iterations in calculation (default depends on resolution)
--two-sided:    inflate both up and down
--no-colors:    omit colors from SVG file (default: include colors)
--center-page:  put the center of the SVG page at (0,0,0) in the OpenSCAD file
--name=abc:     make all the OpenSCAD variables/module names contain abc (e.g., center_abc) (default: svg)
--output=file:  write output to file (default: stdout)
"""
        if exitCode:
            sys.stderr.write(help + "\n")
        else:
            print(help)
        sys.exit(exitCode)

    try:
        opts, args = getopt.getopt(sys.argv[1:], "h", 
                        ["tab=", "help", "stl", "rectangular", "mesh=", "flatness=", "name=", "height=", 
                        "exponent=", "resolution=", "format=", "iterations=", "width=", "xtwo-sided=", "two-sided", 
                        "output=", "center-page", "xcenter-page=", "no-colors", "xcolors=", "noise=", "noise-exponent="])

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
            elif opt == '--height':
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
            elif opt == "--noise":
                params.noise = float(arg)
            elif opt == "--noise-exponent":
                params.noiseExponent = float(arg)
            elif opt == "--center-page":
                centerPage = True
            elif opt == "--xcenter-page":
                centerPage = (arg == "true" or arg == "1")
            elif opt == "--xcolors":
                colors = (arg == "true" or arg == "1")
            elif opt == "--no-colors":
                colors = False
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
        offset = 0j
        
    data = inflatePaths(paths, inflationParams=params, gridSize=gridSize, twoSided=twoSided, baseName=baseName, offset=offset, colors=colors)
    
    if format == 'stl':
        mesh = [datum for name,mesh in data.meshes for datum in mesh]
        saveSTL(outfile, mesh, quiet=quiet)
    else:
        scad = ""
        for i,(name,mesh) in enumerate(data.meshes):
            mesh,centerX,centerY,width,height = recenterMesh(mesh)
            data.meshes[i] = (name,mesh)
            scad += "center_%s = [%.5f,%.5f];\n" % (name,centerX,centerY)
            scad += "size_%s = [%.5f,%.5f];\n" % (name,width,height)
            scad += "color_%s = [%.5f,%.5f,%.5f];\n\n" % ((name,)+getColorFromMesh(mesh))
            
        for name,mesh in data.meshes:
            scad += toSCADModule(mesh, moduleName=name, coordinateFormat="%.5f", colorOverride="color_%s" % (name,))
            scad += "\n"
        
        for name,_ in data.meshes:
            scad += "translate(center_%s) %s();\n" % (name,name)
            
        if outfile:
            with open(outfile, "w") as f: f.write(scad)
        else:
            print(scad)    
