import logging
import time

import hyperopt
import numba
import numpy as np
import pandas as pd
import tensorflow as tf


use_numba = True
if use_numba:
    njit = numba.njit
else:
    def njit(parallel=False):
        def inner(fn):
            return fn
        return inner


log = logging.getLogger(__name__)
# Default MRR values
RECIP_EXAM_PROB = 1 / np.arange(1, 100)
# Calculated from wikidata autocomplete users
EXAM_PROB = np.asarray([0.6361, 0.4922, 0.4002, 0.3042, 0.2226, 0.1814, 0.0651])


def tf_run_all(tf_session, data_init_op, op):
    try:
        if data_init_op is not None:
            tf_session.run(data_init_op)
        while True:
            yield tf_session.run(op)
    except tf.errors.OutOfRangeError:
        pass


def prefixes(string):
    """Return all prefixes of provided string from shortest to longest"""
    assert isinstance(string, str)
    return (string[:i] for i in range(1, len(string) + 1))


@njit()
def score_query(search_results, clickpage, exam_prob=EXAM_PROB):
    """Mean prefix length satisfied at"""
    remain = 1.0
    result = 0.0
    max_prefix_len = search_results.shape[0]
    top_k = min(len(exam_prob), search_results.shape[1])
    for i in range(max_prefix_len):
        for j in range(top_k):
            if search_results[i, j] == clickpage:
                break
        else:
            continue
        satisfied = remain * exam_prob[j]
        remain -= satisfied
        # 'satisfied' will add up to 1 at the end, so a simple sum
        # gives us the mean length
        # prefix length is i + 1
        result += satisfied * (i + 1)
    # Assume max_prefix_length for unsatisfied users
    if remain > 0:
        result += remain * max_prefix_len
    return result


class EvaluationScores(object):
    def __init__(self, scores):
        self.scores = scores

    @property
    def mean(self):
        return np.mean(self.scores)

    @property
    def std(self):
        return np.std(self.scores)

    @property
    def percentiles(self):
        return np.percentile(self.scores, range(0, 101))

    @property
    def summary(self):
        return {
            'mean': float(self.mean),
            'std': float(self.std),
        }

    def to_dict(self, with_scores=False):
        result = dict(self.summary, percentiles=self.percentiles.tolist())
        if with_scores:
            result['scores'] = self.scores.tolist()
        return result


class EvaluationReport(object):
    def __init__(self, variables, scores, timing):
        assert np.all(~np.isnan(np.hstack(list(scores.values()))))
        self.variables = variables
        self.scores = {k: EvaluationScores(v) for k, v in scores.items()}
        self.timing = timing

    def __getitem__(self, idx):
        return self.scores[idx]

    @property
    def took_sec(self):
        return sum(self.timing.values())

    @property
    def summary(self):
        return {
            'variables': {k: float(v) for k, v in self.variables.items()},
            'took_sec': float(self.took_sec),
            'scores': {name: score.summary for name, score in self.scores.items()}
        }

    def to_dict(self, with_scores=False):
        return dict(
            self.summary,
            timing=self.timing,
            scores={name: score.to_dict(with_scores) for name, score in self.scores.items()})


class MinimizeReport(object):
    def __init__(self, initial_report, evaluation_reports, num_observations, num_hits, dataset='test'):
        self.initial_report = initial_report
        self.evaluation_reports = evaluation_reports
        self.num_hits = num_hits
        self.num_observations = num_observations
        self.dataset = dataset
        # TODO: This are set after creation because reasons...
        self.run_parameters = None

    @property
    def best_idx(self):
        # TODO: vary with some strategy, like best_value_near_zero?
        # Or more likely something taking into account overfitting.
        return np.argmin([r[self.dataset].mean for r in self.evaluation_reports])

    @property
    def best_report(self):
        return self.evaluation_reports[self.best_idx]

    @property
    def summary(self):
        return {
            'run_parameters': self.run_parameters,
            'num_observations': self.num_observations,
            'num_hits': self.num_hits,
            'initial_report': self.initial_report.summary,
            'best_report': self.best_report.summary,
        }

    def to_dict(self, with_scores=False):
        """Create a json serializable dictionary version of the report"""
        reports = [r.to_dict(with_scores) for r in self.evaluation_reports]
        return dict(self.summary, reports=reports)


class SensitivityReport(object):
    def __init__(self, variable_reports):
        self.variable_reports = variable_reports

    @property
    def variables(self):
        return self.variable_reports.keys()

    def sensitivity(self, var_name, dataset='test'):
        reports = self.variable_reports[var_name]
        x = np.empty((2, len(reports)))
        for i, report in enumerate(reports):
            x[0, i] = report.variables[var_name]
            x[1, i] = report[dataset].mean
        # TODO: What metric makes sense over this to quantify sensitivity?
        return pd.DataFrame(x, columns=('value', 'mean')).sort_values('value')

    @property
    def summary(self):
        return {
            'variable_reports': {var_name: [r.summary for r in reports]
                                 for var_name, reports in self.variable_reports.items()}
        }

    def to_dict(self, with_scores=False):
        return {
            'variable_reports': {var_name: [r.to_dict(with_scores) for r in reports]
                                 for var_name, reports in self.variable_reports.items()}
        }


class AutocompleteEvaluator(object):
    def __init__(
        self, tf_session, data_init_op, score_op, datasets, top_k,
        variables_ops, metric=score_query, train='train', test='test',
        max_prefix_len=10,
    ):
        self.tf_session = tf_session
        self.data_init_op = data_init_op
        self.score_op = score_op
        self.datasets = datasets
        self.top_k = top_k
        self.variables_ops = variables_ops
        self.metric = metric
        self.max_prefix_len = max_prefix_len

    @property
    def num_hits(self):
        return self.page_ids.size

    @property
    def num_observations(self):
        return {k: len(df) for k, df in self.datasets.items()}

    def make_agg_report(self, reports):
        return MinimizeReport(self.initial_report, reports, self.num_observations, self.num_hits)

    def _simplify_df(self, df, str_to_cat_id):
        df.reset_index(inplace=True)
        # TODO: Why default None? When do items not exist?
        df['searchterm'] = df['searchterm'].apply(lambda x: str_to_cat_id.get(x, None))
        df.dropna(subset=['searchterm'], inplace=True)
        return df[['searchterm', 'clickpage']].astype(np.int64).values

    def _build_results_lookup_indexes(self, str_to_cat_id):
        # dict from searchterm cat_id to cat_id's of all it's prefixes from
        # shortest to longest
        max_cat_id = max(str_to_cat_id.values())
        lookup = np.zeros((max_cat_id + 1, self.max_prefix_len), dtype=np.int64)
        for df in self.datasets.values():
            for searchterm in df['searchterm'].unique():
                try:
                    cat_id = str_to_cat_id[searchterm]
                    for i, prefix in enumerate(prefixes(searchterm)):
                        if i >= self.max_prefix_len:
                            break
                        lookup[cat_id, i] = str_to_cat_id[prefix]
                except KeyError:
                    pass
        return lookup

    def _make_indptr(self, x):
        _, idx = np.unique(x, return_index=True)
        return np.append(idx, len(x))

    def initialize(self, next_batch):
        start = time.time()
        # Pull some initial metadata about the dataset that we need for scoring
        results = np.hstack(tf_run_all(self.tf_session, self.data_init_op, [
            next_batch['meta/page_id'],
            next_batch['meta/prefix']]))
        self.page_ids = results[0].ravel().astype(np.int64)
        # generate a 0-indexed id for every unqiue string in the tensorflow data
        prefixes = results[1].ravel()
        cats = pd.Series(prefixes).str.decode('utf8').astype('category').values
        self.max_cat_id = len(cats.categories)
        # Dict from string to it's id
        str_to_cat_id = {prefix: cat_id for cat_id, prefix in enumerate(cats.categories)}
        # 2d array from searchterm cat_id to cat_id's of all it's prefixes from
        # shortest to longest up to self.max_prefix_len. This is actually very
        # sparse, but it needs to be in numpy for numba.
        self.results_lookup_idx = self._build_results_lookup_indexes(str_to_cat_id)
        # Pre-sort into prefix groups and pre-calculate boundaries of
        # each prefix as in indptr.
        self.sort_idx = np.argsort(cats.codes)
        sorted_prefixes = cats.codes[self.sort_idx]
        self.page_ids = self.page_ids[self.sort_idx]
        self.prefix_indptr = self._make_indptr(sorted_prefixes)
        # Convert dataframes to ndarrays of ints for numba
        self.datasets = {k: self._simplify_df(df, str_to_cat_id)
                         for k, df in self.datasets.items()}
        # results are same size every evaluation, hold a buffer for them.
        rlb_shape = (len(self.prefix_indptr) - 1, self.top_k)
        self.results_lookup_buffer = np.empty(rlb_shape, dtype=self.page_ids.dtype)
        took = time.time() - start
        # Must be last step of initialization.
        self.initial_report = self.evaluate()
        self.initial_report.timing['initialize_sec'] = took

    @staticmethod
    @njit(parallel=True)
    def _build_results_lookup(scores, sort_idx, indptr, page_ids, result):
        """Build search result lists out of scores

        Takes the scores generated by the ranker under test and
        populates a result array with the page_ids of the top k
        results for each group identified by indptr.

        All input ndarrays except indptr must have the same first
        dimension. Result out must have a first dimension equal
        to the length of indptr - 1. The second dimension will
        be populated with rank order page_ids for each search.

        Parameters
        ----------
        scores : 1d float ndarray
        sort_idx : 1d int ndarray
            indices to re-order scores such that it is grouped
            by search term.
        indptr : 1d int ndarray
            points to search term result start indices in
            scores, page_ids, and result
        page_ids : 1d int ndarray
            associated page_id for each element in scores after
            it is sorted by sort_idx
        result : 2d float ndarray
            Output array containing top k page_ids for each
            group in indptr. k is set by the width passed in.

        Returns
        -------
        2d float ndarray
            Returns the result argument
        """
        top_k = result.shape[1]
        scores = scores.ravel()[sort_idx]
        for i in numba.prange(len(indptr) - 1):
            search_scores = scores[indptr[i]:indptr[i+1]]
            # argsorts always sorts low to high, so take last top_k
            # and reverse with ::-1
            top_k_idx = np.argsort(search_scores)[-top_k:][::-1]
            # argsort returned indices from the start of search_scores. to
            # index into page_ids shift by indptr[i]
            result[i, :len(top_k_idx)] = page_ids[indptr[i] + top_k_idx]
        return result

    @staticmethod
    @njit(parallel=True)
    def _eval_metric(clickthroughs, results_lookup, results_lookup_idx, metric):
        """Apply metric to clickthroughs

        Parameters
        ----------
        clickthroughs : np.ndarray
            return value of self._simplify_df
        results_lookup : np.ndarray
            return value of self._build_results_lookup
        results_lookup_idx : np.ndarray
            return value of self._build_results_lookup_indexes
        metric : callable
            Must be decorated with numba.njit. Will be called with two
            arguments. First a 2-d ndarray with the first dimension
            representing the character length of the prefix search and the
            second containing the page_id of the top-k results in rank order.
            The second argument is the clicked page_id. The metric must
            return a single float.

        Returns
        -------
        np.ndarray
            result of applying metric to each row of clickthroughs
        """
        out = np.empty(clickthroughs.shape[0], dtype=np.float32)
        for i in numba.prange(clickthroughs.shape[0]):
            cat_id, clickpage = clickthroughs[i]
            # list of cat_ids for prefix searches on cat_id
            # from shortest to longest
            results_list_idx = results_lookup_idx[cat_id]
            # the search results for all prefix searches of cat_id
            # up to self.max_prefix_len
            searchterm_results = results_lookup[results_list_idx]
            out[i] = metric(searchterm_results, clickpage)
        return out

    def evaluate(self):
        start = time.time()
        scores = np.vstack(tf_run_all(
            self.tf_session, self.data_init_op, self.score_op))
        took_generate = time.time() - start

        start = time.time()
        results = self._build_results_lookup(
            scores, self.sort_idx, self.prefix_indptr,
            self.page_ids, self.results_lookup_buffer)
        took_lookup = time.time() - start

        start = time.time()
        scores = {k: self._eval_metric(clickthroughs, results, self.results_lookup_idx, self.metric)
                  for k, clickthroughs in self.datasets.items()}
        took_eval = time.time() - start

        variables = self.tf_session.run(self.variables_ops)
        report = EvaluationReport(variables, scores, timing={
            'generate_sec': took_generate,
            'build_lookup_sec': took_lookup,
            'eval_sec': took_eval,
        })
        log.info('evaluate: total: %.4fs, gen: %.4fs lookup: %.4fs score: %.4fs',
                 report.took_sec, took_generate, took_lookup, took_eval)
        return report


class SensitivityAnalyzer(object):
    def __init__(self, tf_session, evaluator, variables, width=20):
        """Initialize Sensitivity Analyzer

        Parameters
        ----------
        tf_session : tf.Session
        evaluator : AutocompleteEvaluator
        variables : list of tf.Tensor or None
        width : Number of points to evaluate per variable
        """
        self.tf_session = tf_session
        self.evaluator = evaluator
        if not variables:
            variables = tf.get_collection(tf.GraphKeys.GLOBAL_VARIABLES)
        self.variables = variables
        self.width = width
        self.assign_var = tf.placeholder(shape=(), dtype=tf.float32)
        self.assign_ops = {var.name: var.assign(self.assign_var) for var in self.variables}

    def _assign_value(self, var_name, value):
        self.tf_session.run(self.assign_ops[var_name], {
            self.assign_var: value,
        })

    def evaluate(self):
        var_reports = {}
        for variable in self.variables:
            initial_value = self.tf_session.run(variable)
            start_value = max(np.abs(initial_value/100), .01)
            base_space = np.geomspace(start_value, np.abs(initial_value), self.width // 2)
            space = np.hstack((initial_value + base_space, [initial_value], initial_value - base_space))
            reports = []
            for test_value in space:
                self._assign_value(variable.name, test_value)
                reports.append(self.evaluator.evaluate())
            self._assign_value(variable.name, initial_value)
            var_reports[variable.name] = reports
        return SensitivityReport(var_reports)


class HyperoptOptimizer(object):
    def __init__(self, tf_session, evaluator, variables, train_dataset, seed):
        self.tf_session = tf_session
        self.evaluator = evaluator
        if not variables:
            variables = tf.get_collection(tf.GraphKeys.GLOBAL_VARIABLES)
        self.variables = {var.name: var for var in variables}
        self.train_dataset = train_dataset
        self.seed = seed
        self.assign_var = tf.placeholder(shape=(), dtype=tf.float32)
        self.assign_ops = {var.name: var.assign(self.assign_var) for var in self.variables.values()}

    def _assign_values(self, values):
        for var_name, value in values.items():
            self.tf_session.run(self.assign_ops[var_name], {
                self.assign_var: value,
            })

    def _evaluate(self, values):
        self._assign_values(values)
        report = self.evaluator.evaluate()
        return {
            'status': hyperopt.STATUS_OK,
            'loss': report[self.train_dataset].mean,
            'attachments': {'report': report},
        }

    def _make_tune_space(self, best_values):
        from hyperopt import hp
        tune_space = {}
        for k, v in best_values.items():
            if '/satu/' in k and k.endswith('/k:0'):
                var_low = 1.0
                var_high = 500.0
            elif '/satu/' in k and k.endswith('/a:0'):
                var_low = 0.1
                var_high = 10.0
            elif v >= 0:
                var_low = 0.001
                var_high = 1.0
            else:
                var_low = -1.0
                var_high = -0.001
            tune_space[k] = hp.uniform(k, var_low, var_high)
        return tune_space

    def minimize(self, restarts=2, epochs=600, tune_space=None):
        from hyperopt import fmin, tpe, Trials
        if tune_space is None:
            initial_values = self.tf_session.run(self.variables)
            tune_space = self._make_tune_space(initial_values)
        # TODO: This report structure has the downside of not writing
        # anything to disk until it's 100% complete.
        reports = []
        # Make minimize deterministic
        R = np.random.RandomState(self.seed)
        for restarts in range(restarts):
            trials = Trials()
            best = fmin(fn=self._evaluate,
                        space=tune_space,
                        algo=tpe.suggest,
                        max_evals=epochs,
                        trials=trials,
                        rstate=R)
            self._assign_values(best)
            reports.extend(trials.trial_attachments(t)['report'] for t in trials.trials)
        return self.evaluator.make_agg_report(reports)
