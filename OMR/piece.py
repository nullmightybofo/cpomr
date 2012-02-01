#!/usr/bin/env python

import sys,os, pickle, logging
import bar
import numpy as nu
from utilities import cachedProperty
from multiprocessing import Pool
from utilities import FakePool
from scoreImage import ScoreImage

# all this KeyboardInterrupt stuff is a workaround of bug
# http://bugs.python.org/issue8296

class KeyboardInterruptError(Exception): pass

def processPage(imgFile):
    try:
        si = ScoreImage(imgFile)
        si.bars
        return si
    except KeyboardInterrupt:
        raise KeyboardInterruptError()

pool = Pool()

class Piece(object):
    def __init__(self,imgFiles):
        self.imgFiles = imgFiles
    
    @cachedProperty
    def imgs(self):
        log = logging.getLogger(__name__)
        imgs = []
        try:
            imgs = pool.map(processPage,self.imgFiles)
        except KeyboardInterrupt:
            log.info('Got ^C while pool mapping, terminating the pool')
            pool.terminate()
            log.info('Pool is terminated')
            log.info('Joining pool processes')
            pool.close()
            pool.join()
            log.info('Join complete')
        except Exception, e:
            log.info('Got exception: %r, terminating the pool' % (e,))
            pool.terminate()
            log.info('Pool is terminated')
            log.info('Joining pool processes')
            pool.close()
            pool.join()
            log.info('Join complete')
        return imgs

    def drawAnnotatedScores(self,outputDir):
        bar_i = 1
        for img in self.imgs:
            # this draws the annotations on the internally
            # stored image
            img.drawAnnotatedScore(bar_i)
            # this writes the internally stored image to a file
            img.ap.writeImage(os.path.join(outputDir,img.filenameBase+'.png'),absolute=True)
            bar_i += len(img.bars)

    @cachedProperty
    def barCoordinates(self):
        bar_i = 0
        bb = []
        for j,img in enumerate(self.imgs):
            bb.extend([[j,bar_i+i]+list(bar.boundingBoxes) for i,bar in enumerate(img.bars)])
            bar_i += len(img.bars)
        return bb

    def writeBarCoordinates(self,outputDir):
        cpfx = os.path.commonprefix([x.filenameBase for x in self.imgs])
        fname = ''.join([cpfx, '-' if len(cpfx) > 0 else '', 'barBoundingBoxes.txt'])
        fname = os.path.join(outputDir,fname)
        log = logging.getLogger(__name__)
        try:
            log.info('Writing bar bounding boxes to file {0}'.format(fname))
            with open(fname,'w') as f:
                f.write('# pageNr barNr (topLeft_v topLeft_h botRight_v botRight_h)+')
                for line in self.barCoordinates:
                    f.write(' '.join(['{0:d}'.format(x) for x in line])+'\n')
        except OSError:
            log.error('Cannot write to file {0}'.format(fname))

if __name__ == '__main__':
    pass
