from __future__ import division
from vector import *
from exportmesh import *
import itertools
import os.path
import math
from multiprocessing import Process, Array

class InflationParams(object):
    def __init__(self, thickness=10., flatness=0., exponent=2., iterations=None, hex=True):
        self.thickness = thickness
        self.flatness = flatness
        self.exponent = exponent
        self.iterations = iterations
        self.hex = hex
        
class MeshData(object):
    def __init__(self, cols, rows):
        self.cols = cols
        self.rows = rows
        self.data = tuple([0 for row in range(rows)] for col in range(cols))
        self.mask = tuple([False for row in range(rows)] for col in range(cols))
        
    def clearData(self):
        for x in range(self.cols):
            for y in range(self.rows):
                self.data[x][y] = 0.
        
    def inside(self, col, row):
        return 0 <= col < self.cols and 0 <= row < self.rows and self.mask[col][row]
        
    def getData(self, col, row):
        if 0 <= col < self.cols and 0 <= row < self.rows:
            return self.data[col][row]
        else:
            return 0.

    def getNeighborData(self, col, row, i):
        x,y = self.getNeighbor(col, row, i)
        if 0 <= x < self.cols and 0 <= y < self.rows:
            return self.data[x][y]
        else:
            return 0.
            
    def getPoints(self, useMask=True):
        for i in range(self.cols):
            for j in range(self.rows):
                if not useMask or self.mask[i][j]:
                    yield (i,j)
        
class RectMeshData(MeshData):
    def __init__(self, width, height, lowerLeft, spacing):
        MeshData.__init__(self, 1+int(width / spacing), 1+int(height / spacing))
        self.lowerLeft = lowerLeft
        self.spacing = spacing
        self.numNeighbors = 4
        self.deltas = (Vector(-1,0),Vector(1,0),Vector(0,-1),Vector(0,1))
        self.normalizedDeltas = self.deltas
        
    def getNeighbor(self, col, row,i):
        return (col,row)+self.deltas[i]

    def getCoordinates(self, col,row):
        return self.spacing*Vector(col,row) + self.lowerLeft
        
    def insideCoordinates(self, v):
        v = (v-self.lowerLeft)* (1./self.spacing)
        return self.inside(int(math.floor(0.5+v.x)), int(math.floor(0.5+v.y)))
        
    def getDeltaLength(self, col, row, i):
        return self.spacing
        
    def getMesh(self, twoSided=False, color=None):
        mesh = []
        
        def getValue(z):
            return self.getData(z[0],z[1])
        
        for x in range(-1,self.cols):
            for y in range(-1,self.rows):
                v = Vector(x,y)
                numPoints = sum(1 for delta in ((0,0), (1,0), (0,1), (1,1)) if self.getData(v.x+delta[0],v.y+delta[1]) > 0.)

                def triangles(d1, d2, d3):
                    v1,v2,v3 = v+d1,v+d2,v+d3
                    z1,z2,z3 = map(getValue, (v1,v2,v3))
                    if (z1,z2,z3) == (0.,0.,0.):
                        return []
                    v1 = self.getCoordinates(v1.x,v1.y)
                    v2 = self.getCoordinates(v2.x,v2.y)
                    v3 = self.getCoordinates(v3.x,v3.y)
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
        
    
class HexMeshData(MeshData):
    def __init__(self, width, height, lowerLeft, spacing):
        self.hSpacing = spacing
        self.vSpacing = spacing * math.sqrt(3) / 2.
        self.lowerLeft = lowerLeft + Vector(-self.hSpacing*0.25, self.vSpacing*0.5)
#        height += 10
#        width += 10
        MeshData.__init__(self, 2+int(width / self.hSpacing), 2+int(height / self.vSpacing))
        self.numNeighbors = 6

        self.oddDeltas = (Vector(1,0), Vector(1,1), Vector(0,1), Vector(-1,0), Vector(0,-1), Vector(1,-1))
        self.evenDeltas = (Vector(1,0), Vector(0,1), Vector(-1,1), Vector(-1,0), Vector(-1,-1), Vector(0,-1))
        
        a = math.sqrt(3) / 2.
        self.normalizedDeltas = (Vector(1.,0.), Vector(0.5,a), Vector(-0.5,a), Vector(-1.,0.), Vector(-0.5,-a), Vector(0.5,-a))
        
    def getNeighbor(self, col,row,i):
        if row % 2:
            return Vector(col,row)+self.oddDeltas[i]
        else:
            return Vector(col,row)+self.evenDeltas[i]
            
    def getCoordinates(self, col,row):
        return Vector( self.hSpacing * (col + 0.5*(row%2)), self.vSpacing * row ) + self.lowerLeft
        
    def insideCoordinates(self, v):
        row = int(math.floor(0.5+(v.y-self.lowerLeft.y) / self.vSpacing))
        col = int(math.floor(0.5+(v.x-self.lowerLeft.x) / self.hSpacing -0.5*(row%2)) )
        return self.inside(col, row)
        
    def getColRow(self, v):
        row = int(math.floor(0.5+(v.y-self.lowerLeft.y) / self.vSpacing))
        col = int(math.floor(0.5+(v.x-self.lowerLeft.x) / self.hSpacing -0.5*(row%2)) )
        return (col, row)
        
    def getDeltaLength(self, col, row, i):
        return self.hSpacing

    def getMesh(self, twoSided=False, color=None):
        mesh = []
        
        def getValue(z):
            return self.getData(z[0],z[1])
            
        done = set()
        
        for x,y in self.getPoints():
            neighbors = [self.getNeighbor(x,y,i) for i in range(self.numNeighbors)]
            for i in range(self.numNeighbors):
                triangle = ((x,y), tuple(neighbors[i-1]), tuple(neighbors[i]))
                sortedTriangle = tuple(sorted(triangle))
                if sortedTriangle not in done:
                    done.add(sortedTriangle)
                    v1,v2,v3 = (self.getCoordinates(p[0],p[1]) for p in triangle)
                    z1,z2,z3 = (self.getData(p[0],p[1]) for p in triangle)
                    mesh.append( (color,(Vector(v1.x,v1.y,z1), Vector(v2.x,v2.y,z2), Vector(v3.x,v3.y,z3))) )
                    if not twoSided:
                        z1,z2,z3 = 0.,0.,0.
                    mesh.append( (color,(Vector(v3.x,v3.y,-z3), Vector(v2.x,v2.y,-z2), Vector(v1.x,v1.y,-z1))) )
        return mesh

def inflateRaster(meshData, inflationParams=InflationParams(), distanceToEdge=None):
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
    
    width = meshData.cols
    height = meshData.rows
    
    k = meshData.numNeighbors
    alpha = 1 - 500 * inflationParams.flatness /  max(width,height)**2
    exponent = inflationParams.exponent
    invExponent = 1. / exponent
    
    if distanceToEdge == None:
        adjustedDistances = tuple(tuple(tuple( 1.  for i in range(k)) for y in range(height)) for x in range(width))
    else:
        adjustedDistances = tuple(tuple(tuple( min(distanceToEdge(x,y,i) / meshData.getDeltaLength(x,y,i), 1.)  for i in range(k)) for y in range(height)) for x in range(width))
    
    if not inflationParams.iterations:
        iterations = 25 * max(width,height) 
    else:
        iterations = inflationParams.iterations
        
    meshData.clearData()
    
    for iter in range(iterations):
        newData = tuple([0 for y in range(height)] for x in range(width))

        for x,y in meshData.getPoints(): 
            s = 0
            w = 0
            
            for i in range(k):
                d = adjustedDistances[x][y][i]
                w += 1. / d
                s += (meshData.getNeighborData(x,y,i)**invExponent+d)**exponent / d
            
            newData[x][y] = alpha * s / w
                    
        meshData.data = newData
        
    data = tuple([point**invExponent for point in col] for col in meshData.data)

    maxZ = max(max(col) for col in data)
    
    meshData.data = tuple([datum / maxZ * inflationParams.thickness for datum in col] for col in data)
