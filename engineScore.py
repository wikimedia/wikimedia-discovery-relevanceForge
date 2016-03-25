#!/usr/bin/env python
# engineScore.py - Generate an engine score for a set of queries
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

import os
import sys
import json
import itertools
import functools
import operator
import argparse
import ConfigParser
import hashlib
import tempfile
import subprocess
import math
import pprint
import relevancyRunner

verbose = False


def debug(string):
    if verbose:
        print(string)


class CachedQuery:
    def __init__(self, settings):
        self._cache_dir = settings('workDir') + '/cache'
        self._stats_server = settings('stats_server')
        self._mysql_options = settings('mysql_options')

        with open(settings('query')) as f:
            queryFormat = f.read()
        self._query = queryFormat.format(**settings())

    def _run_query(self):
        p = subprocess.Popen(['ssh', self._stats_server, 'mysql', self._mysql_options],
                             stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE)

        stdout, stderr = p.communicate(input=self._query)
        if len(stdout) == 0:
            raise RuntimeError("Couldn't run SQL query:\n%s" % (stderr))

        return stdout

    def fetch(self):
        query_hash = hashlib.md5(self._query).hexdigest()
        cache_path = "%s/click_log.%s" % (self._cache_dir, query_hash)
        try:
            with open(cache_path, 'r') as f:
                return f.read().split("\n")
        except IOError:
            pass

        result = self._run_query()

        if not os.path.isdir(self._cache_dir):
            try:
                os.mkdir(self._cache_dir)
            except OSError:
                # directory created since checking
                pass

        with open(cache_path, 'w') as f:
            f.write(result)
        return result.split("\n")


def extract_sessions(sql_result):
    # drop the header
    sql_result.pop(0)

    def not_null(x):
        return x != 'NULL'

    sessions = {}
    rows = sorted(line.split("\t", 2) for line in sql_result if len(line) > 0)
    for sessionId, group in itertools.groupby(rows, operator.itemgetter(0)):
        _, clicks, queries = zip(*group)
        sessions[sessionId] = {
            'clicks': set(filter(not_null, clicks)),
            'queries': set(filter(not_null, queries)),
        }
    return sessions


def load_results(results_path):
    # Load the results
    results = {}
    with open(results_path) as f:
        for line in f:
            decoded = json.loads(line)
            hits = []
            if 'error' not in decoded:
                for hit in decoded['rows']:
                    hits.append(hit['pageId'])
            results[decoded['query']] = hits
    return results


# Load an sql results file containing query\tpage_id\tscore
# for use with DCG
def load_relevance_score(results_path):
    relevance = {}
    with open(results_path) as f:
        # burn the header
        f.readline()
        for line in f:
            query, page_id, score = line.strip().split("\t")
            relevance[query][page_id] = score
    return relevance


# Discounted Cumulative Gain
class DCG:
    def __init__(self, results, relevance):
        self.results = results
        self.relevance = relevance

    def _relevance(self, query, page_id):
        if query not in self.relevance:
            return 0
        if page_id not in self.relevance[query]:
            return 0
        return self.relevance[query][page_id]

    def engine_score(self):
        dcg = 0
        for query in self.results:
            hits = self.results[query]
            dcg += self._relevance(hits[0])
            for i in xrange(1, len(hits)):
                dcg += self._relevance(query, hits[i]) / math.log(i, 2)
        return dcg


# Idealized Discounted Cumulative Gain. Computes DCG if the returned
# hits were in the ideal order. Does not take into account results
# that are relevant but not included in the results
class IDCG(DCG):
    def __init__(self, results, relevance):
        self.relevance = relevance
        self.results = {}
        for query in results:
            sorter = itertools.partial(self._relevance, query)
            self.results[query] = sorted(results[query], key=sorter, reverse=True)


# Normalized Discounted Cumulative Gain
class nDCG:
    def __init__(self, results, relevance):
        self.dcg = DCG(results, relevance)
        self.idcg = IDCG(results, relevance)

    def engine_score(self):
        return float(self.dcg.engine_score()) / self.idcg.engine_score()


# Formula from talk given by Paul Nelson at ElasticON 2016
# TODO: This needs a proper name
class EngineScore:
    def __init__(self, sessions, results, factor):
        self.results = results
        self.sessions = sessions
        self.factor = float(factor)

    def _query_score(self, sessionId, query):
        try:
            hits = self.results[query]
        except KeyError:
            debug("\tmissing query? oops...")
            return 0.
        clicks = self.sessions[sessionId]['clicks']
        score = 0.
        for hit, pos in zip(hits, itertools.count()):
            if hit in clicks:
                score += self.factor ** pos
                self.histogram.add(pos)
        return score

    def _session_score(self, sessionId):
        queries = self.sessions[sessionId]['queries']
        if len(queries) == 0:
            # sometimes we get a session with clicks but no queries...
            # might want to filter those at the sql level
            debug("\tsession has no queries...")
            return 0.
        scorer = functools.partial(self._query_score, sessionId)
        return sum(map(scorer, queries))/len(queries)

    def engine_score(self):
        self.histogram = Histogram()
        return sum(map(self._session_score, self.sessions))/len(self.sessions)


class Histogram:
    def __init__(self):
        self.data = {}

    def add(self, value):
        if value in self.data:
            self.data[value] += 1
        else:
            self.data[value] = 1

    def __str__(self):
        most_hits = max(self.data.values())
        scale = 1. / max(1, most_hits/40)
        format = "%2s (%" + str(len(str(most_hits))) + "d): %s\n"
        res = ''
        for i in xrange(0, max(self.data.keys())):
            if i in self.data:
                hits = self.data[i]
            else:
                hits = 0
            res += format % (i, hits, '*' * int(scale * hits))
        return res


def score(sessions, config):
    # Run all the queries
    print('Running queries')
    results_dir = relevancyRunner.runSearch(config, 'test1')
    results = load_results(results_dir)

    print('Calculating engine score')
    scorer = EngineScore(sessions, results, config.get('settings', 'factor'))
    score = scorer.engine_score()
    return score, scorer.histogram


def make_search_config(config, x):
    if x.shape == ():
        x.shape = (1,)
    for value, pos in zip(x, itertools.count()):
        config.set('optimize', 'x%d' % (pos,), value)

    return config.get('optimize', 'config')


def minimize(sessions, config):
    from scipy import optimize

    engine_scores = {}
    histograms = {}

    def f(x):
        search_config = make_search_config(config, x)
        if search_config in engine_scores:
            return engine_scores[search_config]

        print("Trying: " + search_config)
        config.set('test1', 'config', search_config)
        engine_score, histogram = score(sessions, config)
        histograms[search_config] = histogram
        print('Engine Score: %f' % (engine_score))
        engine_score *= -1
        engine_scores[search_config] = engine_score
        return engine_score

    # Make sure we don't reuse query results between runs
    config.set('test1', 'allow_reuse', 0)
    # Exhaustively search the bounds grid
    bounds = json.loads(config.get('optimize', 'bounds'))
    x, fval, grid, jout = optimize.brute(f, bounds, finish=None, disp=True,
                                         full_output=True,
                                         Ns=config.get('optimize', 'Ns'))

    # f() returned negative engine scores, because scipy only does minimization
    jout *= -1
    fval *= -1

    pprint.pprint(grid)
    pprint.pprint(jout)
    print("optimum config: " + make_search_config(config, x))

    results_dir = relevancyRunner.getSafeWorkPath(config, 'test1', 'optimize')
    relevancyRunner.refreshDir(results_dir)
    optimized_config = make_search_config(config, x)
    with open(results_dir + '/config.json', 'w') as f:
        f.write(optimized_config)
    plot_optimize_result(len(x.shape) + 1, grid, jout, results_dir + '/optimize.png', config)

    return fval, histograms[optimized_config]


def plot_optimize_result(dim, grid, jout, filename, config):
    import matplotlib.pyplot as plt
    if dim == 1:
        plt.plot(grid, jout, 'ro')
        plt.ylabel('engine score')
        plt.show()
    elif dim == 2:
        fig = plt.figure()
        ax = fig.add_subplot(1, 1, 1)

        vmin = config.getfloat('optimize', 'zmin')
        vmax = config.getfloat('optimize', 'zmax')

        CS = plt.contourf(grid[0], grid[1], jout, vmin=vmin, vmax=vmax)
        cbar = plt.colorbar(CS)
        cbar.ax.set_ylabel('engine score')

        ax.set_xticks(grid[0][:, 0])
        ax.set_yticks(grid[1][0])
        plt.grid(linewidth=0.5)
    else:
        print("Can't plot %d dimensional graph" % (dim))
        return

    if config.has_option('optimize', 'xlabel'):
        plt.xlabel(config.get_option('optimize', 'xlabel'))
    if config.has_option('optimize', 'ylabel'):
        plt.ylabel(config.get_option('optimize', 'ylabel'))
    plt.savefig(filename)
    if config.has_option('optimize', 'plot') and config.getboolean('optimize', 'plot'):
        plt.show()


def genSettings(config):
    def get(key=None):
        if key is None:
            return dict(config.items('settings'))
        else:
            return config.get('settings', key)
    return get

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Calculate an engine score', prog=sys.argv[0])
    parser.add_argument('-c', '--config', dest='config', help='Configuration file name',
                        required=True)
    parser.add_argument('-v', '--verbose', dest='verbose', action='store_true',
                        help='Increase output verbosity')
    parser.set_defaults(verbose=False)
    args = parser.parse_args()

    config = ConfigParser.ConfigParser()
    verbose = args.verbose
    with open(args.config) as f:
        config.readfp(f)

    relevancyRunner.checkSettings(config, 'settings', [
                                  'stats_server', 'mysql_options', 'date_start',
                                  'date_end', 'dwell_threshold', 'wiki',
                                  'num_sessions', 'workDir'])
    relevancyRunner.checkSettings(config, 'test1', [
                                  'name', 'labHost', 'searchCommand'])
    if config.has_section('optimize'):
        relevancyRunner.checkSettings(config, 'optimize', [
                                      'bounds', 'Ns', 'config', 'zmin', 'zmax'])

    settings = genSettings(config)

    print('Fetching query and click logs')
    query = CachedQuery(settings)
    sessions = extract_sessions(query.fetch())
    queries = set([q for s in sessions.values() for q in s['queries']])
    clicks = sum([len(s['clicks']) for s in sessions.values()])
    print('Loaded %d sessions with %d clicks and %d unique queries' %
          (len(sessions), clicks, len(queries)))

    # Write out a list of queries for the relevancyRunner
    queries_temp = tempfile.mkstemp('_engine_score_queries')
    try:
        with os.fdopen(queries_temp[0], 'w') as f:
            f.write("\n".join(queries))
        config.set('test1', 'queries', queries_temp[1])

        if config.has_section('optimize'):
            engine_score, histogram = minimize(sessions, config)
        else:
            engine_score, histogram = score(sessions, config)
    finally:
        os.remove(queries_temp[1])

    print('Engine Score: %0.2f' % (engine_score))
    print('Histogram:')
    print(str(histogram))
