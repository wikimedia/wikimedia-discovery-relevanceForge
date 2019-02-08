#!/usr/bin/env python
# relevancyRunner.py - Run relevance lab queries
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

import sys
import argparse
import ConfigParser
import relforge.runner
import shutil


def distributeGlobalSettings(config, globals, sections, settings):
    # if settings are missing from sections, copy from globals
    for sec in sections:
        for set in settings:
            if not config.has_option(sec, set) and config.has_option(globals, set):
                config.set(sec, set, config.get(globals, set))


def main():
    parser = argparse.ArgumentParser(description='Run relevance lab queries', prog=sys.argv[0])
    parser.add_argument('-c', '--config', dest='config', help='Configuration file name',
                        required=True)
    args = parser.parse_args()

    config = ConfigParser.ConfigParser()
    config.readfp(open(args.config))
    distributeGlobalSettings(config, 'settings', ['test1', 'test2'],
                             ['queries', 'labHost', 'searchCommand', 'config',
                              'wikiUrl', 'explainUrl', 'allowReuse'])
    relforge.runner.checkSettings(config, 'settings', ['workDir', 'jsonDiffTool', 'metricTool'])
    relforge.runner.checkSettings(config, 'test1', ['name', 'queries', 'labHost', 'searchCommand'])
    relforge.runner.checkSettings(config, 'test2', ['name', 'queries', 'labHost', 'searchCommand'])
    # TODO: make some useful defaults here?
    relforge.runner.defaults(config, 'test1', {'wikiUrl': '', 'explainUrl': '', 'allowReuse': True})
    relforge.runner.defaults(config, 'test2', {'wikiUrl': '', 'explainUrl': '', 'allowReuse': True})

    res1 = relforge.runner.runSearch(config, 'test1')
    res2 = relforge.runner.runSearch(config, 'test2')
    comparisonDir = "%s/comparisons/%s_%s" % (
            config.get('settings', 'workDir'),
            relforge.runner.getSafeName(config.get('test1', 'name')),
            relforge.runner.getSafeName(config.get('test2', 'name')))
    relforge.runner.refreshDir(comparisonDir)
    shutil.copyfile(args.config, comparisonDir + "/config.ini")  # archive comparison config

    relforge.runner.runCommand("%s %s -w %s -W %s -e '%s' -E '%s' %s %s" % (
        config.get('settings', 'jsonDiffTool'),
        comparisonDir + "/diffs",
        config.get('test1', 'wikiUrl'), config.get('test2', 'wikiUrl'),
        config.get('test1', 'explainUrl'), config.get('test2', 'explainUrl'),
        res1, res2))
    relforge.runner.runCommand(
        "%s %s %s %s" % (config.get('settings', 'metricTool'), comparisonDir, res1, res2))


if __name__ == '__main__':
    main()
