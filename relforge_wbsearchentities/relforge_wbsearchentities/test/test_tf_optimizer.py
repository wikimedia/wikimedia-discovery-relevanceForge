import json
import string

import numpy as np
import pytest

import relforge_wbsearchentities.tf_optimizer as opt


def test_score_query_doesnt_blow_up():
    all_results = np.asarray([
        [1, 2, 3],  # prefix len 1
        [2, 3, 4],  # prefix len 2
    ])
    clickpage = 3
    opt.score_query(all_results, clickpage)


def make_evaluation_report(R, datasets={'train': 100}):
    n_variables = R.randint(1, 20)
    variables = dict(zip(
        R.choice(list(string.ascii_lowercase), n_variables, replace=False),
        R.rand(n_variables)))
    scores = {k: R.rand(v) for k, v in datasets.items()}
    timing = {'took_s': R.rand()}
    return opt.EvaluationReport(variables, scores, timing)


def make_minimize_report(R):
    n_reports = R.randint(1, 10)
    num_hits = R.randint(10, 1000)
    num_observations = {
        'test': R.randint(10, 1000),
        'train': R.randint(10, 1000),
    }
    initial_report = make_evaluation_report(R, num_observations)
    reports = [make_evaluation_report(R, num_observations) for _ in range(n_reports)]
    return opt.MinimizeReport(initial_report, reports, num_observations, num_hits)


def make_sensitivity_report(R):
    n_var_reports = R.randint(2, 20)
    variables = R.choice(list(string.ascii_lowercase), n_var_reports, replace=False)
    reports_per_var = R.randint(2, 20)
    reports = {name: [make_evaluation_report(R) for _ in range(reports_per_var)]
               for name in variables}
    return opt.SensitivityReport(reports)


@pytest.mark.parametrize('make_report', [
    make_evaluation_report,
    make_minimize_report,
    make_sensitivity_report
])
def test_report_is_json_serializable(make_report):
    R = np.random.RandomState(seed=0)
    report = make_report(R)
    json.dumps(report.summary)
    json.dumps(report.to_dict(with_scores=False))
    json.dumps(report.to_dict(with_scores=True))
