from __future__ import division
import inflateutils.svgpath.shader as shader
import inflateutils.svgpath.parser as parser
import sys
import getopt
from inflateutils.exportmesh import *

quiet = False

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
        self.bounds[2] = max(self.bounds[0], z.real)
        self.bounds[3] = max(self.bounds[1], z.imag)

    def getCenter(self):
        return complex(0.5*(self.bounds[0]+self.bounds[2]),0.5*(self.bounds[1]+self.bounds[3]))

    
def extractPaths(paths, offset, tolerance=0.1, baseName="svg", colors=True, colorFromFill=False):
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
        polygons.append(polygon)
        for j,subpath in enumerate(path.breakup()):
            points = [subpath[0].start+offset]
            polygon.updateBounds(points[-1])
            for line in subpath:
                points.append(line.end+offset)
                polygon.updateBounds(points[-1])
            if subpath.closed and points[0] != points[-1]:
                points.append(points[0]+offset)
            polygon.pointLists.append(points)
        for points in polygon.pointLists:
            for j in range(len(points)):
                points[j] -= polygon.getCenter()
            
    return polygons
    
if __name__ == '__main__':
    outfile = None
    mode = "points"
    baseName = "svg"
    tolerance = 0.1
    width = 1
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
--width:        ribbon width (thickness)
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
        
    polygons = extractPaths(paths, offset, tolerance=tolerance, baseName=baseName, colors=colors, colorFromFill=(mode.startswith('pol')))
    
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
        scad += "center_%s = [%.9f,%.9f];\n" % (polyName(i), polygon.getCenter().real, polygon.getCenter().imag)
        scad += "size_%s = [%.9f,%.9f];\n" % (polyName(i), polygon.bounds[2]-polygon.bounds[0],polygon.bounds[3]-polygon.bounds[1])
        if colors:
            scad += "color_%s = %s;\n" % (polyName(i), describeColor(polygon.color))
        
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
            if colors:
                scad += "color(color_%s) " % (polyName(i),)
                
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
            if colors:
                scad += "color(color_%s) " % (polyName(i),)
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
