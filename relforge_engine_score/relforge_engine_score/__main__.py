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
import ConfigParser
import logging
import os
import sys
import tempfile

import relforge.runner

from relforge_engine_score.scores import init_scorer, load_results


LOG = logging.getLogger(__name__)


def genSettings(config):
    def get(key=None):
        if key is None:
            return dict(config.items('settings'))
        else:
            return config.get('settings', key)
    return get


def score_for_config(config_path, verbose):
    logging.basicConfig(level=logging.DEBUG if verbose else logging.INFO)

    config = ConfigParser.ConfigParser()
    with open(config_path) as f:
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


def parse_arguments(argv):
    parser = argparse.ArgumentParser(
        description='Calculate an engine score', prog=sys.argv[0])
    parser.add_argument(
        '-c', '--config', dest='config_path', help='Configuration file name',
        required=True)
    parser.add_argument(
        '-v', '--verbose', dest='verbose', action='store_true',
        help='Increase output verbosity')
    parser.set_defaults(verbose=False)
    return parser.parse_args()


def main(argv=None):
    args = parse_arguments(argv)
    return score_for_config(**dict(vars(args)))


if __name__ == '__main__':
    sys.exit(main())
