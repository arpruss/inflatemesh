from __future__ import division
import inflateutils.svgpath.shader as shader
import inflateutils.svgpath.parser as parser
import sys
import getopt
import cmath
from inflateutils.exportmesh import *
from random import sample

quiet = False

def closed(path):
    return path[-1] == path[0]
    
def inside(z, path):
    for p in path:
        if p == z:
            return False
    try:
        phases = sorted((cmath.phase(p-z) for p in path))
        # make a ray that is relatively far away from any points
        if len(phases) == 1:
            # should not happen
            bestPhase = phases[0] + math.pi
        else:    
            bestIndex = max( (phases[i+1]-phases[i],i) for i in range(len(phases)-1))[1]
            bestPhase = (phases[bestIndex+1]+phases[bestIndex])/2.
        ray = cmath.rect(1., bestPhase)
        rotatedPath = tuple((p-z) / ray for p in path)
        # now we just need to check shiftedPath's intersection with the positive real line
        s = 0
        for i,p2 in enumerate(rotatedPath):
            p1 = rotatedPath[i-1]
            if p1.imag == p2.imag:
                # horizontal lines can't intersect positive real line once phase selection was done
                continue
                # (1/m)y + xIntercept = x
            reciprocalSlope = (p2.real-p1.real)/(p2.imag-p1.imag)
            xIntercept = p2.real - reciprocalSlope * p2.imag
            if xIntercept == 0:
                return False # on boundary
            if xIntercept > 0 and p1.imag * p2.imag < 0:
                if p1.imag < 0:
                    s += 1
                else:
                    s -= 1
        return s != 0
            
    except OverflowError:
        return False
    
def nestedPaths(path1, path2, pointsToCheck=3):
    if not closed(path2):
        return False
    k = min(pointsToCheck, len(path1))
    for point in sample(path1, k):
        if inside(point, path2):
            return True
    return False
    
def comparePaths(path1,path2,pointsToCheck=3):
    """
    open paths before closed paths
    outer paths come before inner ones
    otherwise, top to bottom bounds, left to right
    """
    
    if closed(path1) and not closed(path2):
        return 1
    elif closed(path2) and not closed(path1):
        return -1
    if nestedPaths(path1, path2, pointsToCheck=pointsToCheck):
        return 1
    elif nestedPaths(path2, path1, pointsToCheck=pointsToCheck):
        return -1
    y1 = max(p.imag for p in path1)
    y2 = max(p.imag for p in path2)
    if y1 == y2:
        return comparison(min(p.real for p in path1),min(p.real for p in path2))
    else:
        return comparison(y1,y2)

def getLevels(paths):
    level = []
    empty = True
    for i,path in enumerate(paths):
        if path is None:
            continue
        empty = False
        outer = True
        if closed(path):
            for j in range(len(paths)):
                if j != i and paths[j] is not None and nestedPaths(path, paths[j]):
                    outer = False
                    break
        if outer:
            level.append(path)
            paths[i] = None

    if empty:
        return []
    else:
        return [level] + getLevels(paths)
        
def message(string):
    if not quiet:
        sys.stderr.write(string + "\n")
    
def sortedApproximatePaths(paths,error=0.1):
    paths = [path.linearApproximation(error=error) for path in paths if len(path)]
    
    def key(path):
        top = min(min(line.start.imag,line.end.imag) for line in path)
        left = min(min(line.start.real,line.end.real) for line in path)
        return (top,left)
        
    return sorted(paths, key=key)

class PolygonData(object):
    def __init__(self,color):
        self.bounds = [float("inf"),float("inf"),float("-inf"),float("-inf")]
        self.color = color
        self.pointLists = []
        
    def updateBounds(self,z):
        self.bounds[0] = min(self.bounds[0], z.real)
        self.bounds[1] = min(self.bounds[1], z.imag)
        self.bounds[2] = max(self.bounds[2], z.real)
        self.bounds[3] = max(self.bounds[3], z.imag)

    def getCenter(self):
        return complex(0.5*(self.bounds[0]+self.bounds[2]),0.5*(self.bounds[1]+self.bounds[3]))

    
def extractPaths(paths, offset, tolerance=0.1, baseName="svg", colors=True, colorFromFill=False, levels=False):
    polygons = []

    paths = sortedApproximatePaths(paths, error=tolerance )
    
    for i,path in enumerate(paths):
        color = None
        if colors:
            if colorFromFill:
                if path.svgState.fill is not None:
                    color = path.svgState.fill
                else:
                    color = path.svgState.stroke
            else:
                if path.svgState.stroke is not None:
                    color = path.svgState.stroke
                else:
                    color = path.svgState.fill
        polygon = PolygonData(color)
        polygon.strokeWidth = path.svgState.strokeWidth;
        polygons.append(polygon)
        for j,subpath in enumerate(path.breakup()):
            points = [subpath[0].start+offset]
            polygon.updateBounds(points[-1])
            for line in subpath:
                points.append(line.end+offset)
                polygon.updateBounds(points[-1])
            if subpath.closed and points[0] != points[-1]:
                points.append(points[0])
            polygon.pointLists.append(points)
        for points in polygon.pointLists:
            for j in range(len(points)):
                points[j] -= polygon.getCenter()
                
        if levels:
            polygon.levels = getLevels(polygon.pointLists)
            polygon.pointLists = flattenLevels(polygon.levels)

    return polygons
    
def toNestedPolygons(levels, name, i=0, indent=4):
    def spaces():
        return ' '*indent
    out = ""
    if len(levels)>1:
        out += spaces() + "difference() {\n"
        indent += 2
    if len(levels[0])>1:
        out += spaces() + "union() {\n"
        indent += 2
    for poly in levels[0]:
        if closed(poly):
            out += spaces() + "polygon(points=%s);\n" % name(i)
        i += 1
    if len(levels[0])>1:
        indent -= 2
        out += spaces() + "}\n"
    if len(levels)>1:
        out += toNestedPolygons(levels[1:], name, i=i, indent=indent)
        indent -= 2
        out += spaces() + "}\n"
    return out
    
def flattenLevels(levels):
    out = []
    for level in levels:
        out += level
    return out
    
if __name__ == '__main__':
    outfile = None
    mode = "points"
    baseName = "svg"
    tolerance = 0.1
    width = 0
    height = 10
    colors = True
    centerPage = False
    
    def help(exitCode=0):
        help = """python svg2scad.py [options] filename.svg
options:
--help:         this message        
--tolerance=x:  when linearizing paths, keep them within x millimeters of correct position (default: 0.1)
--ribbon:       make ribbons out of paths
--polygons:     make polygons out of paths (requires manual adjustment of holes)
--width:        ribbon width override
--height:       ribbon or polygon height in millimeters; if zero, they're two-dimensional (default: 10)
--no-colors:    omit colors from SVG file (default: include colors)
--name=abc:     make all the OpenSCAD variables/module names contain abc (e.g., center_abc) (default: svg)
--center-page:  put the center of the SVG page at (0,0,0) in the OpenSCAD file
--output=file:  write output to file (default: stdout)
"""
        if exitCode:
            sys.stderr.write(help + "\n")
        else:
            print(help)
        sys.exit(exitCode)
    
    try:
        opts, args = getopt.getopt(sys.argv[1:], "h", 
                        ["mode=", "help", "tolerance=", "ribbon", "polygons", "points", "width=", 
                        "height=", "tab=", "name=", "center-page", "xcenter-page=", "no-colors", "xcolors="])

        if len(args) == 0:
            raise getopt.GetoptError("invalid commandline")

        i = 0
        while i < len(opts):
            opt,arg = opts[i]
            if opt in ('-h', '--help'):
                help()
                sys.exit(0)
            elif opt == '--tolerance':
                tolerance = float(arg)
            elif opt == '--width':
                width = float(arg)
            elif opt == '--height':
                height = float(arg)
            elif opt == '--name':
                baseName = arg
            elif opt == "--ribbon":
                mode = "ribbon"
            elif opt == "--polygons":
                mode = "polygons"
            elif opt == "--points":
                mode = "points"
            elif opt == "--center-page":
                centerPage = True
            elif opt == "--xcenter-page":
                centerPage = (arg == "true" or arg == "1")
            elif opt == "--xcolors":
                colors = (arg == "true" or arg == "1")
            elif opt == "--no-colors":
                colors = False
            elif opt == "--mode":
                mode = arg.strip().lower()
                
            i += 1
                
    except getopt.GetoptError as e:
        sys.stderr.write(str(e)+"\n")
        help(exitCode=1)
        sys.exit(2)
        
    paths, lowerLeft, upperRight = parser.getPathsFromSVGFile(args[0])
    
    if centerPage:
        offset = -0.5*(lowerLeft+upperRight)
    else:
        offset = 0
        
    polygons = extractPaths(paths, offset, tolerance=tolerance, baseName=baseName, colors=colors, colorFromFill=(mode.startswith('pol')), levels=(mode.startswith('pol')))
    
    scad = ""
    if (mode.startswith("pol") or mode[0] == "r") and height > 0:
        scad += "height_%s = %.9f;\n"  % (baseName, height)
    if mode[0] == "r" and width:
        scad += "width_%s = %.9f;\n" % (baseName, width)
        
    if len(scad):
        scad += "\n"
        
    def polyName(i):
        return baseName + "_" + str(i+1)
        
    def subpathName(i,j):
        return polyName(i) + "_" + str(j+1)
        
    for i,polygon in enumerate(polygons):
        scad += "center_%s = [%.9f,%.9f];\n" % (polyName(i), polygon.getCenter().real, polygon.getCenter().imag)
        scad += "size_%s = [%.9f,%.9f];\n" % (polyName(i), polygon.bounds[2]-polygon.bounds[0],polygon.bounds[3]-polygon.bounds[1])
        scad += "stroke_width_%s = %.9f;\n" % (polyName(i), polygon.strokeWidth)
        if colors:
            scad += "color_%s = %s;\n" % (polyName(i), describeColor(polygon.color))
        
    for i,polygon in enumerate(polygons):
        scad += "// paths for %s\n" % polyName(i)
        for j,points in enumerate(polygon.pointLists):
            scad += "points_" + subpathName(i,j) + " = [ " + ','.join('[%.9f,%.9f]' % (point.real,point.imag) for point in points) + " ];\n"
        scad += "\n"

    if mode[0] == "r":
        scad += """module ribbon(points, thickness=1) {
    p = points;
    
    union() {
        for (i=[1:len(p)-1]) {
            hull() {
                translate(p[i-1]) circle(d=thickness, $fn=8);
                translate(p[i]) circle(d=thickness, $fn=8);
            }
        }
    }
}

""" 
        objectName = "ribbon"
        
        for i,polygon in enumerate(polygons):
            scad += "module %s_%s() {\n " % (objectName,polyName(i),)
            if colors:
                scad += "color(color_%s) " % (polyName(i),)
                
            if height > 0:
                scad += "linear_extrude(height=height_%s) " % (baseName,)
            scad += "{\n"
            for j in range(len(polygon.pointLists)):
                scad += "  ribbon(points_%s, thickness=%s);\n" % (subpathName(i,j), ("width_"+baseName) if width else ("stroke_width_"+polyName(i)))
            scad += " }\n}\n\n"
    elif mode.startswith("pol"):
    
        objectName = "polygon"
    
        for i,polygon in enumerate(polygons):
            scad += "module %s_%s() {\n " % (objectName,polyName(i),)
            if colors:
                scad += "color(color_%s) " % (polyName(i),)
            if height > 0:
                scad += "linear_extrude(height=height_%s) " % (baseName,)
            scad += "{\n"
            scad += toNestedPolygons(polygon.levels, lambda j : "points_" + subpathName(i,j))
            scad += " }\n}\n\n"
            
    else:
        objectName = None
        
    if objectName is not None:
        for i in range(len(polygons)):
            scad += "translate(center_%s) %s_%s();\n" % (polyName(i), objectName, polyName(i))
            
    if outfile:
        with open(outfile, "w") as f: f.write(scad)
    else:
        print(scad)    
