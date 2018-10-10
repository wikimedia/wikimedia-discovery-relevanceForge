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

import argparse
from collections import Counter, defaultdict
import ConfigParser
import functools
import itertools
import json
import logging
import math
import os
import operator
import random
import sys
import tempfile

from relforge.query import CachedQuery
import relforge.runner


LOG = logging.getLogger(__name__)


def init_scorer(settings):
    scoring_algos = {
        'PaulScore': PaulScore,
        'nDCG': nDCG,
        'ERR': ERR,
        'MRR': MRR_AC,
        'MPC': MPC,
    }

    query = CachedQuery(settings)
    query_data = query.fetch()
    scoring_configs = query.scoring_config
    if type(scoring_configs) != list:
        scoring_configs = [scoring_configs]

    scorers = []
    iters = itertools.tee(query_data, len(scoring_configs))
    for config, query_data_iter in zip(scoring_configs, iters):
        algo = config['algorithm']
        print('Initializing engine scorer: %s' % (algo))
        scoring_class = scoring_algos[algo]
        scorer = scoring_class(query_data_iter, config['options'])
        scorer.report()
        scorers.append(scorer)

    if len(scorers) > 1:
        return MultiScorer(scorers)
    else:
        return scorers[0]


def load_results(json_lines):
    # Load the results
    results = {}
    for line in json_lines:
        decoded = json.loads(line)
        hits = []
        if 'error' in decoded:
            LOG.warning('Error in result: %s', line)
        else:
            for hit in decoded['rows']:
                try:
                    # Cirrus
                    docId = str(hit['docId'])
                except KeyError:
                    # Wikidata
                    docId = str(hit['pageId'])
                hits.append({
                    'docId': docId,
                    'title': hit['title'],
                })
        if decoded['query'] in results:
            raise Exception('Duplicate result sets for {}'.format(decoded['query']))
        results[decoded['query']] = hits
    LOG.debug('Loaded %d results', len(results))
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


class MRR_AC(object):
    """Mean Reciprocal Rank for Auto Complete"""
    def __init__(self, rows, options):
        self._queries = defaultdict(list)
        for row in rows:
            query, page_id = row
            self._queries[query].append(int(page_id))
        self.queries = set(q[:i + 1] for q in self._queries.keys() for i in range(len(q)))

    def name(self):
        return "MRR_AC"

    def report(self):
        num_clicks = sum(len(page_ids) for page_ids in self._queries.values())
        num_prefixes = len(self.queries)
        print("Loaded MRR with %d clicks and %d unique prefixes" %
              (num_clicks, num_prefixes))

    @staticmethod
    def score_query(results, query, page_id, allow_missing=False):
        for i in range(len(query)):
            prefix = query[:i + 1]
            try:
                result_list = results[prefix]
            except KeyError:
                if allow_missing:
                    yield 0.
                    continue
                raise Exception('Missing results for prefix {}'.format(prefix))
            try:
                # result_list holds elasticsearch docId's which are always a
                # stringified page id
                j = result_list[str(page_id)]
            except KeyError:
                yield 0.
            else:
                yield 1. / j

    def engine_score(self, results):
        # Enumerate from 1 as MRR is 1 indexed, giving first position the score 1/1.
        results = {q: {hit['docId']: i for i, hit in enumerate(hits, 1)}
                   for q, hits in results.items()}
        score = 0
        N = 0
        for query, page_ids in self._queries.items():
            for page_id in page_ids:
                # Not 100% what is right but this is mean per query
                # instead of per prefix.
                query_score = list(self.score_query(results, query, page_id))
                score += sum(query_score) / len(query_score)
                N += 1
        return EngineScore(self.name(), score / N)


def calc_mpc(queries):
    votes = defaultdict(Counter)
    for query, page_ids in queries.items():
        for i in range(len(query)):
            prefix = query[:i + 1]
            votes[prefix].update(page_ids)
    results = {}
    for prefix, counts in votes.items():
        # TODO: Elements with equal counts are ordered arbitrarily. Not sure
        # what is appropriate to do here.
        results[prefix] = {page_id: i for i, (page_id, count) in enumerate(counts.most_common(), 1)}
    return results


class MPC(object):
    """Calculate MRR over a result set generated by Most Popular Completion

    This overfits massively unless you have a large set of clicks, (how many?)
    """
    def __init__(self, rows, options):
        self.test_set = defaultdict(list)
        self._train_set = None
        r = random.Random(0)
        train_split = 1.0
        if 'test_train_split' in options and options['test_train_split'] != 0.0:
            # The specified % of clicks will be assigned to the train set, leaving
            # the remainder as the test set.
            train_split = float(options['test_train_split'])
            self._train_set = defaultdict(list)
        if not 0.0 <= train_split <= 1.0:
            raise Exception('train_split ({}) must be between 0 and 1'.format(train_split))

        for query, page_id in rows:
            if r.random() >= train_split:
                self.test_set[query].append(str(page_id))
            else:
                self.train_set[query].append(str(page_id))
        self.model = calc_mpc(self.train_set)
        # We don't require any external search requests
        self.queries = []

    @property
    def train_set(self):
        if self._train_set is None:
            return self.test_set
        else:
            return self._train_set

    def name(self):
        return "MPC MRR"

    def report(self):
        print("MPC MRR loaded test set with {} pages and train set with {} pages".format(
            len(self.test_set), len(self.train_set)))

    def engine_score(self, results):
        score = 0
        N = 0
        for query, page_ids in self.test_set.items():
            for page_id in page_ids:
                # Not 100% what is right but this is mean per query
                # instead of per prefix. We have to allow missing for
                # the test/train split where some prefixes only exist
                # on one side.
                query_score = list(MRR_AC.score_query(
                    self.model, query, page_id, allow_missing=True))
                score += sum(query_score) / len(query_score)
                N += 1
        return EngineScore(self.name(), score / N)


# Discounted Cumulative Gain
class DCG(object):
    def __init__(self, rows, options):
        self.k = options.get('k', 20)
        if type(self.k) == list:
            self.k = self.k[0]
        else:
            self.k = int(self.k)
        self._relevance = defaultdict(dict)
        for query, title, score in rows:
            self._relevance[query][title] = score

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
    def __init__(self, rows, options):
        super(IDCG, self).__init__(rows, options)

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
    def __init__(self, rows, options):
        # list() makes a copy, so each gets their own unique list
        self.dcg = DCG(list(rows), options)
        self.idcg = IDCG(list(rows), options)
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
            LOG.debug("failed to find query (%s) in scores", query)
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
    def __init__(self, rows, options):
        super(ERR, self). __init__(rows, options)
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
    def __init__(self, rows, options):

        self._sessions = self._extract_sessions(rows)
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

    def _extract_sessions(self, rows):
        def not_null(x):
            return x != 'NULL'

        sessions = {}
        rows = sorted(rows)
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
            LOG.debug("missing query? oops...")
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
            LOG.debug("session has no queries...")
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


def genSettings(config):
    def get(key=None):
        if key is None:
            return dict(config.items('settings'))
        else:
            return config.get('settings', key)
    return get


def main():
    parser = argparse.ArgumentParser(description='Calculate an engine score', prog=sys.argv[0])
    parser.add_argument('-c', '--config', dest='config', help='Configuration file name',
                        required=True)
    parser.add_argument('-v', '--verbose', dest='verbose', action='store_true',
                        help='Increase output verbosity')
    parser.set_defaults(verbose=False)
    args = parser.parse_args()
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO)

    config = ConfigParser.ConfigParser()
    with open(args.config) as f:
        config.readfp(f)

    relforge.runner.checkSettings(config, 'settings', ['query', 'workDir'])
    relforge.runner.checkSettings(config, 'test1', [
                                  'name', 'labHost', 'searchCommand'])
    settings = genSettings(config)
    scorer = init_scorer(settings)

    # Write out a list of queries for the runner
    queries_temp = tempfile.mkstemp('_engine_score_queries')
    try:
        with os.fdopen(queries_temp[0], 'w') as f:
            f.write("\n".join(scorer.queries).encode('utf-8'))
        config.set('test1', 'queries', queries_temp[1])
        # Run all the queries
        print('Running queries')
        results_dir = relforge.runner.runSearch(config, 'test1')
        with open(results_dir) as f:
            results = load_results(f)

        print('Calculating engine score')
        engine_score = scorer.engine_score(results)
    finally:
        os.remove(queries_temp[1])

    engine_score.output()


if __name__ == '__main__':
    main()
