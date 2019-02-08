from collections import defaultdict
from copy import deepcopy
import pickle


import numpy as np
import pytest
import tensorflow as tf
from . import token_count_router_suite

from relforge_wbsearchentities.explain_parser.core import \
    BaseExplain, RootExplainParser
from relforge_wbsearchentities.explain_parser.bool import \
    BoolQueryExplainParser
from relforge_wbsearchentities.explain_parser.constant_score import \
    ConstantScoreExplainParser
from relforge_wbsearchentities.explain_parser.dis_max import \
    DisMaxQueryExplainParser
from relforge_wbsearchentities.explain_parser.function_score import (
    FLT_MAX, FunctionScoreExplainParser, FunctionScoreFilterExplainParser,
    FunctionScoreFunctionExplainParser, FunctionScoreScriptScoreExplainParser,
    FunctionScoreWeightExplainParser)
from relforge_wbsearchentities.explain_parser.match_all import \
    MATCH_ALL_EXPLAIN, MatchAllExplainParser
from relforge_wbsearchentities.explain_parser.match import \
    MatchQueryExplainParser, MultiMatchQueryExplainParser


TESTS = defaultdict(list)


def register_test(name, options, parser_factory, es_query, lucene_explain):
    def make_explain(verbose=False):
        es_query_copy = deepcopy(es_query)
        parser = parser_factory(es_query_copy, 'pytest')
        assert es_query_copy == es_query, "input query must not be modified"

        lucene_explain_copy = deepcopy(lucene_explain)
        explain = parser.parse(lucene_explain_copy)

        assert isinstance(explain, BaseExplain)
        assert lucene_explain_copy == lucene_explain, "explain must not be modified"

        # Basic requirements of an explain
        assert explain.parser_hash == hash(parser)
        assert not hasattr(explain, 'parser')
        assert explain.value == lucene_explain['value']
        if verbose:
            return parser, explain
        return explain

    defaults = (name, make_explain)
    TESTS['tensor_equiv'].append(defaults)
    TESTS['pickle'].append(defaults)
    TESTS['parser'].append(defaults + (options.get('is_complete', True),))
    if 'feature_values' in options:
        TESTS['feature_values'].append(defaults + (options['feature_values'],))
    if 'trainable' in options:
        TESTS['trainable'].append(defaults + (options['trainable'],))
    if 'merge' in options:
        TESTS['merge'].append(defaults + (options['merge'],))


# **********

register_test(
    'MatchAllExplainParser',
    {
        'feature_values': {
            'pytest/match_all': [1.0],
        },
        'trainable': {},
    },
    MatchAllExplainParser.from_query,
    es_query={},
    lucene_explain=MATCH_ALL_EXPLAIN,
)

# **********

query_FunctionScoreWeightExplainParser = 0.6
lucene_explain_FunctionScoreWeightExplainParser = {
    'value': 0.6,
    'description': 'weight',
    'details': [],
}

register_test(
    'FunctionScoreWeightExplainParser',
    {
        'feature_values': {},
        'trainable': [
            'pytest/weight:0'
        ],
    },
    FunctionScoreWeightExplainParser.from_query,
    query_FunctionScoreWeightExplainParser,
    lucene_explain_FunctionScoreWeightExplainParser,
)

# **********

query_FunctionScoreScriptScoreExplainParser = {
    "script": {
        "inline": "pow(doc['incoming_links'].value , 1) / ( pow(doc['incoming_links'].value, 1) + pow(100,1))",  # noqa: E501
        "lang": "expression"
    }
}

lucene_explain_FunctionScoreScriptScoreExplainParser = {
    "value": 0.8951782,
    "description": "script score function, computed with script:\"Script{" +
        "type=inline, lang='expression', idOrCode='pow(doc['" +  # noqa: E131
        "incoming_links'].value , 1) / ( pow(doc['incoming_links'].value, 1) + pow(100,1))" +
        "', options={}, params={}}\" and parameters: {}",
    "details": [
        {
            "value": 1,
            "description": "_score: ",
            "details": [
                MATCH_ALL_EXPLAIN,
            ]
        }
    ]
}

register_test(
    'FunctionScoreScriptScoreExplainParser',
    {
        'feature_values': {
            'pytest/satu/incoming_links': [854]
        },
        'trainable': [
            'pytest/satu/incoming_links/a:0',
            'pytest/satu/incoming_links/k:0',
        ],
    },
    FunctionScoreScriptScoreExplainParser.from_query,
    query_FunctionScoreScriptScoreExplainParser,
    lucene_explain_FunctionScoreScriptScoreExplainParser,
)

# **********

query_FunctionScoreFilterExplainParser = {
    "term": {
        "statement_keywords": "P31=Q42"
    }
}
lucene_explain_FunctionScoreFilterExplainParser = {
    "value": 1,
    "description": "match filter: statement_keywords:P31=Q42",
    "details": []
}

register_test(
    'FunctionScoreFilterExplainParser',
    {
        'feature_values': {
            'pytest/statement_keywords-P31-Q42': [1.0],
        },
        'trainable': [],
    },
    FunctionScoreFilterExplainParser.from_query,
    query_FunctionScoreFilterExplainParser,
    lucene_explain_FunctionScoreFilterExplainParser,
)

# **********

query_FunctionScoreFunctionExplainParser = {
    'script_score': query_FunctionScoreScriptScoreExplainParser,
    'filter': query_FunctionScoreFilterExplainParser,
    'weight': query_FunctionScoreWeightExplainParser,
}

lucene_explain_FunctionScoreFunctionExplainParser = {
    'value': 0.53710693,
    'description': 'function score, product of:',
    'details': [
        lucene_explain_FunctionScoreFilterExplainParser,
        {
            'value': 0.53710693,
            'description': 'product of:',
            'details': [
                lucene_explain_FunctionScoreScriptScoreExplainParser,
                lucene_explain_FunctionScoreWeightExplainParser,
            ]
        }
    ]
}

register_test(
    'FunctionScoreFunctionExplainParser',
    {
        'feature_values': {
            'pytest/statement_keywords-P31-Q42': [1.0],
            'pytest/satu/incoming_links': [854],
        },
        'trainable': [
            'pytest/weight:0',
            'pytest/satu/incoming_links/a:0',
            'pytest/satu/incoming_links/k:0',
        ],
    },
    FunctionScoreFunctionExplainParser.from_query,
    query_FunctionScoreFunctionExplainParser,
    lucene_explain_FunctionScoreFunctionExplainParser,
)

# **********

query_FunctionScoreFunctionExplainParser_2 = {
    'filter': query_FunctionScoreFilterExplainParser,
    'weight': query_FunctionScoreWeightExplainParser,
}

lucene_explain_FunctionScoreFunctionExplainParser_2 = {
    'value': lucene_explain_FunctionScoreWeightExplainParser['value'],
    'description': 'function score, product of:',
    'details': [
        lucene_explain_FunctionScoreFilterExplainParser,
        {
            'value': lucene_explain_FunctionScoreWeightExplainParser['value'],
            'description': 'product of:',
            'details': [
                {
                    'value': 1,
                    'description': 'constant score 1.0 - no function provided',
                    'details': [],
                },
                lucene_explain_FunctionScoreWeightExplainParser,
            ]
        }
    ]
}
register_test(
    'FunctionScoreFunctionExplainParser_2',
    {
        'feature_values': {
            'pytest/statement_keywords-P31-Q42': [1.0],
        },
        'trainable': ['pytest/statement_keywords-P31-Q42/weight:0'],
    },
    FunctionScoreFunctionExplainParser.from_query,
    query_FunctionScoreFunctionExplainParser_2,
    lucene_explain_FunctionScoreFunctionExplainParser_2,
)

# **********

query_FunctionScoreExplainParser = {
    'score_mode': 'sum',
    'functions': [
        query_FunctionScoreFunctionExplainParser
    ],
}

lucene_explain_FunctionScoreExplainParser = {
    'value': lucene_explain_FunctionScoreFunctionExplainParser['value'],
    'description': 'function score, product of:',
    'details': [
        MATCH_ALL_EXPLAIN,
        {
            'value': lucene_explain_FunctionScoreFunctionExplainParser['value'],
            'description': 'min of:',
            'details': [
                {
                    'value': lucene_explain_FunctionScoreFunctionExplainParser['value'],
                    'description': 'function score, score mode [sum]',
                    'details': [
                        lucene_explain_FunctionScoreFunctionExplainParser,
                    ],
                },
                {
                    'value': FLT_MAX,
                    'description': 'maxBoost',
                    'details': [],
                }
            ]
        }
    ]
}

register_test(
    'FunctionScoreExplainParser',
    {
        'feature_values': {
            'pytest/function_score/match_all': [1.0],
            'pytest/function_score/no_function_match': [0.0],
            'pytest/function_score/0/statement_keywords-P31-Q42': [1.0],
            'pytest/function_score/0/satu/incoming_links': [854],
        },
        'trainable': [
            'pytest/function_score/0/weight:0',
            'pytest/function_score/0/satu/incoming_links/a:0',
            'pytest/function_score/0/satu/incoming_links/k:0',
        ],
    },
    FunctionScoreExplainParser.from_query,
    query_FunctionScoreExplainParser,
    lucene_explain_FunctionScoreExplainParser,
)

# **********

query_FunctionScoreExplainParser_boost_mode_sum = {
    'score_mode': 'sum',
    'boost_mode': 'sum',
    'functions': [
        query_FunctionScoreFunctionExplainParser
    ],
}

lucene_explain_FunctionScoreExplainParser__boost_mode_sum = {
    'value': lucene_explain_FunctionScoreFunctionExplainParser['value'] + MATCH_ALL_EXPLAIN['value'],
    'description': 'sum of',
    'details': [
        MATCH_ALL_EXPLAIN,
        {
            'value': lucene_explain_FunctionScoreFunctionExplainParser['value'],
            'description': 'min of:',
            'details': [
                {
                    'value': lucene_explain_FunctionScoreFunctionExplainParser['value'],
                    'description': 'function score, score mode [sum]',
                    'details': [
                        lucene_explain_FunctionScoreFunctionExplainParser,
                    ],
                },
                {
                    'value': FLT_MAX,
                    'description': 'maxBoost',
                    'details': [],
                }
            ]
        }
    ]
}

register_test(
    'FunctionScoreExplainParser boost_mode sum',
    {
        'feature_values': {
            'pytest/function_score/match_all': [1.0],
            'pytest/function_score/no_function_match': [0.0],
            'pytest/function_score/0/statement_keywords-P31-Q42': [1.0],
            'pytest/function_score/0/satu/incoming_links': [854],
        },
        'trainable': [
            'pytest/function_score/0/weight:0',
            'pytest/function_score/0/satu/incoming_links/a:0',
            'pytest/function_score/0/satu/incoming_links/k:0',
        ],
    },
    FunctionScoreExplainParser.from_query,
    query_FunctionScoreExplainParser_boost_mode_sum,
    lucene_explain_FunctionScoreExplainParser__boost_mode_sum,
)

# **********

lucene_explain_FunctionScoreExplainParser_no_function_match = {
    'value': 1.0,
    'description': 'function score, product of:',
    'details': [
        MATCH_ALL_EXPLAIN,
        {
            'value': 1.0,
            'description': 'min of:',
            'details': [
                {
                    'value': 1.0,
                    'description': 'No function matched',
                    'details': [],
                },
                {
                    'value': FLT_MAX,
                    'description': 'maxBoost',
                    'details': [],
                }
            ]
        }
    ]
}

register_test(
    'FunctionScoreExplainParser no function match',
    {
        'feature_values': {
            'pytest/function_score/match_all': [1.0],
            'pytest/function_score/no_function_match': [1.0],
        },
        'trainable': [],
        'is_complete': False,
        'merge': [lucene_explain_FunctionScoreExplainParser],
    },
    FunctionScoreExplainParser.from_query,
    query_FunctionScoreExplainParser,
    lucene_explain_FunctionScoreExplainParser_no_function_match,
)

# **********

query_ConstantScoreExplainParser = {
    "filter": {"match": {"labels.en.prefix": "{{query_string}}"}},
    "boost": 1.1
}

lucene_explain_ConstantScoreExplainParser = {
    'value': 1.1,
    'description': 'ConstantScore(labels.en.prefix:albert), product of:',
    'details': [
        {
            'value': 1.1,
            'description': 'boost',
            'details': [],
        },
        {
            'value': 1,
            'description': 'queryNorm',
            'details': [],
        }
    ]
}

register_test(
    'ConstantScoreExplainParser',
    {
        'feature_values': {
            'pytest/constant_score/labels.en.prefix': [1.0],
        },
        'trainable': [
            'pytest/constant_score/labels.en.prefix/boost:0',
        ],
    },
    ConstantScoreExplainParser.from_query,
    query_ConstantScoreExplainParser,
    lucene_explain_ConstantScoreExplainParser,
)

# **********

query_MatchQueryExplainParser = {
    'labels.en.near_match': '{{query_string}}'
}

lucene_explain_tfNorm = {
    "value": 1,
    "description": "tfNorm, computed as (freq * (k1 + 1)) / (freq + k1) from:",
    "details": [
        {
            "value": 1,
            "description": "termFreq=1.0",
            "details": []
        },
        {
            "value": 1.2,
            "description": "parameter k1",
            "details": []
        },
        {
            "value": 0,
            "description": "parameter b (norms omitted for field)",
            "details": []
        }
    ]
}

lucene_explain_idf = {
    "value": 14.335771,
    "description": "idf, computed as log(1 + (docCount - docFreq + 0.5) / (docFreq + 0.5)) from:",
    "details": [
        {
            "value": 1,
            "description": "docFreq",
            "details": []
        },
        {
            "value": 2523696,
            "description": "docCount",
            "details": []
        }
    ]
}

lucene_explain_MatchQueryExplainParser = {
    "value": 14.335771,
    "description": "weight(labels.en.near_match:albert in 1328743) [PerFieldSimilarity], result of:",  # noqa: E501
    "details": [
        {
            "value": 14.335771,
            "description": "score(doc=1328743,freq=1.0 = termFreq=1.0), product of:",
            "details": [
                lucene_explain_idf,
                lucene_explain_tfNorm,
            ]
        }
    ]
}

register_test(
    'MatchQueryExplainParser',
    {
        'feature_values': {
            'pytest/labels.en.near_match/idf': [14.335771],
            'pytest/labels.en.near_match/termFreq': [1.0],
        },
        'trainable': [
            'pytest/labels.en.near_match/k1:0',
            'pytest/labels.en.near_match/boost:0',
        ],
    },
    MatchQueryExplainParser.from_query,
    query_MatchQueryExplainParser,
    lucene_explain_MatchQueryExplainParser,
)

# **********

query_MatchQueryExplainParser_w_norms = {
    "text": "{{query_string}}",
}

lucene_explain_MatchQueryExplainParser_zamboni = {
    "value": 20.084152,
    "description": "weight(text:zamboni in 236686) [PerFieldSimilarity], result of:",
    "details": [
        {
            "value": 20.084152,
            "description": "score(doc=236686,freq=11.0 = termFreq=11.0\n), product of:",
            "details": [
                {
                    "value": 9.5103245,
                    "description": "idf, computed as log(1 + (docCount - docFreq + 0.5) / (docFreq + 0.5)) from:",
                    "details": [
                        {
                            "value": 72,
                            "description": "docFreq",
                            "details": []
                        },
                        {
                            "value": 978631,
                            "description": "docCount",
                            "details": []
                        }
                    ]
                },
                {
                    "value": 2.1118262,
                    "description": "tfNorm, computed as (freq * (k1 + 1)) / (freq + k1 * (1 - b + b * fieldLength / avgFieldLength)) from:",  # noqa: E501
                    "details": [
                        {
                            "value": 11,
                            "description": "termFreq=11.0",
                            "details": []
                        },
                        {
                            "value": 1.2,
                            "description": "parameter k1",
                            "details": []
                        },
                        {
                            "value": 0.75,
                            "description": "parameter b",
                            "details": []
                        },
                        {
                            "value": 472.33994,
                            "description": "avgFieldLength",
                            "details": []
                        },
                        {
                            "value": 83.591835,
                            "description": "fieldLength",
                            "details": []
                        }
                    ]
                }
            ]
        }
    ]
}

register_test(
    'MatchQueryExplainParser_w_norms',
    {
        'feature_values': {
            'pytest/text/idf': [9.5103245],
            'pytest/text/termFreq': [11.0],
            'pytest/text/fieldLength': [83.591835],
        },
        'trainable': [
            'pytest/text/k1:0',
            'pytest/text/b:0',
            'pytest/text/boost:0',
        ],
    },
    MatchQueryExplainParser.from_query,
    query_MatchQueryExplainParser_w_norms,
    lucene_explain_MatchQueryExplainParser_zamboni,
)

# **********

query_MatchQueryExplainParser_multi_term = {
    "text": "{{query_string}}"
}

lucene_explain_MatchQueryExplainParser_ice = {
    "value": 7.68435,
    "description": "weight(text:ice in 377572) [PerFieldSimilarity], result of:",
    "details": [
        {
            "value": 7.68435,
            "description": "score(doc=377572,freq=27.0 = termFreq=27.0\n), product of:",
            "details": [
                {
                    "value": 3.78397,
                    "description": "idf, computed as log(1 + (docCount - docFreq + 0.5) / (docFreq + 0.5)) from:",
                    "details": [
                        {
                            "value": 22259,
                            "description": "docFreq",
                            "details": []
                        },
                        {
                            "value": 979202,
                            "description": "docCount",
                            "details": []
                        }
                    ]
                },
                {
                    "value": 2.0307639,
                    "description": "tfNorm, computed as (freq * (k1 + 1)) / (freq + k1 * (1 - b + b * fieldLength / avgFieldLength)) from:",  # noqa: E501
                    "details": [
                        {
                            "value": 27,
                            "description": "termFreq=27.0",
                            "details": []
                        },
                        {
                            "value": 1.2,
                            "description": "parameter k1",
                            "details": []
                        },
                        {
                            "value": 0.75,
                            "description": "parameter b",
                            "details": []
                        },
                        {
                            "value": 472.59653,
                            "description": "avgFieldLength",
                            "details": []
                        },
                        {
                            "value": 1024,
                            "description": "fieldLength",
                            "details": []
                        }
                    ]
                }
            ]
        }
    ]
}

lucene_explain_MatchQueryExplainParser_multi_term = {
    "value": 27.768225,
    "description": "sum of:",
    "details": [
        lucene_explain_MatchQueryExplainParser_zamboni,
        lucene_explain_MatchQueryExplainParser_ice
    ]
}

register_test(
    'MatchQueryExplainParser_multi_term',
    {
        'feature_values': {
            'pytest/text/idf': [9.5103245, 3.78397],
            'pytest/text/fieldLength': [83.591835, 1024.0],
            'pytest/text/termFreq': [11.0, 27.0],
        },
        'trainable': [
            'pytest/text/k1:0',
            'pytest/text/b:0',
            'pytest/text/boost:0',
        ],
    },
    MatchQueryExplainParser.from_query,
    query_MatchQueryExplainParser_multi_term,
    lucene_explain_MatchQueryExplainParser_multi_term,
)

# **********

query_MatchQueryExplainParser_suggest_synonym = {
    "suggest": "{{query_string}}",
}

lucene_explain_MatchQueryExplainParser_suggest_synonym_zamboni_ice = {
    "value": 13.24331,
    "description": "weight(Synonym(suggest:zamboni suggest:zamboni ice) in 170532) [PerFieldSimilarity], result of:",
    "details": [
        {
            "value": 13.24331,
            "description": "score(doc=170532,freq=1.0 = termFreq=1.0\n), product of:",
            "details": [
                {
                    "value": 12.033235,
                    "description": "idf, computed as log(1 + (docCount - docFreq + 0.5) / (docFreq + 0.5)) from:",
                    "details": [
                        {
                            "value": 5,
                            "description": "docFreq",
                            "details": []
                        },
                        {
                            "value": 925400,
                            "description": "docCount",
                            "details": []
                        }
                    ]
                },
                {
                    "value": 1.1005611,
                    "description": "tfNorm, computed as (freq * (k1 + 1)) / (freq + k1 * (1 - b + b * fieldLength / avgFieldLength)) from:",  # noqa: E501
                    "details": [
                        {
                            "value": 1,
                            "description": "termFreq=1.0",
                            "details": []
                        },
                        {
                            "value": 1.2,
                            "description": "parameter k1",
                            "details": []
                        },
                        {
                            "value": 0.3,
                            "description": "parameter b",
                            "details": []
                        },
                        {
                            "value": 16.102627,
                            "description": "avgFieldLength",
                            "details": []
                        },
                        {
                            "value": 7.111111,
                            "description": "fieldLength",
                            "details": []
                        }
                    ]
                }
            ]
        }
    ]
}

lucene_explain_MatchQueryExplainParser_suggest_ice = {
    "value": 9.411105,
    "description": "weight(suggest:ice in 170532) [PerFieldSimilarity], result of:",
    "details": [
        {
            "value": 9.411105,
            "description": "score(doc=170532,freq=2.0 = termFreq=2.0\n), product of:",
            "details": [
                {
                    "value": 6.4144816,
                    "description": "idf, computed as log(1 + (docCount - docFreq + 0.5) / (docFreq + 0.5)) from:",
                    "details": [
                        {
                            "value": 1515,
                            "description": "docFreq",
                            "details": []
                        },
                        {
                            "value": 925400,
                            "description": "docCount",
                            "details": []
                        }
                    ]
                },
                {
                    "value": 1.4671654,
                    "description": "tfNorm, computed as (freq * (k1 + 1)) / (freq + k1 * (1 - b + b * fieldLength / avgFieldLength)) from:",  # noqa: E501
                    "details": [
                        {
                            "value": 2,
                            "description": "termFreq=2.0",
                            "details": []
                        },
                        {
                            "value": 1.2,
                            "description": "parameter k1",
                            "details": []
                        },
                        {
                            "value": 0.3,
                            "description": "parameter b",
                            "details": []
                        },
                        {
                            "value": 16.102627,
                            "description": "avgFieldLength",
                            "details": []
                        },
                        {
                            "value": 7.111111,
                            "description": "fieldLength",
                            "details": []
                        }
                    ]
                }
            ]
        }
    ]
}


lucene_explain_MatchQueryExplainParser_suggest_synonym = {
    'value': 22.654415,
    'description': 'sum of:',
    'details': [
        lucene_explain_MatchQueryExplainParser_suggest_synonym_zamboni_ice,
        lucene_explain_MatchQueryExplainParser_suggest_ice,
    ]
}

register_test(
    'MatchQueryExplainParser_suggest_synonym',
    {
        'feature_values': {
            'pytest/suggest/idf': [12.033235, 6.4144816],
            'pytest/suggest/fieldLength': [7.111111, 7.111111],
            'pytest/suggest/termFreq': [1.0, 2.0],
        },
        'trainable': [
            'pytest/suggest/b:0',
            'pytest/suggest/k1:0',
            'pytest/suggest/boost:0',
        ],
    },
    MatchQueryExplainParser.from_query,
    query_MatchQueryExplainParser_suggest_synonym,
    lucene_explain_MatchQueryExplainParser_suggest_synonym)

######

query_MultiMatchQueryExplainParser = {
    "query": "cat",
    "boost": 0.5,
    "minimum_should_match": 1,
    "type": "most_fields",
    "fields": [
        "title.plain^1",
        "title^3"
    ]
}


lucene_explain_MultiMatchQueryExplainParser = {
    "value": 22.40433,
    "description": "sum of:",
    "details": [
        {
            "value": 17.065096,
            "description": "weight(title:cat in 201306) [PerFieldSimilarity], result of:",
            "details": [
                {
                    "value": 17.065096,
                    "description": "score(doc=201306,freq=2.0 = termFreq=2.0\n), product of:",
                    "details": [
                        {
                            "value": 1.5,
                            "description": "boost",
                            "details": []
                        },
                        {
                            "value": 8.096071,
                            "description": "idf, computed as log(1 + (docCount - docFreq + 0.5) / (docFreq + 0.5)) from:",  # noqa: E501
                            "details": [
                                {
                                    "value": 286,
                                    "description": "docFreq",
                                    "details": []
                                },
                                {
                                    "value": 940163,
                                    "description": "docCount",
                                    "details": []
                                }
                            ]
                        },
                        {
                            "value": 1.4052162,
                            "description": "tfNorm, computed as (freq * (k1 + 1)) / (freq + k1 * (1 - b + b * fieldLength / avgFieldLength)) from:",  # noqa: E501
                            "details": [
                                {
                                    "value": 2,
                                    "description": "termFreq=2.0",
                                    "details": []
                                },
                                {
                                    "value": 1.2,
                                    "description": "parameter k1",
                                    "details": []
                                },
                                {
                                    "value": 0.75,
                                    "description": "parameter b",
                                    "details": []
                                },
                                {
                                    "value": 2.7719269,
                                    "description": "avgFieldLength",
                                    "details": []
                                },
                                {
                                    "value": 2.56,
                                    "description": "fieldLength",
                                    "details": []
                                }
                            ]
                        }
                    ]
                }
            ]
        },
        {
            "value": 5.339233,
            "description": "weight(title.plain:cat in 201306) [PerFieldSimilarity], result of:",
            "details": [
                {
                    "value": 5.339233,
                    "description": "score(doc=201306,freq=2.0 = termFreq=2.0\n), product of:",
                    "details": [
                        {
                            "value": 0.5,
                            "description": "boost",
                            "details": []
                        },
                        {
                            "value": 8.498954,
                            "description": "idf, computed as log(1 + (docCount - docFreq + 0.5) / (docFreq + 0.5)) from:",  # noqa: E501
                            "details": [
                                {
                                    "value": 191,
                                    "description": "docFreq",
                                    "details": []
                                },
                                {
                                    "value": 940193,
                                    "description": "docCount",
                                    "details": []
                                }
                            ]
                        },
                        {
                            "value": 1.2564447,
                            "description": "tfNorm, computed as (freq * (k1 + 1)) / (freq + k1 * (1 - b + b * fieldLength / avgFieldLength)) from:",  # noqa: E501
                            "details": [
                                {
                                    "value": 2,
                                    "description": "termFreq=2.0",
                                    "details": []
                                },
                                {
                                    "value": 1.2,
                                    "description": "parameter k1",
                                    "details": []
                                },
                                {
                                    "value": 0.75,
                                    "description": "parameter b",
                                    "details": []
                                },
                                {
                                    "value": 2.9951456,
                                    "description": "avgFieldLength",
                                    "details": []
                                },
                                {
                                    "value": 4,
                                    "description": "fieldLength",
                                    "details": []
                                }
                            ]
                        }
                    ]
                }
            ]
        }
    ]
}


register_test(
    'MultiMatchQueryExplainParser',
    {},
    MultiMatchQueryExplainParser.from_query,
    query_MultiMatchQueryExplainParser,
    lucene_explain_MultiMatchQueryExplainParser,
)

######

query_MultiMatchQueryExplainParser_multi_term = dict(query_MultiMatchQueryExplainParser, query="cat dog")

lucene_explain_MultiMatchQueryExplainParser_multi_term = {
    "value": 32.0077,
    "description": "sum of:",
    "details": [
        {
            "value": 24.761276,
            "description": "sum of:",
            "details": [
                {
                    "value": 12.291628,
                    "description": "weight(title:cat in 31225) [PerFieldSimilarity], result of:",
                    "details": [
                        {
                            "value": 12.291628,
                            "description": "score(doc=31225,freq=1.0 = termFreq=1.0\n), product of:",
                            "details": [
                                {
                                    "value": 1.5,
                                    "description": "boost",
                                    "details": []
                                },
                                {
                                    "value": 7.9428716,
                                    "description": "idf, computed as log(1 + (docCount - docFreq + 0.5) / (docFreq + 0.5)) from:",  # noqa: E501
                                    "details": [
                                        {
                                            "value": 386,
                                            "description": "docFreq",
                                            "details": []
                                        },
                                        {
                                            "value": 1088164,
                                            "description": "docCount",
                                            "details": []
                                        }
                                    ]
                                },
                                {
                                    "value": 1.0316695,
                                    "description": "tfNorm, computed as (freq * (k1 + 1)) / (freq + k1 * (1 - b + b * fieldLength / avgFieldLength)) from:",  # noqa: E501
                                    "details": [
                                        {
                                            "value": 1,
                                            "description": "termFreq=1.0",
                                            "details": []
                                        },
                                        {
                                            "value": 1.2,
                                            "description": "parameter k1",
                                            "details": []
                                        },
                                        {
                                            "value": 0.75,
                                            "description": "parameter b",
                                            "details": []
                                        },
                                        {
                                            "value": 2.7676811,
                                            "description": "avgFieldLength",
                                            "details": []
                                        },
                                        {
                                            "value": 2.56,
                                            "description": "fieldLength",
                                            "details": []
                                        }
                                    ]
                                }
                            ]
                        }
                    ]
                },
                {
                    "value": 12.469648,
                    "description": "weight(title:dog in 31225) [PerFieldSimilarity], result of:",
                    "details": [
                        {
                            "value": 12.469648,
                            "description": "score(doc=31225,freq=1.0 = termFreq=1.0\n), product of:",
                            "details": [
                                {
                                    "value": 1.5,
                                    "description": "boost",
                                    "details": []
                                },
                                {
                                    "value": 8.057909,
                                    "description": "idf, computed as log(1 + (docCount - docFreq + 0.5) / (docFreq + 0.5)) from:",  # noqa: E501
                                    "details": [
                                        {
                                            "value": 344,
                                            "description": "docFreq",
                                            "details": []
                                        },
                                        {
                                            "value": 1088164,
                                            "description": "docCount",
                                            "details": []
                                        }
                                    ]
                                },
                                {
                                    "value": 1.0316695,
                                    "description": "tfNorm, computed as (freq * (k1 + 1)) / (freq + k1 * (1 - b + b * fieldLength / avgFieldLength)) from:",  # noqa: E501
                                    "details": [
                                        {
                                            "value": 1,
                                            "description": "termFreq=1.0",
                                            "details": []
                                        },
                                        {
                                            "value": 1.2,
                                            "description": "parameter k1",
                                            "details": []
                                        },
                                        {
                                            "value": 0.75,
                                            "description": "parameter b",
                                            "details": []
                                        },
                                        {
                                            "value": 2.7676811,
                                            "description": "avgFieldLength",
                                            "details": []
                                        },
                                        {
                                            "value": 2.56,
                                            "description": "fieldLength",
                                            "details": []
                                        }
                                    ]
                                }
                            ]
                        }
                    ]
                }
            ]
        },
        {
            "value": 7.2464256,
            "description": "sum of:",
            "details": [
                {
                    "value": 3.689394,
                    "description": "weight(title.plain:cat in 31225) [PerFieldSimilarity], result of:",
                    "details": [
                        {
                            "value": 3.689394,
                            "description": "score(doc=31225,freq=1.0 = termFreq=1.0\n), product of:",
                            "details": [
                                {
                                    "value": 0.5,
                                    "description": "boost",
                                    "details": []
                                },
                                {
                                    "value": 8.400816,
                                    "description": "idf, computed as log(1 + (docCount - docFreq + 0.5) / (docFreq + 0.5)) from:",  # noqa: E501
                                    "details": [
                                        {
                                            "value": 244,
                                            "description": "docFreq",
                                            "details": []
                                        },
                                        {
                                            "value": 1088194,
                                            "description": "docCount",
                                            "details": []
                                        }
                                    ]
                                },
                                {
                                    "value": 0.8783418,
                                    "description": "tfNorm, computed as (freq * (k1 + 1)) / (freq + k1 * (1 - b + b * fieldLength / avgFieldLength)) from:",  # noqa: E501
                                    "details": [
                                        {
                                            "value": 1,
                                            "description": "termFreq=1.0",
                                            "details": []
                                        },
                                        {
                                            "value": 1.2,
                                            "description": "parameter k1",
                                            "details": []
                                        },
                                        {
                                            "value": 0.75,
                                            "description": "parameter b",
                                            "details": []
                                        },
                                        {
                                            "value": 2.9882474,
                                            "description": "avgFieldLength",
                                            "details": []
                                        },
                                        {
                                            "value": 4,
                                            "description": "fieldLength",
                                            "details": []
                                        }
                                    ]
                                }
                            ]
                        }
                    ]
                },
                {
                    "value": 3.5570314,
                    "description": "weight(title.plain:dog in 31225) [PerFieldSimilarity], result of:",
                    "details": [
                        {
                            "value": 3.5570314,
                            "description": "score(doc=31225,freq=1.0 = termFreq=1.0\n), product of:",
                            "details": [
                                {
                                    "value": 0.5,
                                    "description": "boost",
                                    "details": []
                                },
                                {
                                    "value": 8.099424,
                                    "description": "idf, computed as log(1 + (docCount - docFreq + 0.5) / (docFreq + 0.5)) from:",  # noqa: E501
                                    "details": [
                                        {
                                            "value": 330,
                                            "description": "docFreq",
                                            "details": []
                                        },
                                        {
                                            "value": 1088194,
                                            "description": "docCount",
                                            "details": []
                                        }
                                    ]
                                },
                                {
                                    "value": 0.8783418,
                                    "description": "tfNorm, computed as (freq * (k1 + 1)) / (freq + k1 * (1 - b + b * fieldLength / avgFieldLength)) from:",  # noqa: E501
                                    "details": [
                                        {
                                            "value": 1,
                                            "description": "termFreq=1.0",
                                            "details": []
                                        },
                                        {
                                            "value": 1.2,
                                            "description": "parameter k1",
                                            "details": []
                                        },
                                        {
                                            "value": 0.75,
                                            "description": "parameter b",
                                            "details": []
                                        },
                                        {
                                            "value": 2.9882474,
                                            "description": "avgFieldLength",
                                            "details": []
                                        },
                                        {
                                            "value": 4,
                                            "description": "fieldLength",
                                            "details": []
                                        }
                                    ]
                                }
                            ]
                        }
                    ]
                }
            ]
        }
    ]
}


register_test(
    'MultiMatchQueryExplainParser_multi_term',
    {
        "feature_values": {
            'pytest/title.plain/idf': [8.400816, 8.099424],
            'pytest/title.plain/fieldLength': [4.0, 4.0],
            'pytest/title.plain/termFreq': [1.0, 1.0],
            'pytest/title/idf': [7.9428716, 8.057909],
            'pytest/title/fieldLength': [2.56, 2.56],
            'pytest/title/termFreq': [1.0, 1.0]
        },
        "trainable": [
            'pytest/title/boost:0',
            'pytest/title/b:0',
            'pytest/title/k1:0',
            'pytest/title.plain/boost:0',
            'pytest/title.plain/b:0',
            'pytest/title.plain/k1:0',
        ],
    },
    MultiMatchQueryExplainParser.from_query,
    query_MultiMatchQueryExplainParser_multi_term,
    lucene_explain_MultiMatchQueryExplainParser_multi_term,
)

######

query_DisMaxQueryExplainParser = {
    'tie_breaker': 0,
    'queries': [
        {'constant_score': query_ConstantScoreExplainParser},
        {'match': query_MatchQueryExplainParser},
    ],
}

lucene_explain_DisMaxQueryExplainParser = {
    'value': max(lucene_explain_ConstantScoreExplainParser['value'],
                 lucene_explain_MatchQueryExplainParser['value']),
    'description': 'max of:',
    'details': [
        lucene_explain_ConstantScoreExplainParser,
        lucene_explain_MatchQueryExplainParser,
    ]
}

register_test(
    'DisMaxQueryExplainParser',
    {
        'trainable': [
            'pytest/dismax/tie_breaker:0',
            'pytest/dismax/0/constant_score/labels.en.prefix/boost:0',
            'pytest/dismax/1/labels.en.near_match/k1:0',
            'pytest/dismax/1/labels.en.near_match/boost:0',
        ],
    },
    DisMaxQueryExplainParser.from_query,
    query_DisMaxQueryExplainParser,
    lucene_explain_DisMaxQueryExplainParser,
)

# **********

query_DisMaxQueryExplainParser_2 = {
    'tie_breaker': 0.11,
    'queries': [
        {'constant_score': query_ConstantScoreExplainParser},
        {'match': query_MatchQueryExplainParser},
    ],
}

lucene_explain_DisMaxQueryExplainParser_2 = {
    'value': max(lucene_explain_ConstantScoreExplainParser['value'],
                 lucene_explain_MatchQueryExplainParser['value']) +
             0.11 * min(lucene_explain_ConstantScoreExplainParser['value'],  # noqa: E131
                        lucene_explain_MatchQueryExplainParser['value']),
    'description': 'max plus 0.11 times others of:',
    'details': [
        lucene_explain_ConstantScoreExplainParser,
        lucene_explain_MatchQueryExplainParser,
    ],
}

register_test(
    'DisMaxQueryExplainParser_2',
    {
        'feature_values': {
            'pytest/dismax/0/constant_score/labels.en.prefix': [1.0],
            'pytest/dismax/1/labels.en.near_match/idf': [14.335771],
            'pytest/dismax/1/labels.en.near_match/termFreq': [1.0],
        },
        'trainable': [
            'pytest/dismax/tie_breaker:0',
            'pytest/dismax/0/constant_score/labels.en.prefix/boost:0',
            'pytest/dismax/1/labels.en.near_match/k1:0',
            'pytest/dismax/1/labels.en.near_match/boost:0',
        ],
    },
    DisMaxQueryExplainParser.from_query,
    query_DisMaxQueryExplainParser_2,
    lucene_explain_DisMaxQueryExplainParser_2,
)

# **********

query_BoolQueryExplainParser = {
    'filter': [{'match': query_MatchQueryExplainParser}],
    'should': [
        {'constant_score': query_ConstantScoreExplainParser},
        {'dis_max': query_DisMaxQueryExplainParser},
    ]
}

lucene_explain_BoolQueryExplainParser = {
    'value': lucene_explain_ConstantScoreExplainParser['value'] +
             lucene_explain_DisMaxQueryExplainParser['value'],  # noqa: E131
    'description': 'sum of:',
    'details': [
        lucene_explain_ConstantScoreExplainParser,
        lucene_explain_DisMaxQueryExplainParser,
        {
            'value': 0,
            'description': 'match on required clause, product of:',
            'details': [
                {
                    'value': 0,
                    'description': '# clause',
                    'details': [],
                },
                {
                    'value': 1.0,
                    'description': 'labels.en.near_match:albert, product of:',
                    'details': [],  # more, but not worth duplicating
                }
            ]
        }
    ],
}

register_test(
    'BoolQueryExplainParser',
    {
        'feature_values': {
            'pytest/constant_score/labels.en.prefix': [1.0],
            'pytest/dismax/0/constant_score/labels.en.prefix': [1.0],
            'pytest/dismax/1/labels.en.near_match/idf': [14.335771],
            'pytest/dismax/1/labels.en.near_match/termFreq': [1.0],
        },
        'trainable': [
            'pytest/constant_score/labels.en.prefix/boost:0',
            'pytest/dismax/tie_breaker:0',
            'pytest/dismax/0/constant_score/labels.en.prefix/boost:0',
            'pytest/dismax/1/labels.en.near_match/k1:0',
            'pytest/dismax/1/labels.en.near_match/boost:0',
        ],
    },
    BoolQueryExplainParser.from_query,
    query_BoolQueryExplainParser,
    lucene_explain_BoolQueryExplainParser,
)


# **********

query_BoolQueryExplainParser_2 = {
    'should': [
        {'bool': query_BoolQueryExplainParser},
        {'function_score': query_FunctionScoreExplainParser},
    ]
}

lucene_explain_BoolQueryExplainParser_2 = {
    'value': lucene_explain_BoolQueryExplainParser['value'] +
             lucene_explain_FunctionScoreExplainParser['value'],  # noqa: E131
    'description': 'sum of:',
    'details': [
        lucene_explain_BoolQueryExplainParser,
        lucene_explain_FunctionScoreExplainParser,
    ],
}

register_test(
    'BoolQueryExplainParser_2', {},
    BoolQueryExplainParser.from_query,
    query_BoolQueryExplainParser_2,
    lucene_explain_BoolQueryExplainParser_2,
)

# **********


query_BoolQueryExplainParser_3 = {
    'filter': [
        {'match': query_MatchQueryExplainParser},
    ]
}

lucene_explain_BoolQueryExplainParser_3 = {
    'value': 0.0,
    'description': 'sum of:',
    'details': [
        {
            'value': 0.0,
            'description': 'match on required clause, product of:',
            'details': [
                {
                    'value': 0.0,
                    'description': '# clause',
                    'details': []
                },
                dict(lucene_explain_MatchQueryExplainParser, value=1.0),
            ]
        }
    ]
}

register_test(
    'BoolQueryExplainParser_3', {},
    BoolQueryExplainParser.from_query,
    query_BoolQueryExplainParser_3,
    lucene_explain_BoolQueryExplainParser_3,
)

# **********

query_RootExplainParser = {
    'query': {'match': query_MatchQueryExplainParser},
    'rescore': [
        {
            'query': {
                'rescore_query': {
                    'function_score': query_FunctionScoreExplainParser,
                }
            }
        }
    ]
}

query_RootExplainParser_multiple_rescore = {
    'query': {'match': query_MatchQueryExplainParser},
    'rescore': [
        {
            'query': {
                'rescore_query': {
                    'function_score': query_FunctionScoreExplainParser,
                }
            }
        },
        {
            'query': {
                'rescore_query_weight': 2.2,
                'query_weight': 2.1,
                'rescore_query': {
                    'function_score': query_FunctionScoreExplainParser,
                }
            }
        }
    ]
}

lucene_explain_RootExplainParser = {
    'value': lucene_explain_MatchQueryExplainParser['value'] +
             lucene_explain_FunctionScoreExplainParser['value'],  # noqa: E131
    'description': 'sum of:',
    'details': [
        {
            'value': lucene_explain_MatchQueryExplainParser['value'],
            'description': 'product of:',
            'details': [
                lucene_explain_MatchQueryExplainParser,
                {
                    'value': 1,
                    'description': 'primaryWeight',
                    'details': [],
                },
            ],
        },
        {
            'value': lucene_explain_FunctionScoreExplainParser['value'],
            'description': 'product of:',
            'details': [
                lucene_explain_FunctionScoreExplainParser,
                {
                    'value': 1,
                    'description': 'secondaryWeight',
                    'details': [],
                }
            ]
        }
    ]
}

lucene_explain_RootExplainParser_multiple_rescore = {
    'value': (query_RootExplainParser_multiple_rescore['rescore'][1]['query']['query_weight'] *
             (lucene_explain_MatchQueryExplainParser['value'] + lucene_explain_FunctionScoreExplainParser['value'])) +  # noqa: E501
             (query_RootExplainParser_multiple_rescore['rescore'][1]['query']['rescore_query_weight'] * lucene_explain_FunctionScoreExplainParser['value']),  # noqa: E131, E501
    'description': 'sum of:',
    'details': [
        {
            'value': lucene_explain_RootExplainParser['value'] * query_RootExplainParser_multiple_rescore['rescore'][1]['query']['query_weight'],  # noqa: E501
            'description': 'product of:',
            'details': [
                lucene_explain_RootExplainParser,
                {
                    'value': query_RootExplainParser_multiple_rescore['rescore'][1]['query']['query_weight'],
                    'description': 'primaryWeight',
                    'details': [],
                },
            ],
        },
        {
            'value': lucene_explain_FunctionScoreExplainParser['value'] * query_RootExplainParser_multiple_rescore['rescore'][1]['query']['rescore_query_weight'],  # noqa: E501
            'description': 'product of:',
            'details': [
                lucene_explain_FunctionScoreExplainParser,
                {
                    'value': query_RootExplainParser_multiple_rescore['rescore'][1]['query']['rescore_query_weight'],
                    'description': 'secondaryWeight',
                    'details': [],
                }
            ]
        }
    ]
}


register_test(
    'RootExplainParser',
    {
        'feature_values': {
            'pytest/query/labels.en.near_match/idf': [14.335771],
            'pytest/query/labels.en.near_match/termFreq': [1.0],
            'pytest/rescore/0/function_score/match_all': [1.0],
            'pytest/rescore/0/function_score/no_function_match': [0.0],
            'pytest/rescore/0/function_score/0/statement_keywords-P31-Q42': [1.0],
            'pytest/rescore/0/function_score/0/satu/incoming_links': [854],
        },
        'trainable': [
            'pytest/query/labels.en.near_match/k1:0',
            'pytest/query/labels.en.near_match/boost:0',
            'pytest/rescore/0/rescore_query_weight:0',
            'pytest/rescore/0/query_weight:0',
            'pytest/rescore/0/function_score/0/satu/incoming_links/k:0',
            'pytest/rescore/0/function_score/0/satu/incoming_links/a:0',
            'pytest/rescore/0/function_score/0/weight:0',
        ],
    },
    RootExplainParser.from_query,
    query_RootExplainParser,
    lucene_explain_RootExplainParser,
)

register_test(
    'RootExplainParser multiple rescore',
    {
        'feature_values': {
            'pytest/query/labels.en.near_match/idf': [14.335771],
            'pytest/query/labels.en.near_match/termFreq': [1.0],
            'pytest/rescore/0/function_score/match_all': [1.0],
            'pytest/rescore/0/function_score/no_function_match': [0.0],
            'pytest/rescore/0/function_score/0/statement_keywords-P31-Q42': [1.0],
            'pytest/rescore/0/function_score/0/satu/incoming_links': [854],
            'pytest/rescore/1/function_score/match_all': [1.0],
            'pytest/rescore/1/function_score/no_function_match': [0.0],
            'pytest/rescore/1/function_score/0/statement_keywords-P31-Q42': [1.0],
            'pytest/rescore/1/function_score/0/satu/incoming_links': [854],
        },
        'trainable': [
            'pytest/query/labels.en.near_match/k1:0',
            'pytest/query/labels.en.near_match/boost:0',
            'pytest/rescore/0/rescore_query_weight:0',
            'pytest/rescore/0/query_weight:0',
            'pytest/rescore/0/function_score/0/satu/incoming_links/k:0',
            'pytest/rescore/0/function_score/0/satu/incoming_links/a:0',
            'pytest/rescore/0/function_score/0/weight:0',
            'pytest/rescore/1/rescore_query_weight:0',
            'pytest/rescore/1/query_weight:0',
            'pytest/rescore/1/function_score/0/satu/incoming_links/k:0',
            'pytest/rescore/1/function_score/0/satu/incoming_links/a:0',
            'pytest/rescore/1/function_score/0/weight:0',
        ],
    },
    RootExplainParser.from_query,
    query_RootExplainParser_multiple_rescore,
    lucene_explain_RootExplainParser_multiple_rescore,
)

# **********

# Same as first, but with a type filter in url

lucene_explain_type_filter = {
    'value': 0,
    'description': 'match on required clause, product of:',
    'details': [
        {
            'value': 0,
            'description': '# clause',
            'details': [],
        },
        {
            "value": 1,
            "description": "_type:page, product of:",
            "details": [
                {
                    "value": 1,
                    "description": "boost",
                    "details": []
                },
                {
                    "value": 1,
                    "description": "queryNorm",
                    "details": []
                }
            ]
        }
    ]
}

lucene_explain_RootExplainParser_w_type = {
    'value': lucene_explain_RootExplainParser['value'],
    'description': 'sum of:',
    'details': [
        {
            'value': lucene_explain_RootExplainParser['value'],
            'description': 'product of:',
            'details': [
                {
                    'value': lucene_explain_RootExplainParser['value'],
                    'description': 'sum of:',
                    'details': [
                        lucene_explain_MatchQueryExplainParser,
                        lucene_explain_type_filter,
                    ]
                },
                {
                    'value': 1,
                    'description': 'primaryWeight',
                    'details': [],
                },
            ]
        },
        lucene_explain_RootExplainParser['details'][1],  # the rescore
    ],
}

register_test(
    'RootExplainParser_w_type', {},
    RootExplainParser.from_query,
    query_RootExplainParser,
    lucene_explain_RootExplainParser_w_type,
)

# **********

# Merging starting at root explain parser

query_RootExplainParser_merge = {
    'query': {
        'dis_max': query_DisMaxQueryExplainParser
    },
}

lucene_explain_RootExplainParser_merge_0 = {
    'value': lucene_explain_ConstantScoreExplainParser['value'],
    'description': 'sum of:',
    'details': [
        {
            'value': lucene_explain_ConstantScoreExplainParser['value'],
            'description': 'max of:',
            'details': [
                lucene_explain_ConstantScoreExplainParser,
            ]
        },
        lucene_explain_type_filter
    ]
}

lucene_explain_RootExplainParser_merge_1 = {
    'value': lucene_explain_MatchQueryExplainParser['value'],
    'description': 'sum of:',
    'details': [
        {
            'value': lucene_explain_MatchQueryExplainParser['value'],
            'description': 'max of:',
            'details': [
                lucene_explain_MatchQueryExplainParser,
            ]
        },
        lucene_explain_type_filter
    ]
}

register_test(
    'RootExplainParser merge',
    {
        'is_complete': False,
        'merge': [
            lucene_explain_RootExplainParser_merge_1,
        ],
    },
    RootExplainParser.from_query,
    query_RootExplainParser_merge,
    lucene_explain_RootExplainParser_merge_0
)

# **********

# Same, but with rescore as well


query_RootExplainParser_merge_w_rescore = {
    'query': {
        'dis_max': query_DisMaxQueryExplainParser
    },
    'rescore': [
        {
            "query": {
                "rescore_query": {
                    "match_all": {}
                }
            }
        }
    ]
}

lucene_explain_RootExplainParser_merge_w_rescore_0 = {
    'value': 2.1,
    'description': 'sum of:',
    'details': [
        {
            'value': 1.1,
            'description': 'product of:',
            'details': [
                lucene_explain_RootExplainParser_merge_0,
                {
                    "value": 1,
                    "description": "primaryWeight",
                    "details": [],
                },
            ],
        },
        {
            'value': 1,
            'description': 'product of:',
            'details': [
                MATCH_ALL_EXPLAIN,
                {
                    'value': 1,
                    'description': 'secondaryWeight',
                    'details': []
                }
            ]
        }
    ]
}

lucene_explain_RootExplainParser_merge_w_rescore_1 = {
    'value': 2.1,
    'description': 'sum of:',
    'details': [
        {
            'value': 1.1,
            'description': 'product of:',
            'details': [
                lucene_explain_RootExplainParser_merge_1,
                {
                    "value": 1,
                    "description": "primaryWeight",
                    "details": [],
                },
            ],
        },
        {
            'value': 1,
            'description': 'product of:',
            'details': [
                MATCH_ALL_EXPLAIN,
                {
                    'value': 1,
                    'description': 'secondaryWeight',
                    'details': []
                }
            ]
        }
    ]
}

register_test(
    'RootExplainParser_merge_w_rescore',
    {
        'is_complete': False,
        'merge': [
            lucene_explain_RootExplainParser_merge_w_rescore_1,
        ],
    },
    RootExplainParser.from_query,
    query_RootExplainParser_merge_w_rescore,
    lucene_explain_RootExplainParser_merge_w_rescore_0
)

# **********


@pytest.mark.parametrize('name,make_explain', TESTS['pickle'])
def test_is_picklable(name, make_explain):
    pickle.dumps(make_explain())


@pytest.mark.parametrize('name,make_explain,is_complete', TESTS['parser'])
def test_is_complete(name, make_explain, is_complete):
    # Simple tests of basic completeness
    explain = make_explain()
    assert explain.is_complete == is_complete

    # Make sure they don't throw exceptions
    assert isinstance(repr(explain), str)
    assert isinstance(str(explain), str)


def run_explain_in_tf(explain):
    tf.reset_default_graph()
    vecs = {k: tf.convert_to_tensor([v])
            for k, v in explain.feature_vec().items()}
    equation = explain.to_tf(vecs)
    with tf.Session() as sess:
        sess.run(tf.global_variables_initializer())
        return sess.run(equation)


def run_explain_recursive(explain):
    return {
        'type': type(explain).__name__,
        'name': explain.name,
        'value': explain.value,
        'tf': run_explain_in_tf(explain),
        'children': [run_explain_recursive(c) for c in explain.children]
    }


@pytest.mark.parametrize('name,make_explain', TESTS['tensor_equiv'])
def test_tensors_are_equivalent(name, make_explain):
    # Create the equation and run it with the feature vector, verify
    # same result as the lucene_explain. Tensors are of shape (batch_size, vec_len)
    explain = make_explain()
    result = run_explain_in_tf(explain)
    # Result can be either a scalar or a vector with a single element per batch item
    assert isinstance(result, (np.float32, np.ndarray))
    if isinstance(result, np.ndarray):
        assert result.shape == (1, 1)  # (batch_size, 1)
        result = result[0, 0]
    assert result == pytest.approx(explain.value), run_explain_recursive(explain)


@pytest.mark.parametrize('name,make_explain,expected_feature_values', TESTS['feature_values'])
def test_feature_vec_has_keys_and_values(name, make_explain, expected_feature_values):
    explain = make_explain()
    vec = explain.feature_vec()
    approx_feature_values = {k: [pytest.approx(v) for v in outer] for k, outer in expected_feature_values.items()}
    assert vec == approx_feature_values


@pytest.mark.parametrize('name,make_explain,expected_tunables', TESTS['trainable'])
def test_trainable_tensors(name, make_explain, expected_tunables):
    tf.reset_default_graph()
    explain = make_explain()
    vec = {k: tf.convert_to_tensor([v])
           for k, v in explain.feature_vec().items()}
    score_op = explain.to_tf(vec)
    assert score_op is not None
    actual = {var.name: var for var in tf.get_collection(tf.GraphKeys.GLOBAL_VARIABLES)}
    assert set(actual.keys()) == set(expected_tunables)
    for name, var in actual.items():
        assert var.shape == ()
        assert var.dtype.is_floating


@pytest.mark.parametrize('name,make_explain,other_explains', TESTS['merge'])
def test_merge(name, make_explain, other_explains):
    parser, explain = make_explain(verbose=True)
    for lucene_explain in other_explains:
        other_explain = parser.parse(lucene_explain)
        explain = parser.merge(explain, other_explain)
    assert explain.is_complete


def test_FunctionScoreExplainParser_merge_same_weight_filters():
    weight = 1.1
    parser = FunctionScoreExplainParser.from_query({
        'score_mode': 'sum',
        'functions': [
            {'weight': weight, 'filter':  {'term': {'statement_keywords': "P1=Q2"}}},
            {'weight': weight, 'filter': {'term': {'statement_keywords': "P3=Q4"}}},
        ]
    }, '')

    lucene_explain_1 = {
        "value": 1,
        "description": "match filter: statement_keywords:P1=Q2",
        "details": []
    }
    lucene_explain_2 = {
        "value": 1,
        "description": "match filter: statement_keywords:P3=Q4",
        "details": []
    }

    def function_score_explain(term_explain):
        value = term_explain['value']
        return {
            'value': value * weight,
            'description': 'function score, product of:',
            'details': [
                MATCH_ALL_EXPLAIN,
                {
                    'value': value * weight,
                    'description': 'min of:',
                    'details': [
                        {
                            'value': value * weight,
                            'description': 'function score, score mode [sum]',
                            'details': [
                                {
                                    'value': value * weight,
                                    'description': 'function score, product of:',
                                    'details': [
                                        term_explain,
                                        {
                                            'value': weight,
                                            'description': 'product of:',
                                            'details': [
                                                {
                                                    'value': 1,
                                                    'description': 'constant score 1.0 - no function provided',  # noqa: E501
                                                    'details': [],
                                                },
                                                {
                                                    'value': weight,
                                                    'description': 'weight',
                                                    'details': [],
                                                }
                                            ]
                                        }
                                    ]
                                }
                            ]
                        },
                        {
                            'value': FLT_MAX,
                            'description': 'maxBoost',
                            'details': [],
                        }
                    ]
                }
            ]
        }

    explain_1 = parser.parse(function_score_explain(lucene_explain_1))
    explain_1_b = parser.parse(function_score_explain(lucene_explain_1))
    explain_2 = parser.parse(function_score_explain(lucene_explain_2))
    assert not explain_1.is_complete
    assert not explain_2.is_complete

    # Merging two similar items must not be complete
    merged = parser.merge(explain_1, explain_1_b)
    assert not merged.is_complete

    # Merging the two distinct items must be complete
    merged = parser.merge(explain_1, explain_2)
    assert merged.is_complete


token_count_router_suite.register_tests(register_test)
