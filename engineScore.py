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
import yaml
import codecs

verbose = False


def debug(string):
    if verbose:
        print(string)


def init_scorer(settings):
    scorers = {
        'PaulScore': PaulScore,
        'nDCG': nDCG,
    }

    query = CachedQuery(settings)
    algo = query.scoring_config['algorithm']
    print('Initializing engine scorer: %s' % (algo))

    scoring_class = scorers[algo]
    scorer = scoring_class(query.fetch(), query.scoring_config['options'])

    scorer.report()

    return scorer


class CachedQuery:
    def __init__(self, settings):
        self._cache_dir = settings('workDir') + '/cache'

        with codecs.open(settings('query'), "r", "utf-8") as f:
            sql_config = yaml.load(f.read())

        try:
            server = self._choose_server(sql_config['servers'], settings('host'))
        except ConfigParser.NoOptionError:
            server = sql_config['servers'][0]

        self._stats_server = server['host']
        self._mysql_cmd = server.get('cmd')
        self.scoring_config = sql_config['scoring']

        sql_config['variables'].update(settings())
        self._query = sql_config['query'].format(**sql_config['variables'])

    def _choose_server(servers, host):
        for server in config['servers']:
            if server['host'] == host:
                return servers[0]

        raise RuntimeError("Couldn't locate host %s" % (host))

    def _run_query(self):
        p = subprocess.Popen(['ssh', self._stats_server, self._mysql_cmd],
                             stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE)

        stdout, stderr = p.communicate(input=self._query)
        if len(stdout) == 0:
            raise RuntimeError("Couldn't run SQL query:\n%s" % (stderr))

        try:
            return stdout.decode('utf-8')
        except UnicodeDecodeError:
            # Some unknown problem ... let's just work through it line by line
            # and throw out bad data :(
            clean = []
            for line in stdout.split("\n"):
                try:
                    clean.append(line.decode('utf-8'))
                except UnicodeDecodeError:
                    debug("Non-utf8 data: %s" % (line))
            return u"\n".join(clean)

    def fetch(self):
        query_hash = hashlib.md5(self._query).hexdigest()
        cache_path = "%s/click_log.%s" % (self._cache_dir, query_hash)
        try:
            with codecs.open(cache_path, 'r', 'utf-8') as f:
                return f.read().split("\n")
        except IOError:
            debug("No cached query result available.")
            pass

        result = self._run_query()

        if not os.path.isdir(self._cache_dir):
            try:
                os.makedirs(self._cache_dir)
            except OSError:
                debug("cache directory created since checking")
                pass

        with codecs.open(cache_path, 'w', 'utf-8') as f:
            f.write(result)
        return result.split("\n")


def load_results(results_path):
    # Load the results
    results = {}
    with open(results_path) as f:
        for line in f:
            decoded = json.loads(line)
            hits = []
            if 'error' not in decoded:
                for hit in decoded['rows']:
                    hits.append({
                        'docId': hit['docId'],
                        'title': hit['title'],
                    })
            results[decoded['query']] = hits
    return results


# Discounted Cumulative Gain
class DCG(object):
    def __init__(self, sql_result, options):
        self.k = int(options.get('k', 20))
        self._relevance = {}

        # burn the header
        sql_result.pop(0)

        # Load the query results
        for line in sql_result:
            if len(line) == 0:
                continue
            query, title, score = line.strip().split("\t")
            if score == 'NULL':
                score = 0
            if query not in self._relevance:
                self._relevance[query] = {}
            self._relevance[query][title] = float(score)

    def _relevance_score(self, query, hit):
        if query not in self._relevance:
            return 0
        title = hit['title']
        if title not in self._relevance[query]:
            return 0
        return self._relevance[query][title]

    # Returns the average DCG of the results
    def engine_score(self, results):
        self.dcgs = {}
        for query in results:
            hits = results[query]
            dcg = 0
            for i in xrange(0, min(self.k, len(hits))):
                top = math.pow(2, self._relevance_score(query, hits[i])) - 1
                # Note this is i+2, rather than i+1, because the i+1 algo starts
                # is 1 indexed, and we are 0 indexed. log base 2 of 1 is 0 and
                # we would have a div by zero problem otherwise
                dcg += top / math.log(i+2, 2)
            self.dcgs[query] = dcg
        return sum(self.dcgs.values()) / len(results)


# Idealized Discounted Cumulative Gain. Computes DCG against the ideal
# order for results to this query, per the provided relevance query
# results
class IDCG(DCG):
    def __init__(self, sql_result, options):
        super(IDCG, self).__init__(sql_result, options)

    # The results argument is unused here, as this is the ideal and unrelated
    # to the actual search results returned
    def engine_score(self, results):
        ideal_results = {}
        for query in self._relevance:
            # Build up something that looks like the hits search returns
            ideal_hits = []
            for title in self._relevance[query]:
                ideal_hits.append({'title': title})

            # Sort them into the ideal order and slice to match
            sorter = functools.partial(self._relevance_score, query)
            ideal_results[query] = sorted(ideal_hits, key=sorter, reverse=True)

        # Run DCG against the ideal ordered results
        return super(IDCG, self).engine_score(ideal_results)


# Normalized Discounted Cumulative Gain
class nDCG(object):
    def __init__(self, sql_result, options):
        # list() makes a copy, so each gets their own unique list
        self.dcg = DCG(list(sql_result), options)
        self.idcg = IDCG(list(sql_result), options)
        self.queries = self.dcg._relevance.keys()

    def report(self):
        num_results = sum([len(self.dcg._relevance[title]) for title in self.dcg._relevance])
        print("Loaded nDCG with %d queries and %d scored results" %
              (len(self.queries), num_results))

    def engine_score(self, results):
        self.dcg.engine_score(results)
        self.idcg.engine_score(results)

        ndcgs = []
        debug = {}
        for query in self.dcg.dcgs:
            try:
                dcg = self.dcg.dcgs[query]
                idcg = self.idcg.dcgs[query]
                ndcg = dcg / idcg if idcg > 0 else 0
                ndcgs.append(ndcg)
                debug[query] = {
                    'dcg': dcg,
                    'idcg': idcg,
                    'ndcg': dcg / idcg if idcg > 0 else 0
                }
            except KeyError:
                # @todo this shouldn't be necessary, but there is some sort
                # of utf8 round tripping problem that breaks a few queries
                debug("failed to find query (%s) in scores" % (query))
                pass
        # print(json.dumps(debug))

        if len(self.dcg.dcgs) != len(debug):
            print("Expected %d queries, but only got %d" % (len(self.dcg.dcgs), len(debug)))

        return sum(ndcgs) / len(ndcgs)


# Formula from talk given by Paul Nelson at ElasticON 2016
class PaulScore:
    def __init__(self, sql_result, options):

        self._sessions = self._extract_sessions(sql_result)
        self.queries = set([q for s in self._sessions.values() for q in s['queries']])
        self.factor = float(options['factor'])

    def report(self):
        num_clicks = sum([len(s['clicks']) for s in self._sessions.values()])
        print('Loaded %d sessions with %d clicks and %d unique queries' %
              (len(self._sessions), num_clicks, len(self.queries)))

    def _extract_sessions(self, sql_result):
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
                'queries': set(filter(not_null, [q.strip() for q in queries])),
            }
        return sessions

    def _query_score(self, sessionId, query):
        try:
            hits = self.results[query]
        except KeyError:
            debug("\tmissing query? oops...")
            return 0.
        clicks = self._sessions[sessionId]['clicks']
        score = 0.
        for hit, pos in zip(hits, itertools.count()):
            if hit['docId'] in clicks:
                score += self.factor ** pos
                self.histogram.add(pos)
        return score

    def _session_score(self, sessionId):
        queries = self._sessions[sessionId]['queries']
        if len(queries) == 0:
            # sometimes we get a session with clicks but no queries...
            # might want to filter those at the sql level
            debug("\tsession has no queries...")
            return 0.
        scorer = functools.partial(self._query_score, sessionId)
        return sum(map(scorer, queries))/len(queries)

    def engine_score(self, results):
        self.results = results
        self.histogram = Histogram()
        return sum(map(self._session_score, self._sessions))/len(self._sessions)


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


def score(scorer, config):
    # Run all the queries
    print('Running queries')
    results_dir = relevancyRunner.runSearch(config, 'test1')
    results = load_results(results_dir)

    print('Calculating engine score')
    score = scorer.engine_score(results)
    try:
        return score, scorer.histogram
    except AttributeError:
        return score, None


def make_search_config(config, x):
    if x.shape == ():
        x.shape = (1,)
    for value, pos in zip(x, itertools.count()):
        config.set('optimize', 'x%d' % (pos,), value)

    return config.get('optimize', 'config')


def minimize(scorer, config):
    from scipy import optimize

    engine_scores = {}
    histograms = {}

    def f(x):
        search_config = make_search_config(config, x)
        if search_config in engine_scores:
            return engine_scores[search_config]

        print("Trying: " + search_config)
        config.set('test1', 'config', search_config)
        engine_score, histogram = score(scorer, config)
        histograms[search_config] = histogram
        print('Engine Score: %f' % (engine_score))
        engine_score *= -1
        engine_scores[search_config] = engine_score
        return engine_score

    # Make sure we don't reuse query results between runs
    config.set('test1', 'allow_reuse', 0)
    # Exhaustively search the bounds grid
    bounds = json.loads(config.get('optimize', 'bounds'))

    Ns = json.loads(config.get('optimize', 'Ns'))
    if type(Ns) is list:
        # different samples sizes (Ns) across different dimensions; set up slices
        newbounds = []
        for N, range in zip(Ns, bounds):
            if N < 2:
                N = 2
            step = float(range[1] - range[0])/(N-1)
            # add epsilon (step/100) to upper range; otherwise slice doesn't include the last point
            newbounds.append([range[0], float(range[1]) + step/100, step])
        Ns = 0
        bounds = newbounds
    else:
        if Ns < 2:
            Ns = 2
    x, fval, grid, jout = optimize.brute(f, bounds, finish=None, disp=True,
                                         full_output=True, Ns=Ns)

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

        vmin = vmax = None
        if config.has_option('optimize', 'zmin'):
            vmin = config.getfloat('optimize', 'zmin')
        if config.has_option('optimize', 'zmax'):
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

    relevancyRunner.checkSettings(config, 'settings', ['query', 'workDir'])
    relevancyRunner.checkSettings(config, 'test1', [
                                  'name', 'labHost', 'searchCommand'])
    if config.has_section('optimize'):
        relevancyRunner.checkSettings(config, 'optimize', [
                                      'bounds', 'Ns', 'config'])

        Ns = json.loads(config.get('optimize', 'Ns'))
        if type(Ns) is int:
            pass
        elif type(Ns) is list:
            bounds = json.loads(config.get('optimize', 'bounds'))
            if len(Ns) != len(bounds):
                raise ValueError("Section [optimize] configuration Ns as list " +
                                 "needs to be the same length as bounds")
        else:
            raise ValueError("Section [optimize] configuration Ns " +
                             "needs to be integer or list of integers")

    settings = genSettings(config)

    scorer = init_scorer(settings)

    # Write out a list of queries for the relevancyRunner
    queries_temp = tempfile.mkstemp('_engine_score_queries')
    try:
        with os.fdopen(queries_temp[0], 'w') as f:
            f.write("\n".join(scorer.queries).encode('utf-8'))
        config.set('test1', 'queries', queries_temp[1])

        if config.has_section('optimize'):
            engine_score, histogram = minimize(scorer, config)
        else:
            engine_score, histogram = score(scorer, config)
    finally:
        os.remove(queries_temp[1])

    print('Engine Score: %0.2f' % (engine_score))
    if histogram is not None:
        print('Histogram:')
        print(str(histogram))
