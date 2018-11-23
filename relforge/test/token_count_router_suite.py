from relforge.explain_parser.token_count_router import TokenCountRouterExplainParser

query = {
    'text': 'test',
    'analyzer': 'text',
    'fallback': {
        'match_none': {}
    },
    'conditions': [
        {
            'gte': 1,
            'query': {
                'term': {
                    'text': '{{query_string}}'
                }
            }
        },
        {
            'gt': 3,
            'query': {
                'match_none': {}
            }
        }
    ]
}

explain = {
    "description": "weight(text:test in 21973) [PerFieldSimilarity], result of:",
    "value": 7.064174,
    "details": [
        {
            "description": "score(doc=21973,freq=43.0 = termFreq=43.0\n), product of:",
            "value": 7.064174,
            "details": [
                {
                    "description": "idf, computed as log(1 + (docCount - docFreq + 0.5) / (docFreq + 0.5)) from:",
                    "value": 3.2709694,
                    "details": [
                        {
                            "description": "docFreq",
                            "value": 33227.0,
                            "details": []
                        },
                        {
                            "description": "docCount",
                            "value": 875107.0,
                            "details": []
                        }
                    ]
                },
                {
                    "description": "tfNorm, computed as (freq * (k1 + 1)) / (freq + "
                                   "k1 * (1 - b + b * fieldLength / avgFieldLength)) from:",
                    "value": 2.1596577,
                    "details": [
                        {
                            "description": "termFreq=43.0",
                            "value": 43.0,
                            "details": []
                        },
                        {
                            "description": "parameter k1",
                            "value": 1.2,
                            "details": []
                        },
                        {
                            "description": "parameter b",
                            "value": 0.75,
                            "details": []
                        },
                        {
                            "description": "avgFieldLength",
                            "value": 457.8359,
                            "details": []
                        },
                        {
                            "description": "fieldLength",
                            "value": 256.0,
                            "details": []
                        }
                    ]
                }
            ]
        }
    ]
}


def register_tests(register_test):
    register_test(
        'token_count_router',
        {},
        TokenCountRouterExplainParser.from_query,
        query,
        explain
    )
