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

import os
import sys
import argparse
import ConfigParser
import pipes
import shutil
import subprocess
import re
import json


def getSafeName(name):
    return re.sub(r'[^a-zA-Z0-9]', '-', name)


def refreshDir(dirname):
    # Delete the dir if it exists to clean out cruft from previous runs
    if os.path.exists(dirname):
        shutil.rmtree(dirname)
    os.makedirs(dirname)


def getSafeWorkPath(config, section, subdir):
    qname = getSafeName(config.get(section, 'name'))
    return '%s/%s/%s' % (config.get('settings', 'workdir'), subdir, qname)


def runSearch(config, section):
    qdir = getSafeWorkPath(config, section, 'queries')
    cmdline = config.get(section, 'searchCommand')

    results_file = qdir + '/results'
    refreshDir(qdir)
    if config.has_option(section, 'config'):
        try:
            # validate json
            json.loads(config.get(section, 'config'))
            search_options = config.get(section, 'config')
        except ValueError:
            # config wasn't valid json, maybe it was a file containing json
            with open(config.get(section, 'config')) as f:
                search_options = f.read()
        with open(qdir + '/config.json', 'w') as f:
            f.write(search_options)  # archive search config
        search_options = search_options.replace("\n", "")
        cmdline += " --options " + pipes.quote(search_options.strip())
    runCommand("cat %s | ssh %s %s > %s" % (config.get(section, 'queries'),
                                            config.get(section, 'labHost'),
                                            pipes.quote(cmdline),
                                            results_file))
    shutil.copyfile(config.get(section, 'queries'), qdir + '/queries')  # archive queries
    return results_file


def distributeGlobalSettings(config, globals, sections, settings):
    # if settings are missing from sections, copy from globals
    for sec in sections:
        for set in settings:
            if not config.has_option(sec, set) and config.has_option(globals, set):
                config.set(sec, set, config.get(globals, set))


def checkSettings(config, section, settings):
    for s in settings:
        if not config.has_option(section, s):
            raise ValueError("Section [%s] missing configuration %s" % (section, s))
    pass


def runCommand(cmd):
    print "RUNNING "+cmd
    subprocess.check_call(cmd, shell=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Run relevance lab queries', prog=sys.argv[0])
    parser.add_argument('-c', '--config', dest='config', help='Configuration file name',
                        required=True)
    args = parser.parse_args()

    config = ConfigParser.ConfigParser()
    config.readfp(open(args.config))
    distributeGlobalSettings(config, 'settings', ['test1', 'test2'],
                             ['queries', 'labHost', 'searchCommand', 'config'])
    checkSettings(config, 'settings', ['workDir', 'jsonDiffTool', 'metricTool'])
    checkSettings(config, 'test1', ['name', 'queries', 'labHost', 'searchCommand'])
    checkSettings(config, 'test2', ['name', 'queries', 'labHost', 'searchCommand'])

    res1 = runSearch(config, 'test1')
    res2 = runSearch(config, 'test2')
    comparisonDir = "%s/comparisons/%s_%s" % (config.get('settings', 'workDir'),
                                              getSafeName(config.get('test1', 'name')),
                                              getSafeName(config.get('test2', 'name')))
    refreshDir(comparisonDir)
    shutil.copyfile(args.config, comparisonDir + "/config.ini")  # archive comparison config

    runCommand("%s %s %s %s" % (config.get('settings', 'jsonDiffTool'),
                                comparisonDir + "/diffs", res1, res2))
    runCommand("%s %s %s %s" % (config.get('settings', 'metricTool'), comparisonDir, res1, res2))
