#!/usr/bin/env python
import json
import sys
import requests
import csv
import subprocess
import os
import argparse
import re


# metastats.py read cirrus index dumps and export various stats as a csv file
# e.g. dump stats from enwiki
# ./metastats.py -w enwiki -t content -d 20160222 -u en.wikipedia.org > enwikistats.csv
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


def loadBoostTemplates(wiki):
    url = 'https://' + wiki + '/wiki/MediaWiki:Cirrussearch-boost-templates'
    boosts = {}
    txt = requests.get(url, {'action': 'raw'}).text
    for (tmpl, boost) in re.findall('([^|]+)\|(\d+)% ?', txt):
        tmpl = tmpl.replace('_', ' ')
        boosts[tmpl] = int(boost) / 100
    return boosts


def dumpReader(url, callback):
    FNULL = open(os.devnull, 'w')
    p = subprocess.Popen('curl -L ' + url + ' | gzip -cd', shell=True,
                         stdout=subprocess.PIPE, stderr=FNULL)
    l = 0
    for line in p.stdout:
        l += 1
        page = json.loads(line)
        if(l % 2 == 1):
            pageId = page['index']['_id']
            continue
        try:
            int(pageId)
        except ValueError:
            print("*** line:" + str(l) + " is not a valid id : '" + str(pageId) + "'")
            continue

        callback(pageId, page)


def statsExtractor(pageId, page, boostTemplates, csv):
    "Export raw stats"
    boost = 1
    for key, value in boostTemplates.iteritems():
        if key in page['template']:
            boost *= value

    csv.writerow([page['title'].replace("\"", "\"\""),
                 pageId,
                 page['incoming_links'],
                 len(page['external_link']),
                 page['text_bytes'],
                 len(page['heading']),
                 len(page['redirect']),
                 len(page['outgoing_link']),
                 page.get('popularity_score', 0),
                 boost])


def dumpStats(wiki, index, date, wikiurl):
    url = \
        'http://dumps.wikimedia.org/other/cirrussearch/%s/%s-%s-cirrussearch-%s.json.gz' % \
        (date, wiki, date, index)
    csv_output = csv.writer(sys.stdout, quoting=csv.QUOTE_MINIMAL, delimiter=',', escapechar='\\')
    csv_output.writerow(["page", "pageId", "incomingLinks", "externalLinks", "bytes", "headings",
                         "redirects", "outgoing", "pop_score", "tmplBoost"])
    boostTemplates = loadBoostTemplates(wikiurl)

    def extract(pageId, page):
        statsExtractor(pageId, page, boostTemplates, csv_output)

    dumpReader(url, extract)


reload(sys)
sys.setdefaultencoding('utf-8')

aparser = argparse.ArgumentParser(description='Cirrus index metadata stats dump', prog=sys.argv[0])
aparser.add_argument('-w', '--wiki', help='The wiki (e.g. enwiki, trwikibooks)', required=True)
aparser.add_argument('-t', '--type', help='The index type (content, general, file)', required=True)
aparser.add_argument('-d', '--date', help='The dump date (e.g. 20160222)', required=True)
aparser.add_argument('-u', '--wikiurl',
                     help='The wikiurl to read boost templates config (e.g. en.wikipedia.org)',
                     required=True)

args = aparser.parse_args()

dumpStats(args.wiki, args.type, args.date, args.wikiurl)
