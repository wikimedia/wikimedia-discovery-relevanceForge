#!/usr/bin/env python

# jsondiff.py - an almost smart enough JSON diff tool
#
# This program does line-by-line diffs of two files with one JSON blob
# per line, outputting one color-coded HTML diff per line into a target
# directory. It performs a text diff on alphabetized, pretty printed
# JSON. That's good enough for JSON blobs that have similar structure,
# or dissimilar values (arrays of single digit numbers, for example, can
# cause confusion, because one 7 looks like every other 7).
#
# A smarter (future) version would intelligently diff the structure of
# the JSON, but the goal here was to put something reasonable together
# as quickly as possible.
#
# It has a number of hacks specific to diffing JSON from CirrusSearch
# results, including removing "searchmatch" markup and bolding elements
# that are most important in comparing results, and numbering results.
#
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301, USA.
# http://www.gnu.org/copyleft/gpl.html

import argparse
import difflib
import json
import os
import re
import sys
from itertools import izip_longest


def add_nums_to_results(results):
    res_count = 1
    if 'rows' in results:
        for result in results['rows']:
            result['relLabItemNumber'] = res_count
            res_count += 1
    return results


def munge_explanation(results):
    if 'rows' not in results:
        return {}
    for result in results['rows']:
        if 'explanation' not in result:
            continue
        explanation = result['explanation']
        del result['explanation']
        result['|scores'] = {
            '1.main': get_main_score(explanation),
            '2.primary': get_primary_score(explanation),
            '3.phrase': get_phrase_score(explanation),
            '4.function': get_function_score(explanation)
        }


def get_main_score(exp):
    return exp['value']


def get_primary_score(exp):
    if has_phrase_rescore(exp):
        return exp['details'][0]['details'][0]['details'][0]['value']
    else:
        return exp['details'][0]['value']


def get_phrase_score(exp):
    if has_phrase_rescore(exp):
        return exp['details'][0]['details'][0]['details'][1]['value']
    else:
        return "N/A"


def get_function_score(exp):
    return exp['details'][0]['value']


def has_phrase_rescore(exp):
    is_ph = ''
    details3 = exp['details'][0]['details'][0]['details'][1]
    if 'details' in details3 and len(details3['details']) > 1:
        details4 = details3['details'][1]
        if 'description' in details4:
            is_ph = details4['description']
    return is_ph == 'secondaryWeight'


def main():
    parser = argparse.ArgumentParser(description='line-by-line diff of JSON blobs',
                                     prog=sys.argv[0])
    parser.add_argument('file', nargs=2, help='files to diff')
    parser.add_argument('-d', '--dir', dest='dir', default='./diffs/',
                        help='output directory, default is ./diffs/')
    args = parser.parse_args()

    (file1, file2) = args.file
    target_dir = args.dir + '/'

    diff_count = 0

    if not os.path.exists(target_dir):
        os.makedirs(os.path.dirname(target_dir))

    with open(file1) as a, open(file2) as b:
        for tuple in izip_longest(a, b, fillvalue='{}'):
            (aline, bline) = tuple
            aline = aline.strip(' \t\n')
            bline = bline.strip(' \t\n')
            if aline == '':
                aline = '{}'
            if bline == '':
                bline = '{}'
            diff_count += 1
            diff_file = open(target_dir + 'diff' + repr(diff_count) + '.html', 'w')

            # remove searchmatch markup
            aline = re.sub(r'<span class=\\"searchmatch\\">(.*?)<\\/span>',
                           '\\1', aline)
            bline = re.sub(r'<span class=\\"searchmatch\\">(.*?)<\\/span>',
                           '\\1', bline)

            aresults = add_nums_to_results(json.loads(aline))
            bresults = add_nums_to_results(json.loads(bline))

            # munge lucene explanation
            munge_explanation(aresults)
            munge_explanation(bresults)

            aline = json.dumps(aresults, sort_keys=True, indent=2)
            bline = json.dumps(bresults, sort_keys=True, indent=2)
            output = difflib.HtmlDiff(wrapcolumn=50).make_file(aline.splitlines(),
                                                               bline.splitlines(),
                                                               file1, file2)
            # highlight key fields
            output = re.sub(r'("(title|query|totalHits|relLabItemNumber)":&nbsp;.*?)</td>',
                            '<b><font color=#0000aa>\\1</font></b></td>', output)
            diff_file.writelines(output)
            diff_file.close()

if __name__ == "__main__":
    main()
