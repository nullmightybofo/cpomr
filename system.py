#!/usr/bin/env python

import sys,os
import numpy as nu
from utils import Rotator
from utilities import getter
from agent import makeAgentClass, AgentPainter, assignToAgents, mergeAgents
from utils import selectColumns
from imageUtil import getAntiAliasedImg
from bar import Bar

def sortBarAgents(agents):
    agents.sort(key=lambda x: -x.score)
    scores = nu.append(nu.array([x.score for x in agents if x.score > 1]),0)
    hyp = 0
    if len(scores) > 1:
        hyp = nu.argmin(nu.diff(scores))
        #print(scores)
        print('guessing:',hyp+1)
    return hyp+1

class System(object):
    def __init__(self,scoreImage,staffs,n=0):
        self.scrImage = scoreImage
        self.staffs = staffs
        self.barPoints = []
        self.dodraw = False
        # system counter
        self.n = n

    def getTop(self):
        return self.staffs[0].top
    def getBottom(self):
        return self.staffs[1].bottom

    def addBarPoint(self,xy):
        self.barPoints.append(xy)

    def getLowerLeft(self):
        return self.getSystemPoints()[2]

    def getUpperLeft(self):
        return self.getSystemPoints()[0]

    def getLowerMid(self):
        return self.getSystemPoints()[4]

    def getLowerMidLocal(self):
        return nu.array((self.getSystemHeight()-1,int((self.getSystemWidth()-1)/2)))

    @getter
    def getSystemPoints(self):
        # returns topleft, topright, botleft, botright, and lower hmid
        # of tilted rectangle, such that all above coordinates fall inside the img
        hMid = int(self.scrImage.getWidth()/2.)
        # sometimes the staff is close to the border of the segment
        extra = nu.array((int(nu.ceil(self.getStaffLineDistance())),0))

        top = self.staffs[0].top-extra[0]
        bot = self.staffs[1].bottom+extra[0]

        dyl = -hMid
        dyr = self.scrImage.getWidth()-hMid

        botLeft = bot+dyl*nu.tan(nu.pi*self.getStaffAngle())
        botRight = bot+dyr*nu.tan(nu.pi*self.getStaffAngle())
        topLeft = top+dyl*nu.tan(nu.pi*self.getStaffAngle())
        topRight = top+dyr*nu.tan(nu.pi*self.getStaffAngle())

        botCorrection = min(0,nu.floor(self.scrImage.getHeight()-max(botLeft,botRight)-1))
        topCorrection = min(0,nu.floor(min(topLeft,topRight))-1)
        return (nu.array((topLeft-topCorrection,0)),
             nu.array((topRight-topCorrection,self.scrImage.getWidth())),
             nu.array((botLeft+botCorrection,0)),
             nu.array((botRight+botCorrection,self.scrImage.getWidth())),
             nu.array((bot+botCorrection,hMid)))


    def draw(self):
        for staff in self.staffs:
            staff.draw()
        self.drawBarPoints()

    def drawBarPoints(self):
        lower = int(self.getLowerLeft()[0])
        upper = int(self.getUpperLeft()[0])
        r = lower-upper
        c = nu.array((255,0,0))
        for p in self.barPoints:
            self.scrImage.ap.paintRav(nu.column_stack((nu.arange(upper,lower),(nu.zeros(r)+p[0]).astype(nu.int))),
                                      c)
        
    def getStaffAngle(self):
        return nu.mean([s.getAngle() for s in self.staffs])

    @getter
    def getHSums(self):
        return nu.sum(self.getCorrectedImgSegment(),1)

    @getter
    def getStaffLineWidth(self):
        return nu.mean([a.getLineWidth() for a in self.staffs[0].staffLineAgents]+
                       [a.getLineWidth() for a in self.staffs[1].staffLineAgents])

    @getter
    def getStaffLineDistance(self):
        return (self.staffs[0].getStaffLineDistance()+self.staffs[1].getStaffLineDistance())/2.0

    def getImgHParts(self,hbins,overlap):
        M,N = self.getCorrectedImgSegment().shape
        overlapPix = int(overlap*N/2.)
        breaks = nu.linspace(0,N,hbins+1)
        lefts = breaks[:-1].copy()
        lefts[1:] -= overlapPix
        rights = breaks[1:].copy()
        rights[:-1] += overlapPix
        return [self.getCorrectedImgSegment()[:,lefts[i]:rights[i]]
                for i in range(len(lefts))],lefts,rights
            
    @getter
    def getBarLines(self):
        """
        strategy:
        * run barline detection for different (slightly overlapping) segements
        * join agents (+merge)
        """
        #systemTopL = self.getRotator().rotate(self.staffs[0].staffLineAgents[0].getDrawMean().reshape((1,2)))[0,0]
        #systemBotL = self.getRotator().rotate(self.staffs[1].staffLineAgents[-1].getDrawMean().reshape((1,2)))[0,0]
        vbins = 5
        hbins = 5
        overlap = .1 # of width
        hparts,lefts,rights = self.getImgHParts(hbins,overlap)
        agents = []
        for i,hpart in enumerate(hparts):
            agents.extend(self.getBarLinesPart(hpart,vbins,lefts[i],rights[i],i))
        agents,died = mergeAgents(agents)
        agents.sort(key=lambda x: -x.score)
        for a in agents:
            print(a)
        #print('s',[x.shape for x in p])
        return agents
        #hsums = self.getHSums()[int(systemTopL):int(systemBotL)]
        #rows = selectColumns(hsums,bins)[0]+int(systemTopL) # sounds funny, change name of function       
        
    def getBarLinesPart(self,img,vbins,yoffset,rightBorder,j):
        BarAgent = makeAgentClass(targetAngle=.5,
                                  maxAngleDev=4/180.,
                                  #maxError=1,
                                  maxError=self.getStaffLineWidth()/7.0,
                                  minScore=-2,
                                  yoffset=yoffset)
        agents = []
        systemTopL = self.getRotator().rotate(self.staffs[0].staffLineAgents[0].getDrawMean().reshape((1,2)))[0,0]
        systemBotL = self.getRotator().rotate(self.staffs[1].staffLineAgents[-1].getDrawMean().reshape((1,2)))[0,0]
        hsums = nu.sum(img,1)[int(systemTopL):int(systemBotL)]
        rows = selectColumns(hsums,vbins)[0]+int(systemTopL) # sounds funny, change name of function       

        ap = AgentPainter(self.getCorrectedImgSegment())
        ap.paintVLine(yoffset,step=4,color=(50,150,50))
        ap.paintVLine(rightBorder,step=4,color=(50,150,50))
        #draw = self.dodraw
        draw = False
        K = int(.1*len(rows))
        for i,r in enumerate(rows[:K]):
            died = []
            agentsnew,d = assignToAgents(img[r,:],agents,BarAgent,
                                         self.getCorrectedImgSegment().shape[1],
                                         vert=r,fixAgents=False)
            died.extend(d)

            if len(agents) > 2:
                agentsnew,d = mergeAgents(agentsnew)
                died.extend(d)
            agents = agentsnew
            draw = False#self.n==0 and j==4
            if draw:
                ap.reset()
                ap.paintHLine(r,step=2,color=(50,50,50))
                for a in died:
                    ap.unregister(a)
                for a in agents:
                    ap.register(a)
                    ap.drawAgent(a,-400,400)
                ap.writeImage('system{0:04d}-part{1:04d}-{2:04d}-r{3:04d}.png'.format(self.n,j,i,r))
            #assert len(set(agents).intersection(set(died))) == 0
            #print('row',i)
            if len(agents) > 1:
                agents.sort(key=lambda x: -x.score)
        return [a for a in agents if a.score > 1 and a.age > .1*K]

    @getter
    def getBarLinesOld(self):
        agents = []
        defBarAngle = .5 #(self.getStaffAngle()+.5)%1
        print('default staff angle for this system',self.getStaffAngle())
        #print('default bar angle for this system',defBarAngle)
        #assert defBarAngle >= 0
        print('slw',self.getStaffLineWidth())
        BarAgent = makeAgentClass(targetAngle=defBarAngle,
                                  maxAngleDev=4/180.,
                                  #maxError=1,
                                  maxError=self.getStaffLineWidth()/7.0,
                                  minScore=-2,
                                  offset=0)
        systemTopL = self.getRotator().rotate(self.staffs[0].staffLineAgents[0].getDrawMean().reshape((1,2)))[0,0]
        systemBotL = self.getRotator().rotate(self.staffs[1].staffLineAgents[-1].getDrawMean().reshape((1,2)))[0,0]
        bins = 5
        hsums = self.getHSums()[int(systemTopL):int(systemBotL)]
        rows = selectColumns(hsums,bins)[0]+int(systemTopL) # sounds funny, change name of function       
        #rows = [p for p in selectColumns(self.getHSums(),bins)[0] if systemTopL <= p <= systemBotL] # sounds funny, change name of function
        
        finalStage = False
        k = 0
        ap = AgentPainter(self.getCorrectedImgSegment())
        #draw = True
        #draw = False
        draw = self.dodraw
        for i,r in enumerate(rows[:int(.15*len(rows))]):
            died = []
            agentsnew,d = assignToAgents(self.getCorrectedImgSegment()[r,:],agents,BarAgent,
                                            self.getCorrectedImgSegment().shape[1],vert=r,fixAgents=finalStage)
            died.extend(d)

            if len(agents) > 2:
                agentsnew,d = mergeAgents(agentsnew)
                died.extend(d)
            agents = agentsnew
            #assert len(set(agents).intersection(set(died))) == 0
            #print('row',i)
            if len(agents) > 1:
                agents.sort(key=lambda x: -x.score)

            if draw:
                ap.reset()
                ap.paintHLine(r)
                for a in died:
                    #ap.drawAgent(a,-300,300)
                    ap.unregister(a)
                for j,a in enumerate(agents):
                    print('{0} {1}'.format(j,a))
                    ap.register(a)
                    ap.drawAgent(a,-300,300)
                f0,ext = os.path.splitext(self.scrImage.fn)
                print(f0,ext)
                ap.writeImage(f0+'-{0:04d}-r{1}'.format(i,r)+'.png')
        #k = sortBarAgents(agents)
        bAgents = [a for a in agents if a.score > 1]
        bAgents.sort(key=lambda x: -x.score)
        #bAgents = agents[:k]
        meanScore = nu.mean([a.score for a in bAgents])
        meanAge = nu.mean([a.age for a in bAgents])
        for j,a in enumerate(agents):
            print('{0} {1}'.format(j,a))
        agents = [a for a in agents if a.score > .2*meanScore and a.age > .5*meanAge]
        print('chose {0} agents'.format(len(agents)))
        agents.sort(key=lambda x: x.getDrawMean()[1])
        
        if True:
            return agents

        draw = False
        if draw:
            ap.reset()
            for a in agents:
                print(a)
                ap.register(a)
                ap.drawAgentGood(a,-300,300)
            f0,ext = os.path.splitext(self.scrImage.fn)
            print(f0,ext)
            ap.writeImage(f0+'-sys{0:04d}.png'.format(int(self.getLowerLeft()[0])))
        bf = []
        est = []
        for j,a in enumerate(agents):
            b = Bar(self,a)
            ap1 = AgentPainter(b.getNeighbourhood())
            #bu = b.findVerticalStaffLinePositions()
            bf.append([j]+list(b.getFeatures()))
            est.append([j]+list(1000*b.getEstimates()))
            #print(bu)
            #for i,u in enumerate(bu):
            #    ap1.paintHLine(nu.floor(u),step=2,color=(255,0,0))
            #    ap1.paintHLine(nu.ceil(u+self.getStaffLineWidth()),step=2,color=(255,0,0))
            ap1.paintVLine(b.getBarHCoords()[0],step=2,color=(255,0,0))
            ap1.paintVLine(b.getBarHCoords()[1],step=2,color=(255,0,0))
            ap1.writeImage('bar-{0:03d}.png'.format(j))
        nu.savetxt('/tmp/s.txt',nu.array(bf).astype(nu.int),fmt='%d')
        nu.savetxt('/tmp/est.txt',nu.array(est).astype(nu.int),fmt='%d')
        return agents

    @getter
    def getBars(self):
        bars = [Bar(self,x) for x in self.getBarLines()]
        print('bars',len(bars))
        for b in bars:
            pass #print(b.getNeighbourhood())
        bars = [x for x in bars if x.getNeighbourhood() != None
                and x.checkStaffLines() > 50]
        print('bars nonempty neighbourhood',len(bars))
        return bars

    def getSystemWidth(self):
        # this gets cut off from the width, to fit in the page rotated
        cutOff = nu.abs(self.getSystemHeight()*nu.tan(nu.pi*self.getStaffAngle()))
        systemWidth = self.scrImage.getWidth()/nu.cos(nu.pi*self.getStaffAngle()) - 2*cutOff
        systemWidth = int((nu.floor(systemWidth/2.0)-1)*2+1)
        return systemWidth

    def getSystemHeight(self):
        return self.getLowerLeft()[0]-self.getUpperLeft()[0]
        
    @getter
    def getRotator(self):
        return Rotator(self.getStaffAngle(),self.getLowerMid(),self.getLowerMidLocal())

    @getter
    def getCorrectedImgSegment(self):
        halfSystemWidth = int((self.getSystemWidth()-1)/2)
        r = self.getRotator()
        #xx,yy = nu.mgrid[0:self.getSystemHeight(),-halfSystemWidth:halfSystemWidth]
        xx,yy = nu.mgrid[0:self.getSystemHeight(),-halfSystemWidth:halfSystemWidth]
        yy += self.getLowerMidLocal()[1]
        xxr,yyr = r.derotate(xx,yy)
        return getAntiAliasedImg(self.scrImage.getImg(),xxr,yyr)

if __name__ == '__main__':
    pass

