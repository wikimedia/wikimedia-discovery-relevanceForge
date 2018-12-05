import pickle
import tempfile

import elasticsearch
import pytest

import relforge.cli_utils as cli


def test_iterate_pickle():
    input = [1, 2, 3]
    with tempfile.NamedTemporaryFile() as f:
        for x in input:
            pickle.dump(x, f, pickle.HIGHEST_PROTOCOL)
        f.flush()
        result = list(cli.iterate_pickle(f.name))
    assert input == result


def test_load_pkl():
    with tempfile.NamedTemporaryFile() as f:
        input = [1, 2, 3]
        for x in input:
            pickle.dump(x, f, pickle.HIGHEST_PROTOCOL)
        f.flush()
        result = cli.load_pkl(f.name)
    assert input[0] == result


def test_make_elasticsearch_args():
    args = cli.make_elasticsearch_args({'es': 'localhost:9200'})
    assert isinstance(args['es'], elasticsearch.Elasticsearch)


@pytest.mark.parametrize('min_val,max_val,raw_val,expected', [
    (0, 1, '0', 0),
    (0, 1, '.5', 0.5),
    (0, 1, '1', 1),
    (0, 1, '-1', None),
    (0, 1, '2', None),
    (0, 1, 'nan', None),
    (0, 1, '', None),
    (0, 1, 'asdf', None),
])
def test_bounded_float(min_val, max_val, raw_val, expected):
    try:
        result = cli.bounded_float(min_val, max_val)(raw_val)
    except ValueError:
        result = None
    assert expected == result


@pytest.mark.parametrize('raw_val,expected', [
    ('0', 0),
    ('1234', 1234),
    ('1.234', None),
    ('-1', None),
    ('', None),
    ('asdf', None),
])
def test_positive_int(raw_val, expected):
    try:
        result = cli.positive_int(raw_val)
    except ValueError:
        result = None
    assert expected == result
