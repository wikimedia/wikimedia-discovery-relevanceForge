#!/usr/bin/env python

# edf.py - Generate an piecewise linear approximation for an empirical
# distribution function
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
# You should have received a copy of the GNU General Public License along
# with this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301, USA.
# http://www.gnu.org/copyleft/gpl.html

from __future__ import division

import argparse
import numpy as np
import sys

# Segment access constants
# segments tuples are this point (x, y) + slope from previous point
XCOORD = 0
YCOORD = 1
SLOPE = 2


def rmse(predictions, targets):
    predictions = np.array(predictions)
    targets = np.array(targets)
    errors = (predictions - targets) ** 2
    maxerr = np.max(errors)
    maxidx = np.where(errors == maxerr)[0][0]
    return [maxidx, np.sqrt(errors.mean())]


def estimate(x, segments):
    if x < segments[0][XCOORD]:
        return segments[0][YCOORD]
    for i in xrange(1, len(segments)):
        if x < segments[i][XCOORD]:
            return segments[i-1][YCOORD] + (x - segments[i-1][XCOORD]) * segments[i][SLOPE]
    return segments[-1][YCOORD]


def print_signum_latex(segments):
    print "=============\nLaTeX/Desmos signum (not simplified)\n-------------"
    sys.stdout.write("\\frac{{(1-\\operatorname{{signum}}(x-{}))}}{{2}}*{}".format(
        segments[0][XCOORD], segments[0][YCOORD]))
    for i in xrange(1, len(segments)):
        m, e = np.frexp(segments[i][SLOPE])
        sys.stdout.write("+\\frac{{(\\operatorname{{signum}}" +
                         "(x-{})+1)".format(segments[i-1][XCOORD]) +
                         "(1-\\operatorname{{signum}}(x-{}))}}{{4}}".format(segments[i][XCOORD]) +
                         "*({}+(x-{})*{}\\cdot 2^{{{}}})".format(segments[i-1][YCOORD],
                                                                 segments[i-1][XCOORD], m, e))
    print "+\\frac{{(\\operatorname{{signum}}(x-{})+1)}}{{2}}*{}".format(segments[-1][XCOORD],
                                                                         segments[-1][YCOORD])


def main():
    parser = argparse.ArgumentParser(
        description="Generate a piecewise linear model of an empirical distribution function",
        prog=sys.argv[0]
        )
    parser.add_argument("file", nargs=1, help="file with numerical input data")
    parser.add_argument("-s", "--segments", dest="max_segcount", default=20, type=int,
                        help="number of linear segments to use, default is 20")
    parser.add_argument("-e", "--error", dest="min_error", default=0, type=float,
                        help="stop if RMSE error is below this level, default is 0")
    parser.add_argument("-m", "--maxerror", dest="min_max_error", default=1, type=float,
                        help="stop if max error is below this level, default is 1 " +
                        "(i.e., max_error doesn't prevent stopping)")
    parser.add_argument("-d", "--desmos", dest="desmos", action='store_true', default=False,
                        help="output Desmos-compatible table and piecewise LaTeX")
    parser.add_argument("-py", "--python", dest="python", action='store_true', default=False,
                        help="output Python data structures and custom function")
    parser.add_argument("-sig", "--signum", dest="signum", action='store_true', default=False,
                        help="output signum-based custom functions")
    parser.add_argument("-v", "--verbose", dest="verbose", action='store_true', default=False,
                        help="give verbose output while running")
    parser.add_argument("-q", "--quiet", dest="quiet", action='store_true', default=False,
                        help="suppress all intermediate output")
    args = parser.parse_args()

    file = args.file[0]
    data = [int(line.strip()) for line in open(file, 'r')]

    max_segcount = args.max_segcount
    min_error = args.min_error
    min_max_error = args.min_max_error

    data.sort()
    data = np.array(data)
    min = np.min(data)
    max = np.max(data)
    count = len(data)

    if args.verbose and not args.quiet:
        print "min: {}\nmax: {}\ncount: {}\n".format(min, max, count)
        print "mean: {}\ns.d. {}\nmedian: {}\n".format(np.mean(data),
                                                       np.std(data), np.median(data))

    targets = np.arange(0, 1+1/(count-1), 1/(count-1))
    for x in xrange(1, len(targets)):
        if data[x] == data[x-1]:
            targets[x] = targets[x-1]

    segments = [[min, 0, 0], [max, 1, 1/(max-min)]]

    segcount = 0

    predictions = [estimate(x, segments) for x in data]
    # print "predictions: {}\n{}".format(len(predictions), predictions)

    myRMSE = 0
    maxerr_idx = 0
    max_error = 0

    while segcount < max_segcount:
        segcount += 1

        maxerr_idx, myRMSE = rmse(predictions, targets)
        pred = estimate(data[maxerr_idx], segments)
        max_error = pred-targets[maxerr_idx]

        if not args.quiet:
            print "==============\nsegments: {}".format(segcount)
            if args.verbose:
                print segments
                print "\tpoorest point:"
                print "\t\ttarget : [{0:}, {1:}]\n\t\tpredict: [{0:}, {2:}]".format(
                    data[maxerr_idx], targets[maxerr_idx], pred)
            print "\tRMSE: {}".format(myRMSE)
            print "\tmax err: {}\n".format(max_error)

        if myRMSE <= min_error and abs(max_error) < min_max_error:
            break

        if segcount < max_segcount:
            segments.append([data[maxerr_idx], targets[maxerr_idx], 0])
            segments.sort(key=lambda tup: tup[YCOORD])
            new_seg_idx = [y[0] for y in segments].index(data[maxerr_idx])
            for i in xrange(new_seg_idx, new_seg_idx+2):
                segments[i][SLOPE] = (segments[i][YCOORD]-segments[i-1][YCOORD]) / \
                    (segments[i][XCOORD]-segments[i-1][XCOORD])
            lo = np.where(data == segments[new_seg_idx-1][XCOORD])[0][0]
            hi = np.where(data == segments[new_seg_idx+1][XCOORD])[0][0]
            predictions[lo:hi] = [estimate(x, segments) for x in data[lo:hi]]

    print "{}-segment results: RMSE {}; max_error {}".format(max_segcount, myRMSE, max_error)

    if args.desmos:
        print "\nDESMOS OUTPUT"
        print "=============\ntable\n-------------"
        print "x\ty"
        for s in segments:
            print s[XCOORD], "\t", s[YCOORD]
        print_signum_latex(segments)
        print "=============\nLaTeX/Desmos (in pieces)\n-------------"
        print "{}\\ \\left\\{{x\le{}\\right\\}}".format(segments[0][YCOORD], segments[0][XCOORD])
        for i in xrange(1, len(segments)):
            m, e = np.frexp(segments[i][SLOPE])
            print "{}\\ +\\ ".format(segments[i-1][YCOORD]) + \
                "\\left(x-{}\\right)\\cdot ".format(segments[i-1][XCOORD]) + \
                "{}\cdot 2^{{{}}}\\ ".format(m, e) + \
                "\\left\\{{{}<x\le{}\\right\\}}".format(segments[i-1][XCOORD], segments[i][XCOORD])
        print "{}\\ \\left\\{{x>{}\\right\\}}".format(segments[-1][YCOORD], segments[-1][XCOORD])
        print "============="

    if args.python:
        print "\nPYTHON OUTPUT"
        print "=============\ngeneric function + segments\n-------------"
        print """# segments tuples are this point (x, y) + slope from previous point
XCOORD = 0
YCOORD = 1
SLOPE = 2

def estimate(x, segments):
    if x < segments[0][XCOORD]:
        return segments[0][YCOORD]
    for i in xrange(1, len(segments)):
        if x < segments[i][XCOORD]:
            return segments[i-1][YCOORD] + (x - segments[i-1][XCOORD]) * segments[i][SLOPE]
    return segments[-1][YCOORD]"""

        print "\n# training data: RMSE {}; max_error {}".format(myRMSE, max_error)
        print "segments =", segments
        print "=============\ncustom function\n-------------"
        print "def estimate(x):"
        print "\t# training data: RMSE {}; max_error {}".format(myRMSE, max_error)
        print "\t# may be optimized by reversing the order of the cases"
        print "\tif x < {}:\n\t\treturn {}".format(segments[0][XCOORD], segments[0][YCOORD])
        for i in xrange(1, len(segments)):
            print "\tif x < {}:\n\t\treturn {} + (x - {}) * {:.10E}".format(segments[i][XCOORD],
                                                                            segments[i-1][YCOORD],
                                                                            segments[i-1][XCOORD],
                                                                            segments[i][SLOPE])
        print "\treturn {}".format(segments[-1][YCOORD])
        print "============="

    if args.signum:
        # (1 - signum(x-n))/2 ==> {x < n}
        # (signum(x-n) + 1)/2 ==> {n < x}
        # (signum(x-n) + 1)(1 - signum(x-m))/4 ==> {n < x < m}

        print "\nSIGNUM OUTPUT"
        print "=============\ngeneral signum\n-------------"
        print "(1 - signum(x-{}))/2 * {}".format(segments[0][XCOORD], segments[0][YCOORD])
        print "\t+ ("
        for i in xrange(1, len(segments)):
            sys.stdout.write("\t\t")
            if (i != 1):
                sys.stdout.write("+ ")
            print "(signum(x-{}) + 1)(1 - signum(x-{})) * ({} + (x - {}) * {:.10E})".format(
                segments[i-1][XCOORD], segments[i][XCOORD], segments[i-1][YCOORD],
                segments[i-1][XCOORD], segments[i][SLOPE])
        print "\t)/4"
        print "\t+ (signum(x-{}) + 1)/2 * {}".format(segments[-1][XCOORD], segments[-1][YCOORD])
        if (not args.desmos):
            print_signum_latex(segments)
        print "============="


if __name__ == "__main__":
    main()
