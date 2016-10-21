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
    scoring_algos = {
        'PaulScore': PaulScore,
        'nDCG': nDCG,
        'ERR': ERR,
    }

    query = CachedQuery(settings)
    query_data = query.fetch()
    scoring_configs = query.scoring_config
    if type(scoring_configs) != list:
        scoring_configs = [scoring_configs]

    scorers = []
    for config in scoring_configs:
        algo = config['algorithm']
        print('Initializing engine scorer: %s' % (algo))
        scoring_class = scoring_algos[algo]
        scorer = scoring_class(query_data, config['options'])
        scorer.report()
        scorers.append(scorer)

    if len(scorers) > 1:
        return MultiScorer(scorers)
    else:
        return scorers[0]


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


class MultiScorer(object):
    def __init__(self, scorers):
        self.scorers = scorers
        self.queries = set([q for s in scorers for q in s.queries])

    def name(self):
        return ", ".join([s.name() for s in self.scorers])

    def report(self):
        for scorer in self.scorers:
            scorer.report()

    def engine_score(self, results):
        scores = []
        for scorer in self.scorers:
            score = scorer.engine_score(results)
            if type(score) == EngineScoreSet:
                scores = scores + score.scores
            else:
                scores.append(score)
        return EngineScoreSet(scores)


# Discounted Cumulative Gain
class DCG(object):
    def __init__(self, sql_result, options):
        self.k = options.get('k', 20)
        if type(self.k) == list:
            self.k = self.k[0]
        else:
            self.k = int(self.k)
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

    def name(self):
        return "DCG@%d" % (self.k)

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
        return EngineScore(self.name(), sum(self.dcgs.values()) / len(results))


# Idealized Discounted Cumulative Gain. Computes DCG against the ideal
# order for results to this query, per the provided relevance query
# results
class IDCG(DCG):
    def __init__(self, sql_result, options):
        super(IDCG, self).__init__(sql_result, options)

    def name(self):
        return "IDCG@%d" % (self.k)

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
        return EngineScore(self.name(), super(IDCG, self).engine_score(ideal_results))


# Normalized Discounted Cumulative Gain
class nDCG(object):
    def __init__(self, sql_result, options):
        # list() makes a copy, so each gets their own unique list
        self.dcg = DCG(list(sql_result), options)
        self.idcg = IDCG(list(sql_result), options)
        self.queries = self.dcg._relevance.keys()
        self.k = options.get('k', 20)
        if type(self.k) != list:
            self.k = [self.k]

    def name(self, k=None):
        if k is None:
            # A bit of a lie...but whatever
            k = self.k[0]
        return "nDCG@%d" % (k)

    def report(self):
        num_results = sum([len(self.dcg._relevance[title]) for title in self.dcg._relevance])
        print("Loaded nDCG with %d queries and %d scored results" %
              (len(self.queries), num_results))

    def _query_score(self, query):
        try:
            dcg = self.dcg.dcgs[query]
            idcg = self.idcg.dcgs[query]
            return dcg / idcg if idcg > 0 else 0
        except KeyError:
            # @todo this shouldn't be necessary, but there is some sort
            # of utf8 round tripping problem that breaks a few queries
            debug("failed to find query (%s) in scores" % (query))
            return None

    def engine_score(self, results):
        scores = []
        for k in self.k:
            self.dcg.k = k
            self.dcg.engine_score(results)
            self.idcg.k = k
            self.idcg.engine_score(results)

            ndcgs = []
            errors = 0
            for query in self.dcg.dcgs:
                ndcg = self._query_score(query)
                if ndcg is None:
                    errors += 1
                else:
                    ndcgs.append(ndcg)

            if errors > 0:
                print("Expected %d queries, but %d were missing" % (len(self.dcg.dcgs), errors))

            scores.append(EngineScore(self.name(k), sum(ndcgs) / len(ndcgs)))
        return EngineScoreSet(scores)


# http://olivier.chapelle.cc/pub/err.pdf
# http://don-metzler.net/presentations/err_cikm09.pdf
# A drawback of DCG is its additive nature and the underlying independence
# assumption: a document in a given position has always the same gain and
# discount independently of the documents shown above it. This new metric is
# defined as the expected reciprocal length of time that the user will take to
# find a relevant document.
# Compared to position-based metrics such as DCG and RBP for which the discount
# depends only the position, the discount in ERR depends on the relevance of
# documents shown above it.
#
# Note this isn't really a sub-thing of DCG, it just happens to be computed similarly
# enough we can reused all its code except engine_score()
class ERR(DCG):
    def __init__(self, sql_result, options):
        super(ERR, self). __init__(sql_result, options)
        # Assuming a relevance scale of {0, 1, 2, 3}
        # max is 2^3 = 8
        self.max_rel = pow(2, options.get('max_relevance_scale'))
        self.k = options.get('k', 20)
        if type(self.k) != list:
            self.k = [self.k]
        self.queries = self._relevance.keys()

    def report(self):
        num_results = sum([len(self._relevance[title]) for title in self._relevance])
        print("Loaded ERR with %d queries and %d scored results" %
              (len(self.queries), num_results))

    def name(self, k=None):
        if k is None:
            k = self.k[0]
        return "ERR@%d" % (k)

    def _probability_of_relevance(self, query, hit):
        # Map from hit to relevance grade
        score = self._relevance_score(query, hit)
        # Map from relevance grade to probability of relevance
        # On the example scale of {0, 1, 2, 3} this gives
        # probabilities of {0, 12.5, 37.5, 87.5}
        return (pow(2, score) - 1) / self.max_rel

    def _query_score(self, k, query, hits):
        p = 1
        err = 0
        for i in xrange(0, min(k, len(hits))):
            # The r value is 1-indexed
            r = i + 1
            R = self._probability_of_relevance(query, hits[i])
            err = err + p * (R / r)
            p = p * (1 - R)
        return err

    def engine_score(self, results):
        scores = []
        for k in self.k:
            total_err = sum([self._query_score(k, q, results[q]) for q in results])
            scores.append(EngineScore(self.name(k), total_err / len(results)))
        return EngineScoreSet(scores)


# Formula from talk given by Paul Nelson at ElasticON 2016
class PaulScore:
    def __init__(self, sql_result, options):

        self._sessions = self._extract_sessions(sql_result)
        self.queries = set([q for s in self._sessions.values() for q in s['queries']])
        self.factors = options['factor']
        if type(self.factors) != list:
            self.factors = [self.factors]

    def name(self, factor=None):
        if factor is None:
            # This is a complete lie...but whatever
            factor = self.factors[0]
        return "PaulScore@%.2f" % (factor)

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

    def _query_score(self, factor, sessionId, query):
        try:
            hits = self.results[query]
        except KeyError:
            debug("\tmissing query? oops...")
            return 0.
        clicks = self._sessions[sessionId]['clicks']
        score = 0.
        for hit, pos in zip(hits, itertools.count()):
            if hit['docId'] in clicks:
                score += factor ** pos
                self.histogram.add(pos)
        return score

    def _session_score(self, factor, sessionId):
        queries = self._sessions[sessionId]['queries']
        if len(queries) == 0:
            # sometimes we get a session with clicks but no queries...
            # might want to filter those at the sql level
            debug("\tsession has no queries...")
            return 0.
        scorer = functools.partial(self._query_score, factor, sessionId)
        return sum(map(scorer, queries))/len(queries)

    def engine_score(self, results):
        self.results = results
        scores = []
        for factor in self.factors:
            self.histogram = Histogram()
            scorer = functools.partial(self._session_score, factor)
            score = sum(map(scorer, self._sessions))/len(self._sessions)
            scores.append(EngineScore(self.name(factor), score, self.histogram))
        return EngineScoreSet(scores)


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


class EngineScore(object):
    def __init__(self, name, score, histogram=None):
        self.name = name
        self.score = score
        self.histogram = histogram

    def name(self):
        return self.name

    def score(self):
        return self.score

    def output(self, verbose=True):
        print('%s: %0.2f' % (self.name, self.score))
        if verbose and self.histogram is not None:
            print('Histogram:')
            print(str(self.histogram))


class EngineScoreSet(object):
    def __init__(self, scores):
        self.scores = scores

    def name(self):
        # While wasteful, if the receiving code doesnt care about
        # the difference between EngineScore and EngineScoreSet just
        # give them the first one
        return self.scores[0].name()

    def score(self):
        # While wasteful, if the receiving code doesnt care about
        # the difference between EngineScore and EngineScoreSet just
        # give them the first one
        return self.scores[0].score()

    def output(self, verbose=True):
        for score in self.scores:
            score.output(verbose)


def score(scorer, config):
    # Run all the queries
    print('Running queries')
    results_dir = relevancyRunner.runSearch(config, 'test1')
    results = load_results(results_dir)

    print('Calculating engine score')
    return scorer.engine_score(results)


def make_search_config(config, x):
    if x.shape == ():
        x.shape = (1,)
    for value, pos in zip(x, itertools.count()):
        config.set('optimize', 'x%d' % (pos,), value)

    return config.get('optimize', 'config')


def minimize(scorer, config):
    from scipy import optimize

    engine_scores = {}

    def f(x):
        search_config = make_search_config(config, x)
        if search_config in engine_scores:
            return engine_scores[search_config].score

        print("Trying: " + search_config)
        config.set('test1', 'config', search_config)
        engine_score = score(scorer, config)
        print('Engine Score: %f' % (engine_score.score))
        # Our optimizer is a minimizer, so flip the score
        engine_score.score *= -1
        engine_scores[search_config] = engine_score
        return score.engine_score

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

    pprint.pprint(grid)
    pprint.pprint(jout)
    optimized_config = make_search_config(config, x)
    print("optimum config: " + optimized_config)

    results_dir = relevancyRunner.getSafeWorkPath(config, 'test1', 'optimize')
    relevancyRunner.refreshDir(results_dir)
    with open(results_dir + '/config.json', 'w') as f:
        f.write(optimized_config)
    plot_optimize_result(len(x.shape) + 1, grid, jout, results_dir + '/optimize.png', config)

    engine_score = engine_scores[optimized_config]
    # Flip the score back to it's true value
    engine_score.score *= -1
    return engine_score


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
            engine_score = minimize(scorer, config)
        else:
            engine_score = score(scorer, config)
    finally:
        os.remove(queries_temp[1])

    engine_score.output()
