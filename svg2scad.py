from __future__ import division
import svgpath.shader as shader
import svgpath.parser as parser
import sys
import getopt
from inflateutils.exportmesh import *

quiet = False

def updateBounds(bounds,points):
    bounds[0] = min(bounds[0], min(p.real for p in points))
    bounds[1] = min(bounds[1], min(p.imag for p in points))
    bounds[2] = max(bounds[0], max(p.real for p in points))
    bounds[3] = max(bounds[1], max(p.imag for p in points))
    
def getCenterX(bounds):
    return 0.5*(bounds[0]+bounds[2])

def getCenterY(bounds):
    return 0.5*(bounds[1]+bounds[3])

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
    def __init__(self,fillColor,edgeColor):
        self.bounds = [float("inf"),float("inf"),float("-inf"),float("-inf")]
        self.fillColor = fillColor
        self.edgeColor = edgeColor
        self.pointLists = []
    
def extractPaths(paths, offset, tolerance=0.1, baseName="svg"):
    polygons = []

    paths = sortedApproximatePaths(paths, error=tolerance )
    
    for i,path in enumerate(paths):
        polygon = PolygonData(path.svgState.fill,path.svgState.stroke)
        polygons.append(polygon)
        for j,subpath in enumerate(path.breakup()):
            points = [subpath[0].start+offset]
            for line in subpath:
                points.append(line.end+offset)
            if subpath.closed and points[0] != points[-1]:
                points.append(points[0]+offset)
            updateBounds(polygon.bounds,points)
            polygon.pointLists.append(points)
        polygon.center = complex(0.5*(polygon.bounds[0]+polygon.bounds[2]),0.5*(polygon.bounds[1]+polygon.bounds[3]))
        for points in polygon.pointLists:
            for j in range(len(points)):
                points[j] -= polygon.center
            
    return polygons
    
def describeColor(c):
    if c is None:
        return "undef";
    else:
        return "[%.5f,%.5f,%.5f]" % tuple(c)
    
if __name__ == '__main__':
    outfile = None
    mode = "svg"
    baseName = "svg"
    tolerance = 0.1
    width = 1
    height = 10
    centerPage = False
    
    def help(exitCode=0):
        help = """python svg2scad.py [options] filename.svg"""
        if exitCode:
            sys.stderr.write(help + "\n")
        else:
            print(help)
        sys.exit(exitCode)
    
    try:
        opts, args = getopt.getopt(sys.argv[1:], "h", 
                        ["mode=", "help", "tolerance=", "ribbon", "polygons", "points", "width=", "height=", "tab=", "name=", "center-page", "--xcenter-page="])

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
        
    polygons = extractPaths(paths, offset, tolerance=tolerance, baseName=baseName)
    
    scad = ""
    if (mode.startswith("pol") or mode[0] == "r") and height > 0:
        scad += "height_%s = %.9f;\n"  % (baseName, height)
    if mode[0] == "r":
        scad += "width_%s = %.9f;\n" % (baseName, width)
        
    if len(scad):
        scad += "\n"
        
    def polyName(i):
        return baseName + "_" + str(i+1)
        
    def subpathName(i,j):
        return polyName(i) + "_" + str(j+1)
        
    for i,polygon in enumerate(polygons):
        scad += "center_%s = [%.9f,%.9f];\n" % (polyName(i), polygon.center.real, polygon.center.imag)
        scad += "fill_color_%s = %s;\n" % (polyName(i), describeColor(polygon.fillColor))
        scad += "outline_color_%s = %s;\n\n" % (polyName(i), describeColor(polygon.edgeColor))
        
    for i,polygon in enumerate(polygons):
        scad += "// paths for %s\n" % polyName(i)
        for j,points in enumerate(polygon.pointLists):
            scad += "points_" + subpathName(i,j) + " = [ " + ','.join('[%.9f,%.9f]' % (point.real,point.imag) for point in points) + " ];\n"
        scad += "\n"

    if mode[0] == "r":
        scad += """module ribbon(points, thickness=width_%s) {
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

""" % (baseName,)

        objectName = "ribbon"
        
        for i,polygon in enumerate(polygons):
            scad += "module %s_%s() {\n " % (objectName,polyName(i),)
            if polygon.edgeColor is not None:
                scad += "color(outline_color_%s) " % (polyName(i),)
            elif polygon.fillColor is not None:
                scad += "color(fill_color_%s) " % (polyName(i),)
                
            if height > 0:
                scad += "linear_extrude(height=height_%s) " % (baseName,)
            scad += "{\n"
            for j in range(len(polygon.pointLists)):
                scad += "  ribbon(points_%s, thickness=width_%s);\n" % (subpathName(i,j), baseName)
            scad += " }\n}\n\n"
    elif mode.startswith("pol"):
    
        objectName = "polygon"
    
        for i,polygon in enumerate(polygons):
            scad += "module %s_%s() {\n " % (objectName,polyName(i),)
            if polygon.fillColor is not None:
                scad += "color(fill_color_%s) " % (polyName(i),)
            elif d.edgeColor is not None:
                scad += "color(outline_color_%s) " % (polyName(i),)
            if height > 0:
                scad += "linear_extrude(height=height_%s) " % (baseName,)
            scad += "{\n"
            for j in range(len(polygon.pointLists)):
                scad += "  polygon(points=points_%s);\n" % subpathName(i,j)  
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
