from __future__ import division
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

class ExtractedData(object):
    def __init__(self):
        self.pathData = {}
        self.polygon = {}
    
class PathData(object):
    def __init__(self,points,fillColor,edgeColor):
        self.points = points
        self.fillColor = fillColor
        self.edgeColor = edgeColor
    
def extractSVGFile(svgFile, tolerance=0.1, baseName="svg"):
    data = ExtractedData()

    paths = sortedApproximatePaths( parser.getPathsFromSVGFile(svgFile)[0], error=tolerance )
    
    for i,path in enumerate(paths):
        polyName = str(i)
        data.polygon[polyName] = []
        subpaths = []
        for j,subpath in enumerate(path.breakup()):
            points = [subpath[0].start]
            for line in subpath:
                points.append(line.end)
            if subpath.closed and points[0] != points[-1]:
                points.append(points[0])
            name = str(i) + "_" + str(j)
            data.pathData[name] = PathData(points,path.svgState.fill,path.svgState.stroke)
            data.polygon[polyName].append(name)
            
    return data
    
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
    
    def help(exitCode=0):
        help = """python svg2scad.py [options] filename.svg"""
        if exitCode:
            sys.stderr.write(help + "\n")
        else:
            print(help)
        sys.exit(exitCode)
    
    try:
        opts, args = getopt.getopt(sys.argv[1:], "h", 
                        ["mode=", "help", "tolerance=", "ribbon", "polygons", "points", "width=", "height=", "tab=", "name="])

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
            elif opt == "--mode":
                mode = arg.strip().lower()
                
            i += 1
                
    except getopt.GetoptError as e:
        sys.stderr.write(str(e)+"\n")
        help(exitCode=1)
        sys.exit(2)
        
    data = extractSVGFile(args[0], tolerance=tolerance, baseName=baseName)
    
    scad = ""
    if (mode.startswith("pol") or mode[0] == "r") and height > 0:
        scad += "height_%s = %.9f;\n"  % (baseName, height)
    if mode[0] == "r":
        scad += "width_%s = %.9f;\n" % (baseName, width)
        
    for name in sorted(data.pathData):
        d = data.pathData[name]
        scad += "points_" + baseName+ "_" + name + " = [ " + ','.join('[%.9f,%.9f]' % (point.real,point.imag) for point in d.points) + " ];\n"
        scad += "fill_color_" + baseName + "_" + name + " = " + describeColor(d.fillColor) + ";\n"
        scad += "outline_color_" + baseName + "_" + name + " = " + describeColor(d.edgeColor) + ";\n"
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
        
        for name in sorted(data.pathData):
            if data.pathData[name].edgeColor is not None:
                scad += "color(outline_color_%s_%s) " % (baseName,name)
            elif data.pathData[name].fillColor is not None:
                scad += "color(fill_color_%s_%s) " % (baseName,name)
                
        if height > 0:
            scad += "linear_extrude(height=height_%s) " % (baseName,)
        scad += "ribbon(points_%s_%s, thickness=width_%s);\n\n" % (baseName, name, baseName)
    elif mode.startswith("pol"):
        for name in sorted(data.polygon):
            scad += "module polygon_%s_%s() {\n" % (baseName, name)
            for subname in data.polygon[name]:
                scad += " polygon(points=points_%s_%s);\n" % (baseName,subname)
            scad += "}\n\n"
            
        for name in sorted(data.polygon):
            if data.polygon[name]:
                firstName = data.polygon[name][0]
                d = data.pathData[firstName]
                if d.fillColor is not None:
                    scad += "color(fill_color_%s_%s) " % (baseName,firstName)
                elif d.edgeColor is not None:
                    scad += "color(outline_color_%s_%s) " % (baseNane,firstName)
                if height > 0:
                    scad += "linear_extrude(height=height_%s) " % (baseName,)
                scad += "polygon_%s_%s();\n\n" % (baseName,name)
            
    if outfile:
        with open(outfile, "w") as f: f.write(scad)
    else:
        print(scad)    
