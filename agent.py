#!/usr/bin/env python

import sys,os
from scipy import signal,cluster,spatial
import numpy as nu
from imageUtil import getImageData, writeImageData, makeMask, normalize, jitterImageEdges,getPattern
from utilities import argpartition, partition, makeColors
from copy import deepcopy
from PIL import ImageDraw,ImageFont,Image

def assignToAgents(v,agents,AgentType,M,vert=None,horz=None,fixAgents=False,maxWidth=nu.inf):
    data = nu.nonzero(v)[0]
    if len(data) > 1:
        candidates = [tuple(x) if len(x)==1 else (x[0],x[-1]) for x in 
                      nu.split(data,nu.nonzero(nu.diff(data)>1)[0]+1)]
        #print(candidates)
    elif len(data) == 1:
        candidates = [tuple(data)]
    else:
        return agents
    #print(candidates)
    if vert is not None:
        
        candidates = [[nu.array([vert,horz]) for horz in horzz] for horzz in candidates]
    elif horz is not None:
        candidates = [[nu.array([vert,horz]) for vert in vertz] for vertz in candidates]
    else:
        print('error, need to specify vert or horz')
    unadopted = []
    bids = None
    newagents =[]
    if len(agents) == 0:
        unadopted.extend(range(len(candidates)))
    else:
        #print('agents, candidates',len(agents),len(candidates))
        bids = nu.zeros((len(candidates),len(agents)))
        for i,c in enumerate(candidates):
            bids[i,:] = nu.array([nu.abs(a.bid(*c)) for a in agents])
        sortedBets = nu.argsort(bids,1)
        if False: #vert == 326:
            for j,a in enumerate(agents):
                print('{0} {1}'.format(j,a))
            print('candidates',candidates)
            print(sortedBets)
            print(bids[-1,sortedBets[-1,:]])
            sys.exit()
        cidx = nu.argsort(sortedBets[:,0])
        adopters = set([])
        for i in cidx:
            bestBidder = sortedBets[i,0]
            bestBet = bids[i,bestBidder]
            #print('sortedBets')
            #print(sortedBets[i,:])
            #print(bids[i,sortedBets[i,:]])
            bidderHas = bestBidder in adopters
            if bestBet <= agents[bestBidder].maxError and not bidderHas:
                # nu.sum((candidates[i][0]-candidates[i][-1])**2)**.5 < maxWidth and 
                #print('{0} goes to {1}'.format(candidates[i][0][1],agents[bestBidder].id))
                agents[bestBidder].award(*candidates[i])
                adopters.add(bestBidder)
                newagents.append(agents[bestBidder])
            else:
                #print('{0} unadopted, best {1}, available: {2}'.format(candidates[i][0][1],
                #                                                       agents[bestBidder].id,bidderHas))
                unadopted.append(i)
        newagents.extend([agents[x] for x in set(range(len(agents))).difference(adopters)])
    if not fixAgents:
        for i in unadopted:
            #print('unadopted',candidates[i])
            if len(candidates[i]) == 1 or (len(candidates[i]) >1 and (candidates[i][-1][0]-candidates[i][0][0]) <= M/50.):
                # only add an agent if we are on a small section
                newagent = AgentType(nu.mean(nu.array(candidates[i]),0))
                newagents.append(newagent)
    
    #return [a for a in newagents if a.tick(fixAgents)]
    r = partition(lambda x: x.tick(fixAgents),newagents)
    return r.get(True,[]),r.get(False,[])

def mergeAgents(agents):
    if len(agents) < 3:
        return agents,[]
    newagents = []
    N = len(agents)
    pdist = []
    for i in range(N-1):
        for j in range(i+1,N):
            if agents[i].points.shape[0] < 2 or agents[j].points.shape[0] < 2:
                pdist.append(agents[i].maxError+1)
            else:
                #cAngle = ((nu.arctan2(*(agents[i].mean-agents[j].mean))/nu.pi)+1)%1
                # fast check: are means in positions likely for merge?
                if True: #((cAngle-agents[i].targetAngle+.5)%1-.5) < agents[i].maxAngleDev:
                #if nu.abs(cAngle-agents[i].targetAngle) < agents[i].maxAngleDev:
                    # yes, do further check
                    pdist.append(agents[i].mergeable(agents[j]))
                else:
                    # no, exclude
                    pdist.append(agents[i].maxError+1)
    pdist = nu.array(pdist)
    l = cluster.hierarchy.complete(pdist)
    c = cluster.hierarchy.fcluster(l,agents[0].maxError,criterion='distance')
    idict = argpartition(lambda x: x[0], nu.column_stack((c,nu.arange(len(c)))))
    died = []
    for v in idict.values():
        if len(v) == 1:
            newagents.append(agents[v[0]])
        else:
            a = agents[v[0]]
            for i in v[1:]:
                a.merge(agents[i])
            newagents.append(a)
            died.extend(v[1:])
    return newagents,died

def tls(X):
    """total least squares for 2 dimensions
    """
    u,s,v = nu.linalg.svd(X)
    #v = v.T
    #return ((nu.arctan2(-v[1,1],v[0,1])-nu.pi)%nu.pi)/nu.pi
    #return ((nu.arctan2(-v[1,1],v[1,0])-nu.pi)%nu.pi)/nu.pi
    return (nu.arctan2(-v[1,1],v[1,0])/nu.pi+1)%1.0

def getError(x,a):
    return nu.sum(nu.dot(x,nu.array([nu.cos(a*nu.pi),-nu.sin(a*nu.pi)]).T)**2)**.5

def makeAgentClass(targetAngle,maxAngleDev,maxError,minScore,offset=0,yoffset=0):
    class CustomAgent(Agent): pass
    CustomAgent.targetAngle = (targetAngle+1.0)%1
    CustomAgent.maxError = maxError
    CustomAgent.maxAngleDev = maxAngleDev
    CustomAgent.minScore = minScore
    CustomAgent.offset = offset
    CustomAgent.yoffset = yoffset
    CustomAgent.aoffset = nu.array((offset,yoffset))
    return CustomAgent

class Agent(object):
    targetAngle = None
    maxError = None
    maxAngleDev = None
    minScore = None

    def __init__(self,xy0,xy1=None):
        self.lineWidth = []
        if xy1 != None:
            xy = (xy0+xy1)/2.0
            self._addLineWidth(1+nu.sum((xy0-xy1)**2)**.5)
        else:
            xy = xy0
            self._addLineWidth(1.0)
        self.points = nu.array(xy).reshape((1,2))
        self.mean = xy
        self.angleDev = 0
        self.error = 0
        self.score = 0
        self.adopted = True
        self.age = 0
        self.id = str(self.__hash__())
        self.offspring = 0

    def __str__(self):
        return 'Agent: {id}; angle: {angle:0.4f} ({ta:0.4f}+{ad:0.4f}); error: {err:0.3f} age: {age}; npts: {pts}; score: {score}; mean: {mean}'\
            .format(id=self.id,err=self.error,angle=self.angle,ta=self.targetAngle,ad=self.angleDev,
                    age=self.age,pts=self.points.shape[0],score=self.score,mean=self.getDrawMean())
    
    def getLineWidth(self):
        return self.lw

    def getLineWidthStd(self):
        return self.lwstd

    def _addLineWidth(self,w):
        self.lineWidth.append(w)
        self.lw = nu.median(self.lineWidth)
        self.lwstd = nu.std(self.lineWidth)

    @property
    def angle(self):
        return self.targetAngle + self.angleDev

    def getDrawPoints(self):
        return self.points+self.aoffset
    def getDrawMean(self):
        return self.mean+self.aoffset

    def getMiddle(self,M):
        "get Vertical position of agent at the horizontal center of the page of width M" 
        x = self.mean[0]+(M/2.0-self.mean[1])*nu.tan(self.angle*nu.pi)
        return x

    def mergeable(self,other):
        if other.age > 1 and self.age > 1:
            #e0 = getError(other.points-self.mean,self.angle)/float(other.points.shape[0])
            #e1 = getError(self.points-other.mean,other.angle)/float(self.points.shape[0])
            e0 = getError(other.getDrawPoints()-self.getDrawMean(),self.angle)/float(other.points.shape[0])
            e1 = getError(self.getDrawPoints()-other.getDrawMean(),other.angle)/float(self.points.shape[0])
            #if 950 < self.mean[1] < 960 and 950 < other.mean[1] < 960:
            #    print('mergeable:')
            #    print(self)
            #    print(other)
            #    print((e0+e1)/2.0,self.maxError)
            return (e0+e1)/2.0
        else:
            return self.maxError+1

    def mergeOld(self,other):
        self.points = nu.array(tuple(set([tuple(y) for y in nu.vstack((self.points,other.points))])))
        self.lineWidth = self.lineWidth+other.lineWidth
        self.mean = nu.mean(self.points,0)
        self.angleDev = ((tls(self.points-self.mean)-self.targetAngle)+.5)%1-.5
        self.error = getError(self.points-self.mean,self.angle)/self.points.shape[0]
        self.age = max(self.age,other.age)
        self.score = self.score+other.score

    def merge(self,other):
        
        self.points = nu.array(tuple(set([tuple(y) for y in 
                                          nu.vstack((self.points,other.getDrawPoints()-self.aoffset))])))
        self.lineWidth = self.lineWidth+other.lineWidth
        self.mean = nu.mean(self.points,0)
        self.angleDev = ((tls(self.points-self.mean)-self.targetAngle)+.5)%1-.5
        self.error = getError(self.points-self.mean,self.angle)/self.points.shape[0]
        self.age = max(self.age,other.age)
        self.score = self.score+other.score
        
            
    def tick(self,immortal=False):
        self.offspring = 0
        self.age += 1
        if self.adopted:
            self.score += 1
        else:
            self.score -= 1
        #self.scorehist.append((self.age,self.score))
        self.adopted = False
        if immortal:
            return True
        else:
            return not self.died()
    
    def died(self):
        angleOK = nu.abs(self.angleDev) <= self.maxAngleDev
        errorOK = self.error <= self.maxError
        successRateOK = self.score >= self.minScore
        r = not all((angleOK,errorOK,successRateOK))
        #if r:
        #    print('Died: {0}; angleOK: {1}; errorOK: {2}, scoreOK: {3}'.format(self,angleOK,errorOK,successRateOK))
        return r
  
    def getIntersection(self,xy0,xy1):
        # NB: x and y coordinates are in reverse order
        # because of image conventions: x = vertical, y = horizontal
        dy,dx = nu.array(xy0-xy1,nu.float)
        # slope of new line
        slope = dy/dx
        ytilde,xtilde = xy0-self.mean
        # offset of new line
        b = (ytilde-slope*xtilde)
        # special case 1: parallel lines
        if slope == nu.tan(nu.pi*self.angle):
            print('parallel',slope)
            return None

        # special case 2: vertical line
        if nu.isinf(slope):
            # x constant
            x = xy0[1]
            y = nu.tan(nu.pi*self.angle)*(x - self.mean[1])+self.mean[0]
            return nu.array((y,x))
        # special case 3: line undefined
        if nu.isnan(slope):
            # undefined slope, constant y
            return None

        x = b/(nu.tan(nu.pi*self.angle)-slope)
        r =  nu.array((slope*x+b,x))+self.mean
        return r

    def _getAngleDistance(self,a):
        #return -nu.arctan2(*(xy-self.mean))/nu.pi
        return (a-self.targetAngle+.5)%1-.5

    def _getAngle(self,xy):
        #return -nu.arctan2(*(xy-self.mean))/nu.pi
        return ((nu.arctan2(*((xy-self.mean)))/nu.pi)+1)%1

    def _getClosestAngle(self,a):
        return nu.sort([(a+1)%1,self.angle-self.maxAngleDev,
                        self.angle+self.maxAngleDev])[1]

    def preparePointAdd(self,xy0,xy1=None):
        if xy1 != None:
            error0 = nu.dot(xy0-self.mean,nu.array([nu.cos(self.angle*nu.pi),-nu.sin(self.angle*nu.pi)]))
            error1 = nu.dot(xy1-self.mean,nu.array([nu.cos(self.angle*nu.pi),-nu.sin(self.angle*nu.pi)]))
            lw = 1+nu.sum((xy0-xy1)**2)**.5
            #print(self)
            #print('lw',lw,self.getLineWidth(),self.getLineWidthStd())
            #print('prepare point add',xy0,xy1)
            acceptableWidth = lw <= self.getLineWidth() + max(1,self.getLineWidthStd())
            if nu.sign(error0) != nu.sign(error1) and not acceptableWidth:
                xy = self.getIntersection(xy0,xy1)
            else:
                if acceptableWidth: #lw <= self.getLineWidth() + max(1,self.getLineWidthStd()):
                    # it's most probably a pure segment of the line, store the mean
                    xy = (xy0+xy1)/2.0
                else:
                    # too thick to be a line, store the point that has smallest error
                    xy = (xy0,xy1)[nu.argmin(nu.abs([error0,error1]))]
        else:
            lw = 1.0
            xy = xy0
        points = nu.vstack((self.points,xy))
        mean = nu.mean(points,0)
        tlsr = tls(points-mean)
        angleDev = ((tlsr-self.targetAngle)+.5)%1-.5
        error = getError(points-mean,angleDev+self.targetAngle)/points.shape[0]
        return error,angleDev,mean,lw,points

    def bid(self,xy0,xy1=None):
        # distance of xy0 to the current line (defined by self.angle)
        if self.points.shape[0] == 1:
            # we have no empirical angle yet
            # find the optimal angle (within maxAngleDev), and give the error respective to that
            if xy1 == None:
                xyp1 = xy0
            else:
                xyp1 = xy1
            aa0 = self._getAngleDistance(self._getAngle(xy0))
            aa1 = self._getAngleDistance(self._getAngle(xyp1))
            angle = nu.sort([self.targetAngle+aa0,self.targetAngle+aa1,self.angle])[1]
        else:
            angle = self.angle
        if nu.abs(self._getAngleDistance(angle)) > self.maxAngleDev:
            return self.maxError+1
        # print('adjusting angle:',self.angle,'to',angle)
        anglePen = nu.abs(self.angle-angle)
        error0 = nu.dot((xy0-self.mean),nu.array([nu.cos(angle*nu.pi),-nu.sin(angle*nu.pi)]))
        if xy1 == None:
            return nu.abs(error0)+anglePen
        error1 = nu.dot(xy1-self.mean,nu.array([nu.cos(angle*nu.pi),-nu.sin(angle*nu.pi)]))
        if nu.sign(error0) != nu.sign(error1):
            return 0.0+anglePen
        else:
            return min(nu.abs(error0),nu.abs(error1))+anglePen

    def award(self,xy0,xy1=None):
        self.adopted = True
        
        self.error,self.angleDev,self.mean,lw,self.points = self.preparePointAdd(xy0,xy1=xy1)
        self._addLineWidth(lw)

class AgentPainter(object):
    def __init__(self,img):
        self.img = nu.array((255-img,255-img,255-img))
        self.imgOrig = nu.array((255-img,255-img,255-img))
        self.maxAgents = 300
        self.colors = makeColors(self.maxAgents)
        self.paintSlots = nu.zeros(self.maxAgents,nu.bool)
        self.agents = {}

    def writeImage(self,fn,absolute=False):
        #print(nu.min(img),nu.max(img))
        self.img = self.img.astype(nu.uint8)
        if absolute:
            fn = fn
        else:
            fn = os.path.join('/tmp',os.path.splitext(os.path.basename(fn))[0]+'.png')
        print(fn)
        writeImageData(fn,self.img.shape[1:],self.img[0,:,:],self.img[1,:,:],self.img[2,:,:])

    def isRegistered(self,agent):
        return self.agents.has_key(agent)
        
    def register(self,agent):
        if self.isRegistered(agent):
            return True
        available = nu.where(self.paintSlots==0)[0]
        if len(available) < 1:
            print('no paint slots available')
            return False
        #print('registring {0}'.format(agent.id))
        #print(agent.__hash__())
        self.agents[agent] = available[0]
        self.paintSlots[available[0]] = True
        #self.paintStart(agent.point,self.colors[self.agents[agent]])

    def unregister(self,agent):
        if self.agents.has_key(agent):
            self.paintSlots[self.agents[agent]] = False
            #print('unregistring {0}'.format(agent.id))
            del self.agents[agent]

        else:
            sys.stderr.write('Warning, unknown agent\n')
        
    def reset(self):
        self.img = self.imgOrig.copy()

    def drawText(self, text, pos, size=30, color=(100,100,100), alpha=.5):
        font = ImageFont.truetype('/usr/share/fonts/truetype/ttf-ubuntu-title/Ubuntu-Title.ttf', 
                                  size)
        size = font.getsize(text) # Returns the width and height of the given text, as a 2-tuple.
        im = Image.new('L', size, 255) # Create a blank image with the given size
        draw = ImageDraw.Draw(im)
        draw.text((0,0), text, font=font, fill=None) #Draw text
        d = 255-nu.array(im.getdata(),nu.uint8).reshape(size[::-1])
        maxX = min(self.img.shape[1]-1,d.shape[0]+pos[0])-pos[0]
        maxY = min(self.img.shape[2]-1,d.shape[1]+pos[1])-pos[1]
        d = d[:maxX,:maxY]
        xx,yy = nu.nonzero(d)
        
        vv = d[xx,yy]/255.
        xx += pos[0]
        yy += pos[1]
        alpha = vv*alpha
        self.img[0,xx,yy] = ((1-alpha)*self.img[0,xx,yy] + alpha*color[0]).astype(nu.uint8)
        self.img[1,xx,yy] = ((1-alpha)*self.img[1,xx,yy] + alpha*color[1]).astype(nu.uint8)
        self.img[2,xx,yy] = ((1-alpha)*self.img[2,xx,yy] + alpha*color[2]).astype(nu.uint8)

    def drawAgentGood(self,agent,rmin=-100,rmax=100):
        if self.agents.has_key(agent):
            #print('drawing')
            #print(agent)
            c = self.colors[self.agents[agent]]
            c1 = nu.minimum(255,c+50)
            c2 = nu.maximum(0,c-100)
            M,N = self.img.shape[1:]
            rng = nu.arange(rmin,rmax)
            xy = nu.round(nu.column_stack((rng*nu.sin(agent.angle*nu.pi)+agent.getDrawMean()[0],
                                           rng*nu.cos(agent.angle*nu.pi)+agent.getDrawMean()[1])))
            idx = nu.logical_and(nu.logical_and(xy[:,0]>=0,xy[:,0]<M),
                                 nu.logical_and(xy[:,1]>=0,xy[:,1]<N))
            alpha = min(.8,max(.1,.5+float(agent.score)/max(1,agent.age)))
            xy = xy[idx,:]
            if xy.shape[0] > 0:
                self.paintRav(xy,c2,alpha)
            #for r in range(rmin,rmax):
            #    x = r*nu.sin(agent.angle*nu.pi)+agent.getDrawMean()[0]
            #    y = r*nu.cos(agent.angle*nu.pi)+agent.getDrawMean()[1]
            #    #print(r,agent.angle,agent.getDrawMean(),x,y)
            #    #print(x,y)
            #    if 0 <= x < M and 0 <= y < N:
            #        self.paint(nu.array((x,y)),c2,alpha)

            self.paintRect(agent.getDrawPoints()[0][0],agent.getDrawPoints()[0][0],
                           agent.getDrawPoints()[0][1],agent.getDrawPoints()[0][1],c)
            #self.paintRect(agent.getDrawMean()[0]+2,agent.getDrawMean()[0]-2,
            #               agent.getDrawMean()[1]+2,agent.getDrawMean()[1]-2,c)

            self.paintRav(agent.getDrawPoints(),c1)
            #for p in agent.getDrawPoints():
            #    self.paint(p,c1)

    def drawAgent(self,agent,rmin=-100,rmax=100,rotator=None):
        if self.agents.has_key(agent):
            c = self.colors[self.agents[agent]]
            c1 = nu.minimum(255,c+50)
            c2 = nu.maximum(0,c-100)
            M,N = self.img.shape[1:]
            #rng = nu.arange(rmin,rmax)
            rng = nu.arange(rmin,rmax,.95)
            xy = nu.round(nu.column_stack((rng*nu.sin(agent.angle*nu.pi)+agent.getDrawMean()[0],
                                           rng*nu.cos(agent.angle*nu.pi)+agent.getDrawMean()[1])))
            if rotator:
                xy = rotator.derotate(xy)
            idx = nu.logical_and(nu.logical_and(xy[:,0]>=0,xy[:,0]<M),
                                 nu.logical_and(xy[:,1]>=0,xy[:,1]<N))
            alpha = min(.8,max(.1,.5+float(agent.score)/max(1,agent.age)))
            xy = xy[idx,:].astype(nu.int)
            if xy.shape[0] > 0:
                self.paintRav(xy,c2,alpha)

            # first point
            if agent.getDrawPoints().shape[0] > 0:
                fPoint = agent.getDrawPoints()[0].reshape((1,2))
                if rotator:
                    fPoint = rotator.derotate(fPoint)[0,:]
                else:
                    fPoint = fPoint[0,:]
                self.paintRect(fPoint[0],fPoint[0],fPoint[1],fPoint[1],c)

            drp = agent.getDrawPoints()
            if rotator:
                drp = rotator.derotate(drp)
            self.paintRav(drp,c1)

    def paintRav(self,coords,color,alpha=1):
        idx = (self.img.shape[2]*nu.round(coords[:,0])+nu.round(coords[:,1])).astype(nu.int64)
        self.img[0,:,:].flat[idx] = nu.minimum(255,nu.maximum(0,(1-alpha)*self.img[0,:,:].flat[idx]+alpha*color[0])).astype(nu.uint8)
        self.img[1,:,:].flat[idx] = nu.minimum(255,nu.maximum(0,(1-alpha)*self.img[1,:,:].flat[idx]+alpha*color[1])).astype(nu.uint8)
        self.img[2,:,:].flat[idx] = nu.minimum(255,nu.maximum(0,(1-alpha)*self.img[2,:,:].flat[idx]+alpha*color[2])).astype(nu.uint8)


    def paint(self,coord,color,alpha=1):
        #print('point',coord,img.shape)
        self.img[:,int(coord[0]),int(coord[1])] = (1-alpha)*self.img[:,int(coord[0]),int(coord[1])]+alpha*color

    def paintVLine(self,y,alpha=.5,step=1,color=(100,0,100)):
        if 0 <= y < self.img.shape[2]:
            self.img[0,::step,y] = nu.minimum(255,nu.maximum(0,((1-alpha)*self.img[0,::step,y]+alpha*color[0]))).astype(nu.uint8)
            self.img[1,::step,y] = nu.minimum(255,nu.maximum(0,((1-alpha)*self.img[1,::step,y]+alpha*color[1]))).astype(nu.uint8)
            self.img[2,::step,y] = nu.minimum(255,nu.maximum(0,((1-alpha)*self.img[2,::step,y]+alpha*color[2]))).astype(nu.uint8)

    def paintHLine(self,x,alpha=.5,step=1,color=(0,255,255)):
        if 0 <= x < self.img.shape[1]:
            self.img[0,x,::step] = nu.minimum(255,nu.maximum(0,((1-alpha)*self.img[0,x,::step]+alpha*color[0]))).astype(nu.uint8)
            self.img[1,x,::step] = nu.minimum(255,nu.maximum(0,((1-alpha)*self.img[1,x,::step]+alpha*color[1]))).astype(nu.uint8)
            self.img[2,x,::step] = nu.minimum(255,nu.maximum(0,((1-alpha)*self.img[2,x,::step]+alpha*color[2]))).astype(nu.uint8)


    def paintRect(self,xmin,xmax,ymin,ymax,color,alpha=.5):
        rectSize = 10
        N,M = self.img.shape[1:]
        t = int(max(0,xmin-nu.floor(rectSize/2.)))
        b = int(min(N-1,xmax+nu.floor(rectSize/2.)))
        l = int(max(0,ymin-nu.floor(rectSize/2.)))
        r = int(min(M-1,ymax+nu.floor(rectSize/2.)))
        #self.img[:,:,int(ymin)] = (1-alpha)*self.img[:,:,int(ymin)]+alpha*0
        #self.img[:,int(xmin),:] = (1-alpha)*self.img[:,int(xmin),:]+alpha*0
        for i,c in enumerate(color):
            self.img[i,t:b,l] = c
            self.img[i,t:b,r] = c
            self.img[i,t,l:r] = c
            self.img[i,b,l:r+1] = c


if __name__ == '__main__':
    StaffAgent = makeAgentClass(targetAngle=.005,
                                maxAngleDev=5/180.,
                                maxError=20,
                                minScore=-2,
                                offset=0)
    partner = nu.array((3,0))
    
    #high
    #x01 = nu.array([200.0,200])
    #x11 = nu.array([200.0,205])
    #low
    x = nu.array([(40,10,3),
                  (45,510,3),
                  (53,1010,3),
                  (50,1050,3),
                  (42,850,30)
                  ])

    N,M = 1000,2000
    img = nu.zeros((N,M))
    
    def getPoints(i):
        return x[i,:2],x[i,:2]+nu.array((x[i,2],0))

    for i in range(x.shape[0]):
        img[x[i,0],x[i,1]] = 255
        img[x[i,0]+x[i,2],x[i,1]] = 255
    ap = AgentPainter(img)
    a0 = StaffAgent(*getPoints(0))
    ap.writeImage('hoi00a.png')
    ap.register(a0)

    ap.drawAgentGood(a0,-2000,2000)
    ap.writeImage('hoi00b.png')
    
    for i in range(1,x.shape[0]):
        print(a0)
        ap.reset()
        print('bid',a0.bid(*getPoints(i)))
        print('award',a0.award(*getPoints(i)))
        print('pass?',a0.tick())
        ap.drawAgentGood(a0,-2000,2000)
        ap.writeImage('hoi{0:02d}.png'.format(i))
        print('')

    print(a0)
    print('d',a0.getIntersection(*getPoints(-1)))

    print('\n\n')
    sys.exit()

    print('')
    y1 = nu.array((400,2000))
    #print('a',a0._getAngle(y1))
    print('bid',a0.bid(y1,y1+partner))
    print('award',a0.award(y1,y1+nu.array((3,0))))
    print(a0)
    print('pass?',a0.tick())
    
    
