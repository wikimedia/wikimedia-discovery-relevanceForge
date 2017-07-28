#!/usr/bin/env python

# cqd.py - Cirrus Query Debugger is a small command line tool to display
# various debugging information.
# -.-. --.- -..
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
# import json
import math
import re
import requests
import sys
from termcolor import colored


class CQuery:
    """Represents a cirrus search query"""
    def __init__(self, query, wiki, params):
        self.query = query
        self.params = params
        self.wiki = wiki

    def run(self):
        res = self.fetch().json()
        return CQResultSet(res, self.params.offset)

    def fetch(self):
        if re.search('^https?://', self.wiki):
            base_uri = self.wiki
        else:
            base_uri = 'https://'+self.wiki+'/w/api.php'
        uri_param = dict({
            'action': 'query',
            'list': 'search',
            'cirrusDumpResult': '',
            'cirrusExplain': '',
            'format': 'json',
            'srsearch': self.query,
        })
        self.params.update(uri_param)
        return requests.get(base_uri, uri_param)


class CQueryParams:
    """List of tweak parameters"""
    def __init__(self, args):
        self.limit = args.limit
        self.offset = args.offset
        self.functionWindow = args.functionWindow
        self.phraseWindow = args.phraseWindow
        self.rescoreProfile = args.rescoreProfile
        self.allField = args.allField
        self.custom = args.custom

    def update(self, uri_params):
            uri_params['srlimit'] = self.limit
            uri_params['sroffset'] = self.offset
            if self.functionWindow is not None:
                uri_params['cirrusFunctionWindow'] = self.functionWindow
            if self.phraseWindow is not None:
                uri_params['cirrusPhraseWindow'] = self.phraseWindow
                # TODO: remove back compat param
                uri_params['cirrusPhraseWinwdow'] = self.phraseWindow

            if self.rescoreProfile is not None:
                uri_params['cirrusRescoreProfile'] = self.rescoreProfile

            if self.allField is not None:
                uri_params['cirrusUseAllFields'] = self.allField
            for c in self.custom:
                (param, value) = c.split('=', 2)
                uri_params[param] = value


class CQResultSet:
    """A Cirrus query result set"""
    def __init__(self, res, offset):
        self.desc = res['description']
        res = res['result']
        self.time = res['took']
        self.shards = res['_shards']['total']
        res = res['hits']
        self.total = res['total']
        self.max_score = res['max_score']
        self.hits = list()
        self.shardHits = {}

        rank = offset
        for hit in res['hits']:
            rank += 1
            hit = CQResultHit(rank, hit)
            self.hits.append(hit)
            if hit.shard not in self.shardHits:
                self.shardHits[hit.shard] = 0
            self.shardHits[hit.shard] += 1


class CQResultHit:
    """A single hit"""
    def __init__(self, rank, hit):
        self.rank = rank
        self.shard = hit['_shard']
        self.id = hit['_id']
        self.title = hit['_source']['title']
        self.score = hit['_score']
        self.explanation = None
        if '_explanation' in hit:
            self.explanation = CQExplain.build(hit['_explanation'])

        self.snippet = None
        if 'highlight' in hit and 'text' in hit['highlight']:
            self.snippet = hit['highlight']['text']


class CQPrinter:
    def __init__(self):
        self.out = sys.stdout

    def nl(self):
        self.out.write('\n')

    def w(self, txt, color=None, bg=None):
        txt = str(txt)
        if color is not None:
            if bg is not None:
                txt = colored(txt, color, 'on_'+bg)
            else:
                txt = colored(txt, color, attrs=['bold'])
        self.out.write(txt)


class CQExplainPrinter:
    """Display explain info"""
    def __init__(self, printer=None, level=None, args=None):
        if level is None:
            self.level = 0
        else:
            self.level = level
        self.indentChar = "  "
        if printer is not None:
            self.printer = printer
        else:
            self.printer = CQPrinter()

        self.dismaxFilter = None
        if args is not None:
            if args.dismaxFilter is not None:
                self.dismaxFilter = re.compile(args.dismaxFilter)

    def disp(self, exp, rankScore=None, maxScore=None):
        # we need rankScore because we want to flag
        # the explain node that is responsible for the rankScore
        # This is because explain will re-apply the rescore query
        # and if the doc is normally outside the rescore window
        # during explain it will always be inside the rescore window
        if rankScore is not None:
            self.rankScore = rankScore

        # Flag the max score
        if maxScore is not None:
            self.maxScore = maxScore

        self.indent()
        self.mainScore(exp.score)
        self.append(' = ')
        exp.disp(self)
        self.printer.nl()
        self.descend(exp)

    def append(self, txt, color=None, bg=None):
        self.printer.w(txt, color, bg)
        return self

    def score(self, txt):
        self.printer.w(str(txt), 'cyan')
        return self

    def mainScore(self, txt):
        if self.maxScore is not None and math.fabs(txt - self.maxScore) < 0.0001:
            self.printer.w(str(txt), 'grey', 'green')
            self.maxScore = None
        elif self.rankScore is not None and math.fabs(txt - self.rankScore) < 0.0001:
            self.printer.w(str(txt), 'white', 'blue')
            # found it
            self.rankScore = None
        else:
            if txt > 10:
                self.printer.w(str(txt), 'red')
            elif txt > 1:
                self.printer.w(str(txt), 'yellow')
            else:
                self.printer.w(str(txt), 'white')
        return self

    def term(self, field, term, boost=None):
        self.printer.w(str(field), 'blue')
        self.printer.w(':')
        self.printer.w(term, 'green')
        if boost is not None:
            self.printer.w('^')
            self.score(boost)
        return self

    def operator(self, operator):
        self.printer.w(operator, 'blue')
        return self

    def weight(self, weight):
        self.printer.w(weight, 'cyan')
        return self

    def query(self, query):
        lastO = 0
        for r in re.compile('\\(([^\\(\\)]+)\\)').finditer(query):
            if lastO < r.start(1):
                self.printer.w(query[lastO:r.start(1)])
            self.printer.w(r.group(1), color='magenta')
            lastO = r.end(1)
        if lastO < len(query):
            self.printer.w(query[lastO:])

    def formula(self, formula):
        lastO = 0
        for r in re.compile('doc\\[\'([a-z\\._]+)\'\\]').finditer(formula):
            if lastO < r.start():
                self.printer.w(formula[lastO:r.start(1)])
                self.printer.w(r.group(1), color='magenta')
                lastO += r.end(1)
                self.printer.w(formula[lastO:r.end()])
                lastO = r.end()
            if lastO < len(formula):
                self.printer.w(formula[lastO:])

    def descend(self, exp):
        for child in exp.children:
            if child.filtered(self):
                continue
            self.level += 1
            self.disp(child)
            self.level -= 1

    def indent(self):
        self.printer.w(self.indentChar * self.level)


class CQHitPrinter:
    """Display hit info"""
    def __init__(self, args=None):
        self.level = 0
        self.indentChar = "  "
        self.printer = CQPrinter()
        self.explain_printer = CQExplainPrinter(level=1, args=args)
        self.snippet_pattern = re.compile('<span class="searchmatch">([^<]+)</span>')

    def indent(self, lvl=None):
        if lvl is None:
            lvl = self.level
        self.printer.w(self.indentChar * lvl)

    def higlight(self, word):
        self.printer.w(word, 'white')

    def shard(self, num):
        self.printer.w('S' + str(num), 'green')
        return self

    def disp(self, hit, maxScore=None):
        self.printer.w('#')
        self.printer.w(hit.rank, 'white')
        self.printer.w('(')
        self.shard(hit.shard)
        self.printer.w('): ')
        self.printer.w(hit.title, 'blue')
        self.printer.w(' - ')
        self.printer.w(str(hit.score), 'white')
        self.printer.nl()
        if hit.snippet is not None:
            self.indent(1)
            for s in hit.snippet:
                s = s.replace('\n', ' ')
                lastO = 0
                for p in self.snippet_pattern.finditer(s):
                    if p.start() > lastO:
                        self.printer.w(s[lastO:p.start()])
                    self.higlight(p.group(1))
                    lastO = p.end()
                if lastO < len(s):
                    self.printer.w(s[lastO:])
            self.printer.nl()
            self.indent()

        self.explain_printer.disp(hit.explanation, rankScore=hit.score, maxScore=maxScore)
        self.printer.nl()


class CQResultSetPrinter:
    def __init__(self, args=None):
        self.level = 0
        self.indentChar = "  "
        self.printer = CQPrinter()
        self.hitPrinter = CQHitPrinter(args=args)
        self.docFilter = re.compile('.*')
        if args.docFilter is not None:
            self.docFilter = re.compile(args.docFilter, re.IGNORECASE)

    def num(self, num):
        self.printer.w(num, 'white')
        return self

    def score(self, num):
        self.printer.w(num, 'blue')

    def shard(self, num):
        self.printer.w('S' + str(num), 'green')
        return self

    def disp(self, results):
        self.printer.w(results.desc)
        self.printer.nl()
        self.printer.w('Found ')
        self.num(results.total)
        self.printer.w(' hits in ')
        self.num(results.shards)
        self.printer.w(' shards, time: ')
        self.num(results.time)
        self.printer.w('ms (maxScore: ')
        self.score(results.max_score)
        self.printer.w(', shard bal:')
        for k in sorted(results.shardHits, key=results.shardHits.get, reverse=True):
            self.printer.w(' ')
            self.shard(k)
            self.printer.w(':')
            self.num(results.shardHits[k])
        self.printer.w(')')
        self.printer.nl()
        self.printer.nl()

        for h in results.hits:
            if self.docFilter.search(h.title):
                self.hitPrinter.disp(h, maxScore=results.max_score)


class CQExplain:
    @staticmethod
    def build(exp):
        if CQRescoreExp.accept(exp):
            return CQRescoreExp(exp)
        if CQSingleRescoreExp.accept(exp):
            return CQSingleRescoreExp(exp)
        if CQDisMaxExp.accept(exp):
            return CQDisMaxExp(exp)
        if CQTermWeight.accept(exp):
            return CQTermWeight(exp)
        if CQPhraseWeight.accept(exp):
            return CQPhraseWeight(exp)
        if CQBoolWithCoord.accept(exp):
            return CQBoolWithCoord(exp)
        if CQBool.accept(exp):
            return CQBool(exp)
        if CQFilter.accept(exp):
            return CQFilter(exp)
        if CQFunctionScoreChain.accept(exp):
            return CQFunctionScoreChain(exp)
        raise Exception('Unknown explain node :' + exp['description'])

    def __init__(self, exp):
        self.score = exp['value']
        self.desc = exp['description']
        self.children = list()

    def __cmp__(self, other):
        return cmp(self.score, other.score)

    def disp(self, display):
        return

    def filtered(self, display):
        return False


class CQSingleRescoreExp(CQExplain):
    """Unclear..."""

    @staticmethod
    def accept(exp):
        """Can be identified by the presence of product primaryWeight"""

        # always 2 (primary*w) [op] (secondary*w)
        if len(exp['details']) != 2:
            return False

        # must be the product with primaryWeightV
        if exp['description'] != 'product of:':
            return False

        if len(exp['details'][0]['details']) != 2:
            return False

        if exp['details'][1]['description'] != 'primaryWeight':
            return False

        return True

    def __init__(self, exp):
        CQExplain.__init__(self, exp)
        self.children.append(CQExplain.build(exp['details'][0]))
        self.primaryWeigth = exp['details'][1]['value']

    def disp(self, display):
        display.append('RescoreSingle ')
        display.append(' primW=')
        display.weight(self.primaryWeigth)


class CQRescoreExp(CQExplain):
    """Rescore"""

    @staticmethod
    def accept(exp):
        """Can be identified by the presence of product primaryWeight"""

        # always 2 (primary*w) [op] (secondary*w)
        if len(exp['details']) != 2:
            return False

        # must be the product with primaryWeightV
        if exp['details'][0]['description'] != 'product of:':
            return False

        if len(exp['details'][0]['details']) != 2:
            return False

        if exp['details'][0]['details'][1]['description'] != 'primaryWeight':
            return False

        return True

    def __init__(self, exp):
        CQExplain.__init__(self, exp)
        self.children.append(CQExplain.build(exp['details'][0]['details'][0]))
        self.children.append(CQExplain.build(exp['details'][1]['details'][0]))
        self.operator = re.search(r'([^ ]+)', exp['description']).group(1)
        self.primaryWeigth = exp['details'][0]['details'][1]['value']
        self.secondaryWeigth = exp['details'][1]['details'][1]['value']

    def disp(self, display):
        display.append('Rescore ')
        display.operator(self.operator)
        display.append(' primW=')
        display.weight(self.primaryWeigth)
        display.append(' secW=')
        display.weight(self.secondaryWeigth)


class CQBool(CQExplain):
    """Simple boolean"""
    @staticmethod
    def accept(exp):
        # check sum of
        return exp['description'] == 'sum of:'

    def __init__(self, exp):
        CQExplain.__init__(self, exp)
        for cl in exp['details']:
            self.children.append(CQExplain.build(cl))

    def disp(self, display):
        display.append('Bool')


class CQBoolWithCoord(CQBool):
    """Simple boolean with a coord factor"""
    @staticmethod
    def accept(exp):
        # check for the product with coord()
        if exp['description'] == 'product of:'\
                and len(exp['details']) == 2\
                and exp['details'][1]['description'].startswith('coord('):
            return CQBool.accept(exp['details'][0])
        return False

    def __init__(self, exp):
        CQBool.__init__(self, exp['details'][0])
        self.score = exp['value']
        self.coord = exp['details'][1]['value']

    def disp(self, display):
        CQBool.disp(self, display)
        display.append(' coord=')
        display.weight(self.coord)


class CQFunctionScoreChain(CQExplain):
    """Function score used in function rescore window"""
    @staticmethod
    def accept(exp):
        if exp['description'].startswith('function score, '):
            return True
        return False

    def __init__(self, exp):
        CQExplain.__init__(self, exp)
        self.boost = exp['details'][0]['value']
        if len(exp['details']) == 2:
            # empty rescore chain, no match?
            self.scoreMode = 'nomatch?'
            return

        search = re.search('score mode \\[([^\\]]+)\\]',
                           exp['details'][1]['details'][0]['description'])
        if search:
            self.scoreMode = search.group(1)
            # skip the min of with epsilon
            for func in exp['details'][1]['details'][0]['details']:
                self.children.append(self.build_chain(func))
        else:
            # a single function?
            self.scoreMode = '???'
            self.children.append(self.build_chain(exp))

    def disp(self, display):
        display.append('FuncChain ')
        display.append('scoreMode: ')
        display.operator(self.scoreMode)

    def build_chain(self, func):
        if CQFunction.accept(func):
            return CQFunction(func)
        if CQFunctionQuery.accept(func):
            return CQFunctionQuery(func)
        if CQFunctionScore.accept(func):
            return CQFunctionScore(func)
        raise Exception('Unknwon function :' + func['description'])


class CQFunctionScore(CQExplain):
    """Function score query
    NOTE: do not add to CQExplain.build it's in conflict with CQFunctionScoreChain"""

    @staticmethod
    def accept(exp):
        return exp['description'] == 'function score, product of:'

    def __init__(self, exp):
        CQExplain.__init__(self, exp)
        if exp['details'][0]['description'] != 'match filter: *:*':
            self.query = exp['details'][0]['description']

    def disp(self, display):
        display.append('FuncScore ')
        display.append('query: ')
        display.query(self.query)


class CQFunction(CQFunctionScore):
    @staticmethod
    def accept(exp):
        if '*:*' in exp['details'][0]['description'] and\
                "function: " in exp['details'][1]['description']:
            return True

        if '*:*' in exp['details'][0]['description'] and\
                ("Math.min of" in exp['details'][1]['description'] or
                 "product of:" in exp['details'][1]['description']) and\
                "function: " in exp['details'][1]['details'][0]['description']:
            return True
        return False

    def __init__(self, exp):
        CQFunctionScore.__init__(self, exp)
        if exp['details'][1]['description'] == 'product of:' or\
                "Math.min of" in exp['details'][1]['description']:
            self.function = exp['details'][1]['details'][0]['description']
        else:
            self.function = exp['details'][1]['description']

    def disp(self, display):
        display.append('Function :')
        display.formula(self.function)


class CQFunctionQuery(CQFunctionScore):
    @staticmethod
    def accept(exp):
        return 'match filter: *:*' in exp['details'][0]['description']

    def __init__(self, exp):
        CQFunctionScore.__init__(self, exp)
        self.query = exp['details'][0]['description']
        self.weight = exp['details'][1]['details'][1]['value']

    def disp(self, display):
        display.append('FQuery ')
        display.append('weight: ')
        display.weight(self.weight)
        display.append(', query: ')
        display.query(self.query)


class CQDisMaxExp(CQExplain):
    """https://lucene.apache.org/core/4_4_0/core/org/apache/lucene/search/DisjunctionMaxQuery.html

    Generated by QueryString when using multi field (param dis_max, defaults true)
    https://www.elastic.co/guide/en/elasticsearch/reference/current/query-dsl-query-string-query.html#_multi_field
    """

    @staticmethod
    def accept(exp):
        return exp['description'] == 'max of:'

    def __init__(self, exp):
        CQExplain.__init__(self, exp)
        for exp in exp['details']:
            self.children.append(CQExplain.build(exp))
        self.winner = sorted(self.children, reverse=True)[0]

    def disp(self, display):
        display.append('DisMax ')
        display.append('best=')
        display.term(self.winner.field, self.winner.term)


class CQTermWeight(CQExplain):
    @staticmethod
    def accept(exp):
        # Accept everything except phrases
        if re.search('^weight\\([^"]+$', exp['description']):
            return True
        return False

    """TermWeight (core tf/idf sim)"""
    def __init__(self, exp):
        CQExplain.__init__(self, exp)
        # extract field, term and boost from weight(all.plain^0.5:test in 93730) [....
        search = re.search('weight\\(([a-z_\\.]+):([^\\^]+?)(?:\\^([\d\\.]+))? in [\d]+\\) \\[',
                           self.desc)
        if search:
            self.field = search.group(1)
            self.term = search.group(2)
            self.boost = None
            if search.group(3):
                self.boost = float(search.group(3))
        else:
            raise Exception("Cannot parse TermWeight field: " + self.desc)

        # extract queryWeight idf info (inside queryWeight, product of:)
        qW = exp['details'][0]['details'][0]
        self.queryNorm = None
        if len(qW['details']) > 1:
            self.queryNorm = qW['details'][1]['value']

        # extract tf.idf info (inside fieldWeight )
        fW = exp['details'][0]['details'][1]

        self.tf = fW['details'][0]['value']
        self.termFreq = fW['details'][0]['details'][0]['value']

        if fW['details'][1]['description'] != 'idf(), sum of:':
            # raw docFreq for non phrase
            search = re.search('idf\\(docFreq=(\d+), maxDocs=(\d+)\\)',
                               fW['details'][1]['description'])
            if search:
                self.docFreq = int(search.group(1))
                self.maxDocs = int(search.group(2))
            else:
                raise Exception("Cannot parse docFreq in :" + fW['details'][1]['description'])
        self.idf = fW['details'][1]['value']
        self.norm = fW['details'][2]['value']

    def disp(self, display):
        display.append('TFIDF ')
        display.append('term=')
        display.term(self.field, self.term, self.boost)
        display.append(' tf=')
        display.score(self.tf)
        display.append('(freq=')
        display.score(self.termFreq)
        display.append(') ')
        display.append('idf=')
        display.score(self.idf)
        display.append(' qNorm=')
        display.score(self.queryNorm)
        display.append(' fNorm=')
        display.score(self.norm)

    def filtered(self, display):
        if display.dismaxFilter is not None:
            return not display.dismaxFilter.search(self.field)
        return False


class CQFilter(CQExplain):
    """Constant score node"""
    @staticmethod
    def accept(exp):
        return exp['description'].startswith('ConstantScore(')

    def __init__(self, exp):
        CQExplain.__init__(self, exp)
        self.query = exp['description']

    def disp(self, display):
        display.append('Filter ')
        display.query(self.query)


class CQPhraseWeight(CQExplain):
    """TermWeight for phrases (core tf/idf sim)"""
    @staticmethod
    def accept(exp):
        # Force a phrase (")
        if re.search('^weight\\(.*".*"', exp['description']):
            return True
        return False

    def __init__(self, exp):
        CQExplain.__init__(self, exp)
        # extract field, term and boost from weight(all.plain^0.5:test in 93730) [....
        search = re.search('weight\\(([a-z_\\.]+):([^\\^]+?)(?:\\^([\d\\.]+))? in [\d]+\\) \\[',
                           self.desc)
        if search:
            self.field = search.group(1)
            self.term = search.group(2)
            self.boost = None
            if search.group(3):
                self.boost = float(search.group(3))
        else:
            raise Exception("Cannot parse TermWeight field: " + self.desc)

        self.queryWeight = None
        self.queryNorm = None
        if exp['details'][0]['description'].startswith('score('):
            exp = exp['details'][0]
        if len(exp['details']) > 1:
            if 'queryWeight' in exp['details'][0]['description']:
                qWeight = exp['details'][0]
                fWeight = exp['details'][1]
            else:
                fWeight = exp['details'][0]
                qWeight = exp['details'][1]

            self.queryNorm = qWeight['details'][1]['value']
            self.queryWeight = qWeight['value']
        else:
            fWeight = exp['details'][0]

        if fWeight['details'][0]['description'] == 'idf(), sum of:':
            tfData = fWeight['details'][1]
        else:
            tfData = fWeight['details'][0]

        # extract queryWeight idf info (inside queryWeight, product of:)
        self.tf = tfData['value']
        search = re.search('phraseFreq=([\d\\.]+)$', tfData['details'][0]['description'])
        if search:
            self.phraseFreq = search.group(1)
        else:
            raise Exception('Cannot parse phraseFreq in:' + tfData['details'][0]['description'])
        self.norm = fWeight['details'][2]['value']

        self.idf = exp['details'][0]['details'][1]['value']
        # TODO: fix details extraction
#        self.idfDetails = list()
#        for idf in exp['details'][0]['details'][1]['details']:
#            detail = {
#                'idf': idf['value']
#            }
#            search = re.search('^idf\\(docFreq=(\d+), maxDocs=(\d+)\\)$', idf['description'])
#            if search:
#                detail['docFreq'] = search.group(1)
#                detail['maxDocs'] = search.group(2)
#            else:
#                raise Exception('Cannot load idf details for CQPhraseWeight in : ' +
#                                idf['description'])
#            self.idfDetails.append(detail)

    def disp(self, display):
        display.append('TFIDF ')
        display.append('phrase=')
        display.term(self.field, self.term, self.boost)
        display.append(' tf=')
        display.score(self.tf)
        display.append('(freq=')
        display.score(self.phraseFreq)
        display.append(') ')
        display.append('idf=')
        display.score(self.idf)
        display.append(' fNorm=')
        display.score(self.norm)
        if self.queryWeight is not None:
            display.append(' qWeight=')
            display.score(self.queryWeight)
            display.append('(qNorm=')
            display.score(self.queryNorm)
            display.append(')')


reload(sys)
sys.setdefaultencoding('utf8')

aparser = argparse.ArgumentParser(description='Cirrus Query Debugger', prog=sys.argv[0])
aparser.add_argument('-q', '--query', help='The query', default='cqd')
aparser.add_argument('-w', '--wiki', help='Wiki to run', default='en.wikipedia.org')
aparser.add_argument('-l', '--limit', type=int, help='Limit', default=10)
aparser.add_argument('-o', '--offset', type=int, help='Offset', default=0)
aparser.add_argument('--allField', help='Use the all field (defaults: yes, use no to disable)',
                     default='yes')
aparser.add_argument('-fw', '--functionWindow', type=int, help='Function window size')
aparser.add_argument('-pw', '--phraseWindow', type=int, help='Phrase window size')
aparser.add_argument('-rp', '--rescoreProfile', help='Rescore profile')
aparser.add_argument('-disf', '--dismaxFilter', help='Filter DisMax fields to display')
aparser.add_argument('-docf', '--docFilter', help='Filter docs to display')
aparser.add_argument('-c', '--custom', nargs='+', default=[],
                     help='List of custom param (-c param1=value1 param2=value2)')
args = aparser.parse_args()

params = CQueryParams(args)

query = CQuery(args.query, args.wiki, params)


res = query.run()
printer = CQResultSetPrinter(args)
printer.disp(res)
