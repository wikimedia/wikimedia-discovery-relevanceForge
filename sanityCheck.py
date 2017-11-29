from __future__ import print_function
import argparse
import json
import requests
import sys


def check(model, config):
    ok = True
    query_params = {
        'action': 'query',
        'list': 'search',
        'srlimit': 3,
        'cirrusMLRModel': model,
        'format': 'json',
        'formatversion': 2,
    }
    if 'query' in config:
        # Apply overrides from config if requested. This might
        # apply a specific cirrusUserTesting param or some such.
        query_params.update(config['query'])

    print('Running sanity check against %s' % (config['api']))
    for query, expected in config['queries'].items():
        print("Query: %s" % (query))
        query_params['srsearch'] = query
        r = requests.get(config['api'], params=query_params)
        results = [x['title'] for x in r.json()['query']['search']]
        diff = set(expected).difference(results)
        if diff:
            ok = False
            print("Results:\n\t" + '\n\t'.join(results))
            print("Expected:")
            for title in expected:
                marker = '+' if title in results else '-'
                print('\t%s %s' % (marker, title))
            print('')
        else:
            print("PASSED\n")
    return ok


def parse_arguments(argv):
    parser = argparse.ArgumentParser(description='mlr sanity check')
    parser.add_argument(
            'config', type=lambda x: json.load(open(x)),
            help='json file containing queries to check and results expected in top 3')
    parser.add_argument(
        'model', help='MLR model to use for ranking')
    args = parser.parse_args(argv)
    return dict(vars(args))


def main(argv=None):
    args = parse_arguments(argv)
    return check(**args)


if __name__ == "__main__":
    ok = main()
    sys.exit(0 if ok else 1)
