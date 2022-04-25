import numpy as np
import re


RE_NAME_FIXER = re.compile(r'[^A-Za-z0-9_.\-/]')
# A common explain seen in various things that should be ignored.
MATCH_ALL_EXPLAIN = {'description': '*:*', 'value': 1.0, 'details': []}


def isclose(a, b, atol=1e-6):
    """Check if two values are reasonably close"""
    return np.isclose(a, b, atol=atol)


def name_fixer(name):
    return RE_NAME_FIXER.sub('-', str(name))


def join_name(a, b):
    # TODO: Applying name_fixer here is a quick hack
    if a is None and b is None:
        raise Exception('No names provided')
    if a is None or a == '':
        return b
    if b is None or b == '':
        return a
    return a + '/' + b


def clean_newlines(lucene_explain):
    # A few things like to put \n in the description which makes printing uglier
    return {
        'description': lucene_explain['description'].replace('\n', ''),
        'value': lucene_explain['value'],
        'details': [clean_newlines(child) for child in lucene_explain['details']],
    }


def print_explain(lucene_explain, indent=''):
    print('{}{}'.format(indent, lucene_explain['description']))
    if 'PerFieldSimilarity' not in lucene_explain['description']:
        for child in lucene_explain['details']:
            print_explain(child, indent + '\t')
