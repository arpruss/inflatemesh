from vector import *
from random import shuffle

# triangulation algorithm based on https://www.geometrictools.com/Documentation/TriangulationByEarClipping.pdf
# minus all the double-linked list stuff that would be great but I am not bothering with it

def cross_z(a,b):
    # z-component of cross product
    return a.x * b.y - a.y * b.x

def triangulate(polygon, possibleDegeneracy=False):
    # assume input polygon is counterclockwise
    n = len(polygon)

    if n < 3:
        raise Exception
    
    # efficient special case
    if n == 3:
        return [(0,1,2)]
    
    triangles = []
    polygon = [Vector(v) for v in polygon]
    polygon0 = polygon[:]
    
    index = list(range(n))
    
    def isReflex(i):
        return cross_z(polygon[i]-polygon[i-1], polygon[(i+1) % n]-polygon[i]) < 0
        
    reflex = [isReflex(i) for i in range(n)]

    try:
        reflex.index(True)
    except:
        # no reflex vertices, so convex polygon
        for i in range(1,n-1):
            triangles.append((index[0],index[i],index[i+1]))
        return triangles
    
    def isEar(i):
        #if len(polygon) == 3:
        #    return True
        if reflex[i]:
            return False
        a,b,c = polygon[i-1],polygon[i],polygon[(i+1) % n]
        j = i+2
        ba = b-a
        cb = c-b
        ac = a-c
        while j % n != (i-1) % n:
            if reflex[j % n]:
                p = polygon[j % n]
                if possibleDegeneracy and p == b and polygon[(j-1) % n] == c and polygon[(j+1) % n] == a:
                    return False
                # check if p is inside
                c1 = cross_z(p-a, ba)
                if c1 * cross_z(p-b, cb) > 0 and c1 * cross_z(p-c, ac) > 0:
                    return False
            j += 1
        return True
        
    ear = [isEar(i) for i in range(n)]
    
    while n > 3:
        foundEar = False

        if possibleDegeneracy:
            for i in range(n-1,-1,-1):
                if polygon[i] == polygon[i-2]:
                    del polygon[i]
                    del reflex[i]
                    del ear[i]
                    del index[i]
                    del polygon[i-1]
                    del reflex[i-1]
                    del ear[i-1]
                    del index[i-1]
                    n -= 2
                    if n > 3:
                        reflex[i-2] = isReflex(i-2)
                        ear[i-2] = isEar(i-2)
                        reflex[i-1] = isReflex(i-1)
                        ear[i-1] = isEar(i-1)
                    
            if n <= 3:
                break

        # the backwards search makes the deletions faster
        # if we had a double-indexed list, we wouldn't have this to worry about
        for i in range(n-1,-1,-1):
            if ear[i]:
                triangles.append((index[i-1],index[i],index[(i+1) % n]))
                del polygon[i]
                del reflex[i]
                del ear[i]
                del index[i]
                n -= 1
                # it's tempting to optimize here for the case where n==3, but that would
                # probably be counterproductive, as the n==3 test would run O(n) times
                if reflex[i-1]:
                    reflex[i-1] = isReflex(i-1)
                if reflex[i % n]:
                    reflex[i % n] = isReflex(i % n)
                ear[i-1] = isEar(i-1)
                ear[i % n] = isEar(i % n)
                foundEar = True
                break
                
        assert foundEar
                    
    if n == 3:
        triangles += (tuple(index),)
        
    def isDegenerate(t):
        return polygon0[t[0]] == polygon0[t[1]] or polygon0[t[0]] == polygon0[t[2]] or polygon0[t[1]] == polygon0[t[2]]
        
    return [t for t in triangles if not isDegenerate(t)] if possibleDegeneracy else triangles

def polygonsToSVG(vertices, polys):
    vertices = tuple(Vector(v) for v in vertices)
    minX = min(v.x for v in vertices)
    minY = min(v.y for v in vertices)
    maxX = max(v.x for v in vertices)
    maxY = max(v.y for v in vertices)

    svgArray = []
    svgArray.append('<?xml version="1.0" standalone="no"?>')
    svgArray.append('<svg width="%fmm" height="%fmm" viewBox="0 0 %f %f" xmlns="http://www.w3.org/2000/svg" version="1.1">'%(maxX-minX,maxY-minY,maxX-minX,maxY-minY))
    for p in polys:
        path = '<path stroke="black" stroke-width="0.25mm" opacity="0.5" fill="yellow" d="'
        for i in range(len(p)):
            path += 'L' if i else 'M'
            path += '%.6f %.6f ' % ( vertices[p[i % len(p)]] - (minX,minY) )
        path += ' Z"/>'
        svgArray.append(path)
    svgArray.append('</svg>')
    return '\n'.join(svgArray)
    
def extractLoop(segmentDict, base=None):
    if not segmentDict:
        return []
        
    if base is None:
        base = segmentDict.keys()[0]
    loop = [ base ]
    endPoint = segmentDict[base]
    loop.append(endPoint)

    del segmentDict[base]

    while endPoint != base:
        endPoint2 = segmentDict.get(endPoint)
        if endPoint2 is None:
            break
        loop.append(endPoint2)
        del segmentDict[endPoint]
        endPoint = endPoint2
        
    #return [] if len(loop) <= 1 else return loop
    return loop[:-1] if endPoint == base and len(loop)>1 else []
    
def getSegmentsFromLoop(pointList):
    n = len(pointList)
    for i in range(n):
        yield (pointList[i],pointList[(i+1)%n])
        
def getSegmentsFromDict(dict):
    for k in dict:
        yield (k,dict[k])
        
def intersectSegments(s1,s2):
    def counterclockwise(A,B,C):
        return (C[1]-A[1])*(B[0]-A[0]) > (B[1]-A[1])*(C[0]-A[0])
    return ( counterclockwise(s1[0],s2[0],s2[1]) != counterclockwise(s1[1],s2[0],s2[1])
        and counterclockwise(s1[0],s1[1],s2[0]) != counterclockwise(s1[0],s1[1],s2[1]) )
    
def intersects(segment, segments):
    for s in segments:
        if segment[0] != s[0] and segment[0] != s[1] and segment[1] != s[0] and segment[1] != s[1] and intersectSegments(segment,s):
            return True
    return False
    
def lineSegmentsToPolygon(segments):
    segmentDict = { s[0]:s[1] for s in segments }
    loop = extractLoop(segmentDict)
    #return loop
    didAdd = True
    while segmentDict and didAdd:
        didAdd = False
        n = len(loop)
        for i,p1 in enumerate(loop):
            for p2 in segmentDict:
                if not intersects((p1,p2),getSegmentsFromLoop(loop)) and not intersects((p1,p2),getSegmentsFromDict(segmentDict)):
                    loop2 = extractLoop(segmentDict, base=p2)
                    if loop2:
                        loop = loop[:i+1] + loop2 + [p2] + loop[i:] 
                        #loop = loop[:i] + [p1-Vector(3j)] + loop2 + [p2-Vector(3j)] + loop[i:]
                        didAdd = True                
                        break
            if didAdd:
                break
    return loop

"""    
if __name__ == '__main__':
    import cmath
    import math
    import sys
    import time
    if len(sys.argv) >= 2:
        m = int(sys.argv[1])
    else:
        m = 18
    polygon = [ cmath.exp(2j * math.pi * k / m) * (10 if k%2 else 18) for k in range(m) ]
#    polygon = [ cmath.exp(2j * math.pi * k / m) * (18 if k%2 else 18) for k in range(m) ]
    t = time.time()
    tr = triangulate(polygon)
    t = time.time() - t
    sys.stderr.write("Time %.4fs\n" % t)
#    sys.stderr.write(str(tr)+"\n")
    print(polygonsToSVG(polygon, tr))
"""


if __name__ == '__main__':
    from math import *

    loops = 5
    points = 6
    segments = []

    for j in range(loops):
        r = (loops-j) * 40
        sign = -1 if j%2 else 1
        for i in range(points):
            angle1 = sign * 2 * pi * i / points
            angle2 = sign * 2 * pi * ((i+1)%points) / points
            segments.append( ( (r*cos(angle1),r*sin(angle1)), (r*cos(angle2),r*sin(angle2)) ) )

    loop = [Vector(v) for v in lineSegmentsToPolygon(segments)]
    print(polygonsToSVG(loop,triangulate(loop,possibleDegeneracy=True)))
