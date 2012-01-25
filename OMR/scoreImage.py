#!/usr/bin/env python

import sys,os, pickle, logging
import numpy as nu
from utilities import cachedProperty, getter
from imageUtil import writeImageData, getPattern, findValleys, smooth, normalize
from scipy.stats import distributions

from agentPainter import AgentPainter
from verticalSegment import VerticalSegment, identifyNonStaffSegments
from system import System
from staff import Staff
from bar import RightBarLine,LeftBarLine,Bar
from itertools import chain

class ScoreImage(object):
    def __init__(self,fn):
        self.log = logging.getLogger(__name__)
        self.fn = fn
        self.typicalNrOfSystemPerPage = 6
        self.maxAngle = 1.5/180.
        self.nAnglebins = 600
        self.colGroups = 11
        self.bgThreshold = 20

    @cachedProperty
    def ap(self):
        return AgentPainter(self.getImg())

    @getter
    def getImg(self):
        self.log.info('Loading image: {0}'.format(self.fn))
        try:
            img = 255-getPattern(self.fn,False,False)
        except IOError as e: 
            self.log.error('Problem loading image...')
            raise e
        return self.preprocessImage(img)

    def preprocessImage(self,img):
        imin,imax = nu.min(img),nu.max(img)
        istd = nu.std(img)
        imed = nu.median(img)
        minImageHeight = 1500
        minImageWidth = minImageHeight*.75
        if img.shape[1] < minImageWidth:
            self.log.warn('Image resolution may be too low for accurate OMR, recognition may be slow')
            self.log.warn('For good results, provide images with a width of at least {0} pixels'.format(int(minImageWidth)))
        if istd == 0:
            self.log.warn('Blank image')

        if imed > imin+(imax-imin)/2.:
            self.log.warn('Image appears inverted, Inverting image')
            img = 255-img
        self.log.info('White-thresholding image (threshold: {0:.1f} %)'.format(100*self.bgThreshold/255.))
        img[img< self.bgThreshold] = 0
        return img

    def getWidth(self):
        return self.getImg().shape[1]
    def getHeight(self):
        return self.getImg().shape[0]

    def selectStaffs(self,staffs):
        # staffs get selected if their avg staffline distance (ASD) is
        # larger than thresholdPropOfMax times the largest ASD over all staffs

        maxStaffLineDistDev = .05
        slDists = nu.array([staff.getStaffLineDistance() for staff in staffs])
        #log.info('avg staff line distance per staff:')
        # take the largest avg staff distance as the standard,
        # this discards mini staffs
        medDist = nu.median(slDists)
        staffs = [staff for staff in staffs if
                  nu.sum([nu.abs(x-medDist) for x in 
                          staff.getStaffLineDistances()])/(medDist*5) < maxStaffLineDistDev]
        origNrStaffs = len(staffs)

        self.log.info('Selecting {0} staffs from candidate list, discarding {1} staff(s)'.format(len(staffs),
                                                                                         origNrStaffs-len(staffs)))
        return staffs

    @getter
    def getStaffs(self):
        draw = False
        staffs = []

        for i,vs in enumerate(self.getStaffSegments()):
            self.ap.paintHLine(vs.bottom)
            x = nu.arange(vs.top,vs.bottom)
            #self.ap.paintRav(nu.column_stack((x,i*2*nu.ones(len(x)))),color=(10,10,10))
            self.log.info('Processing staff segment {0}'.format(i))
            #vs.draw = i==2
            staffs.extend([Staff(self,s,vs.top,vs.bottom) for s in vs.staffLines])

        staffs = self.selectStaffs(staffs)

        if len(staffs)%2 != 0:
            self.log.warn('Detected unequal number of staffs for file:\n\t{0}'.format(self.fn))
            self.log.info('TODO: retry to find an equal number of staffs')

        if draw:
            for staff in staffs:
                #self.log.info(staff)
                staff.draw()
            #self.ap.drawText('Maarten Grachten',pos=(230,200),size=30)
            self.ap.writeImage('tst.png')
            self.ap.reset()

        return staffs

    @cachedProperty
    def systems(self):
        staffs = self.getStaffs()
        assert len(staffs)%2 == 0
        return [System(self,(staffs[i],staffs[i+1]),i/2) for i in range(0,len(staffs),2)]

    def drawImage(self):
        # draw segment boundaries
        for i,vs in enumerate(self.getVSegments()):
            self.ap.paintHLine(vs.bottom,step=2)

        for vs in self.getNonStaffSegments():
            for j in range(vs.top,vs.bottom,4):
                self.ap.paintHLine(j,alpha=0.9,step=4)
                
        sysSegs = []
        k=0
        barCandidates = []
        acc = {}
        fn = os.path.splitext(os.path.basename(self.fn))[0]

        for system in self.systems:
            self.log.info('Drawing system {0}'.format(system.n))
            system.barLines()
        #with open('/tmp/{0}-acc.dat'.format(fn),'w') as f:
        #    pickle.dump(acc,f)
        if True:
            return True

        shapes = nu.array([ss.shape for ss in sysSegs])
        ssH = nu.sum(shapes[:,0])
        ssW = nu.max(shapes[:,1])
        ssImg = nu.zeros((ssH,ssW),nu.uint8)
        x0 = 0
        for ss in sysSegs:
            h,w = ss.shape
            horzOffset = 0#int(nu.floor((ssW-w)/2.))
            ssImg[x0:x0+h,horzOffset:horzOffset+w] = ss
            x0 += h
        ap1 = AgentPainter(ssImg)
        ap1.writeImage(self.fn.replace('.png','-corr.png'))

    @cachedProperty
    def bars(self):
        """
        Return bars
        """
        bars = []
        bl = [bl for system in self.systems for bl in system.barLines]
        N = len(bl)
        i1 = 0
        i2 = 1
        print(len(bl))
        while i2 < N:
            print(i1,i2)
            if (bl[i1].estimatedType != RightBarLine and
                bl[i2].estimatedType != LeftBarLine):
                print('bar',i1,i2)
                bars.append(Bar(bl[i1],bl[i2]))
                i1 = i2
                i2 += 1
            else:
                if bl[i1].estimatedType == RightBarLine:
                    i1 += 1
                i2 += 1

            #if bl[i1].estimatedType == RightBarLine or bl[i2].estimatedType != LeftBarLine:
            #    i1 += 1
            #elif bl[i2].estimatedType == LeftBarLine:
            #    i2 += 1
            #elif bl[i1].estimatedType == RightBarLine:
            #    i1 += 1
            #    i2 += 1

        print(len(bars))
        for b in bars:
            bb = b.getBBs()
            self.ap.paintLineSegment(bb[0,:],bb[1,:],color=(200,10,50),alpha=0.9)
        self.ap.writeImage('tst.png')
        return bars

    @cachedProperty
    def hSums(self):
        return nu.sum(self.getImg(),1)

    @getter
    def getVSegments(self):
        K = int(self.getHeight()/(2*self.typicalNrOfSystemPerPage))+1
        sh = smooth(self.hSums,K)
        #nu.savetxt('/tmp/vh1.txt',nu.column_stack((self.hSums,sh)))
        segBoundaries = nu.append(0,nu.append(findValleys(sh),self.getHeight()))
        vsegments = []
        for i in range(len(segBoundaries)-1):
            vsegments.append(VerticalSegment(self,segBoundaries[i],segBoundaries[i+1],
                                             colGroups = self.colGroups,
                                             maxAngle = self.maxAngle,
                                             nAngleBins = self.nAnglebins))
        nonStaff = identifyNonStaffSegments(vsegments,self.getHeight(),self.getWidth())
        for i in nonStaff:
            vsegments[i].flagNonStaff()
        return vsegments

    def getNonStaffSegments(self):
        return [vs for vs in self.getVSegments() if not vs.hasStaff()]

    def getStaffSegments(self):
        return [vs for vs in self.getVSegments() if vs.hasStaff()]
        #d = partition(lambda x: x.hasStaff(),self.getVSegments())
        #return d[True], d[False]

    @getter    
    def getWeights(self):
        globalAngleHist = smooth(nu.sum(nu.array([s.angleHistogram for s 
                                                  in self.getVSegments()]),0),50)
        angles = nu.linspace(-self.maxAngle,self.maxAngle,self.nAnglebins+1)[:-1] +\
            (float(self.maxAngle)/self.nAnglebins)

        amax = angles[nu.argmax(globalAngleHist)]
        return distributions.norm(amax,.5/180.0).pdf(angles)


if __name__ == '__main__':
    pass
