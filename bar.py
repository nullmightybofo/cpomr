#!/usr/bin/env python

import sys
import numpy as nu
from itertools import chain
from utilities import getter
from imageUtil import getAntiAliasedImg
from utils import Rotator

def getVCenterOfBarline(bimg,kRange):
    """
    This function finds the vertical center of bar lines, by
    computing the product of the upper and lower half around
    the hypothetical center. When the hypothetical center is 
    correct, the product will be maximal/minimal (depending on
    the semantics of the color values).
    """
    N,M = bimg.shape
    kMin = int(N*(1-kRange)/2.0)
    kMax = int(N*(1+kRange)/2.0)
    scores = []
    krng = range(kMin,kMax+1)
    for k in krng:
        w = min(k,N-k-1)
        scores.append(nu.sum(((bimg[k-w:k,:]-127)*(bimg[k+w:k:-1,:]-127)))/w)
    return krng[nu.argmin(scores)]

class Bar(object):
    def __init__(self,system,agent):
        self.agent = agent
        self.system = system

        # proportion of the system img segment height that the
        # barline maybe shifted vertically to find the best fit
        self.kRange = .1
        self.widthFactor = 4 # neighbourhood is widthFactor times barlineWidth wide
        self.heightFactor = 1.2 # neighbourhood is heightFactor times systemHeight high

    @getter
    def getFeatureIdx(self):
        w = self.agent.getLineWidth()
        h1,h2 = self.getBarHCoords()
        h0 = int(nu.round(h1-w))
        h3 = int(nu.round(h2+w))
        staffTops = self.getVerticalStaffLinePositions()
        staffBots = staffTops+self.system.getStaffLineWidth()
        staffTops = nu.round(staffTops).astype(nu.int)
        staffBots = nu.round(staffBots).astype(nu.int)
        staffIdx = nu.array([x for x in 
                             chain.from_iterable([range(staffTops[i],staffBots[i]) 
                                                  for i in range(len(staffTops))])])
        interStaffIdx0 = nu.array([x for x in 
                                   chain.from_iterable([range(staffBots[i],staffTops[i+1]) 
                                                        for i in range(4)])])
        interStaffIdx1 = nu.array([x for x in 
                                   chain.from_iterable([range(staffBots[i],staffTops[i+1]) 
                                                        for i in range(5,8)])])
        interStaffIdx = nu.append(interStaffIdx0,interStaffIdx1)
        return {'h0':h0,'h1':h1,'h2':h2,'h3':h3,
                'staffTops':staffTops,'staffBots':staffBots,
                'staff':staffIdx,'interStaff':interStaffIdx}

    def checkStaffLines(self):
        """Return the max staff line blackness on both sides of the bar,
        after subtracting the blackness above and below the staff lines.
        This yields low values for lines that are not on a staff (e.g. the accolade)
        """
        h0 = self.getFeatureIdx()['h0']
        h1 = self.getFeatureIdx()['h1']
        h2 = self.getFeatureIdx()['h2']
        h3 = self.getFeatureIdx()['h3']
        staffTops = self.getFeatureIdx()['staffTops']
        staffBots = self.getFeatureIdx()['staffBots']
        staffIdx = self.getFeatureIdx()['staff']
        w = int(nu.ceil(self.system.getStaffLineWidth()))
        aboveStaffIdx = nu.array([x for x in 
                                   chain.from_iterable([range(staffTops[i]-w,staffTops[i]) 
                                                        for i in range(len(staffTops))])])
        belowStaffIdx = nu.array([x for x in 
                                   chain.from_iterable([range(staffBots[i],staffBots[i]+w) 
                                                        for i in range(len(staffTops))])])
        interStaffIdx = self.getFeatureIdx()['interStaff']
        nh = self.getNeighbourhood()
        staffLeft = nu.mean(nh[staffIdx,h0:h1])
        staffRight = nu.mean(nh[staffIdx,h2:h3])

        aboveStaffLeft = nu.mean(nh[aboveStaffIdx,h0:h1])
        belowStaffLeft = nu.mean(nh[belowStaffIdx,h0:h1])
        staffLeft = nu.mean(nh[staffIdx,h0:h1])
        aboveStaffRight = nu.mean(nh[aboveStaffIdx,h2:h3])
        belowStaffRight = nu.mean(nh[belowStaffIdx,h2:h3])
        staffRight = nu.mean(nh[staffIdx,h2:h3])
        print('sl',staffLeft,aboveStaffLeft,belowStaffLeft)
        print('sr',staffRight,aboveStaffRight,belowStaffRight)
        print('r',max(staffLeft-max(aboveStaffLeft,belowStaffLeft),
                      staffRight-max(aboveStaffRight,belowStaffRight)))
        return max(staffLeft-max(aboveStaffLeft,belowStaffLeft),
                   staffRight-max(aboveStaffRight,belowStaffRight))

    @getter
    def getFeatures(self):
        sd = int(nu.round(self.system.getStaffLineDistance()))
        h0 = self.getFeatureIdx()['h0']
        h1 = self.getFeatureIdx()['h1']
        h2 = self.getFeatureIdx()['h2']
        h3 = self.getFeatureIdx()['h3']
        staffTops = self.getFeatureIdx()['staffTops']
        staffBots = self.getFeatureIdx()['staffBots']
        staffIdx = self.getFeatureIdx()['staff']
        interStaffIdx = self.getFeatureIdx()['interStaff']
        nh = self.getNeighbourhood()
        
        barStaff0 = nu.mean(nh[staffTops[0]:staffBots[4],h1:h2])
        barStaff1 = nu.mean(nh[staffTops[5]:staffBots[9],h1:h2])
        interStaff = nu.mean(nh[staffBots[4]:staffTops[5],h1:h2])
        aboveBar = nu.mean(nh[staffTops[0]-sd:staffTops[0],h1:h2])
        belowBar = nu.mean(nh[staffBots[9]:staffBots[9]+sd,h1:h2])
        if nu.isnan(aboveBar):
            aboveBar = 255.
        if nu.isnan(belowBar):
            belowBar = 255.
        staffLeft = nu.mean(nh[staffIdx,h0:h1])
        staffRight = nu.mean(nh[staffIdx,h2:h3])
        interStaffLeft = nu.mean(nh[interStaffIdx,h0:h1])
        interStaffRight = nu.mean(nh[interStaffIdx,h2:h3])
        print('bar upper staff',barStaff0)
        print('bar lower staff',barStaff1)
        print('above bar',aboveBar)
        print('below bar',belowBar)
        #print('si',staffIdx)
        #print('isi',interStaffIdx)
        print('inter staffline',interStaff)
        print('mean staffline left from staffs',staffLeft)
        print('mean staffline right from staffs',staffRight)
        print('mean interstaffline left from staffs',interStaffLeft)
        print('mean interstaffline right from staffs',interStaffRight)
        return (barStaff0,barStaff1,aboveBar,belowBar,staffLeft,staffRight,interStaffLeft,interStaffRight,interStaff)

    # todo:
    # * staff border detection: take larger margins around bar to look for absent stafflines at one side
    # * bars that are close: adapt margins to avoid interference?
    # * take apart wider bars: redo bar detection to separate double bars?
    # * increase impact of white in barStaff0 and barStaff1
    

    @getter
    def getEstimates(self):
        return nu.array((self.getBarEstimate(),self.getLeftMostBarEstimate(),self.getRightMostBarEstimate()))

    @getter
    def getBarEstimate(self):
        f = self.getFeatures()
        black = (f[0]+f[1]+f[5]+f[4])/(4.*255)
        white = (f[2]+f[3]+f[6]+f[7])/(4.*255)
        return black-white

    @getter
    def getLeftMostBarEstimate(self):
        f = self.getFeatures()
        white = f[4]/255.
        return 1-white

    @getter
    def getRightMostBarEstimate(self):
        f = self.getFeatures()
        white = f[5]/255.
        return 1-white
        
        
    @getter
    def getBarHCoords(self):
        b,e = (nu.array((-.5,.5))+self.widthFactor/2.0)*self.agent.getLineWidth()
        return nu.array((nu.floor(b),nu.ceil(e))).astype(nu.int)

    @getter
    def getVerticalStaffLinePositions(self):
        # approximate system top and bottom (based on global staff detection)
        system0Top = self.system.getRotator().rotate(self.system.staffs[0].staffLineAgents[0].getDrawMean().reshape((1,2)))[0,0]
        system1Bot = self.system.getRotator().rotate(self.system.staffs[1].staffLineAgents[-1].getDrawMean().reshape((1,2)))[0,0]
        sysHeight = (system1Bot-system0Top)
        hhalf = int(sysHeight*self.heightFactor/2.)
        sld = self.system.staffs[0].getStaffLineDistance()
        krng = range(-int(nu.ceil(.5*sld)),int(nu.ceil(.5*sld)))
        hsums = nu.sum(self.getNeighbourhood(),1)
        hslw = int(nu.floor(.5*self.system.getStaffLineWidth()))

        inStaff = nu.arange(nu.round(self.system.getStaffLineWidth()))

        staff0Tops = hhalf-.5*sysHeight-hslw+nu.arange(5)*sld
        staff1Tops = hhalf+.5*sysHeight-hslw-nu.arange(4,-1,-1)*sld
        staff0Rows = nu.round(nu.array([s+inStaff for s in staff0Tops]).flat[:]).astype(nu.int)
        staff1Rows = nu.round(nu.array([s+inStaff for s in staff1Tops]).flat[:]).astype(nu.int)
        f0 = krng[nu.argmax([nu.sum(hsums[staff0Rows+k]) for k in krng])]
        f1 = krng[nu.argmax([nu.sum(hsums[staff1Rows+k]) for k in krng])]
        return nu.append(staff0Tops+f0,staff1Tops+f1)

    @getter
    def getNeighbourhood(self):

        # approximate system top and bottom (based on global staff detection)
        system0Top = self.system.getRotator().rotate(self.system.staffs[0].staffLineAgents[0].getDrawMean().reshape((1,2)))[0,0]
        system1Bot = self.system.getRotator().rotate(self.system.staffs[1].staffLineAgents[-1].getDrawMean().reshape((1,2)))[0,0]
        sysHeight = (system1Bot-system0Top)
        print(system0Top)
        print(system1Bot)
        whalf = int(self.agent.getLineWidth()*self.widthFactor/2.)
        hhalf = int(sysHeight*self.heightFactor/2.)

        yTop = self.agent.getDrawMean()[1]+(system0Top-self.agent.getDrawMean()[0])*nu.cos(nu.pi*self.agent.getAngle())
        yBot = self.agent.getDrawMean()[1]+(system1Bot-self.agent.getDrawMean()[0])*nu.cos(nu.pi*self.agent.getAngle())
        middle = (nu.array((system0Top,yTop))+nu.array((system1Bot,yBot)))/2.0
        r = Rotator(self.agent.getAngle()-.5,middle,nu.array((0,0.)))
        xx,yy = nu.mgrid[-hhalf:hhalf,-whalf:whalf]
        xxr,yyr = r.derotate(xx,yy)
        # check if derotated neighbourhood is inside image
        minx,maxx,miny,maxy = nu.min(xxr),nu.max(xxr),nu.min(yyr),nu.max(yyr)
        M,N = self.system.getCorrectedImgSegment().shape
        #print('w,h',middle)
        #print('mm',minx,maxx,M,miny,maxy,N)
        if minx < 0 or miny < 0 or maxx >= M or maxy >= N:
            return None

        cimg = getAntiAliasedImg(self.system.getCorrectedImgSegment(),xxr,yyr)
        vCorrection = getVCenterOfBarline(cimg,self.kRange)-hhalf
        # TODO: check if barneighbourhood is inside corrected system segment
        cimg = getAntiAliasedImg(self.system.getCorrectedImgSegment(),xxr+vCorrection,yyr)
        print(cimg.shape)
        return cimg
    

if __name__ == '__main__':
    pass
