# runner.py - Run relevance lab queries
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
import pipes
import shutil
import subprocess
import re
import json
import base64


def defaults(config, section, settings):
    """Apply default settings to a configparser section"""
    for s in settings:
        if not config.has_option(section, s):
            config.set(section, s, settings[s])


def getSafeName(name):
    return re.sub(r'[^a-zA-Z0-9]', '-', name)


def refreshDir(dirname):
    # Delete the dir if it exists to clean out cruft from previous runs
    if os.path.exists(dirname):
        shutil.rmtree(dirname)
    os.makedirs(dirname)


def getSafeWorkPath(config, section, subdir):
    qname = getSafeName(config.get(section, 'name'))
    return os.path.join(config.get('settings', 'workdir'), subdir, qname)


def sanitize_json(file):
    file_isjson = file + '.isjson'
    file_isnotjson = file + '.isnotjson'
    isjson = open(file_isjson, 'w')
    isnotjson = open(file_isnotjson, 'w')
    for line in open(file).readlines():
        if line.startswith('{'):
            isjson.write(line)
        else:
            isnotjson.write(line)
    isjson.close()
    isnotjson.close()
    shutil.move(file_isjson, file)
    if os.path.getsize(file_isnotjson) == 0:
        os.remove(file_isnotjson)


def runSearch(config, section, allow_reuse=True):
    qdir = getSafeWorkPath(config, section, 'queries')
    cmdline = config.get(section, 'searchCommand')

    results_file = qdir + '/results'
    if os.path.isfile(results_file) and allow_reuse:
        print("REUSING: %s" % results_file)
        return results_file
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
        search_options = "B64://" + base64.b64encode(search_options.encode('utf8')).decode('ascii')
        cmdline += " --options " + search_options
    runCommand("cat %s | ssh %s %s > %s" % (config.get(section, 'queries'),
                                            config.get(section, 'labHost'),
                                            pipes.quote(cmdline),
                                            results_file))
    shutil.copyfile(config.get(section, 'queries'), qdir + '/queries')  # archive queries
    # sanitize json
    sanitize_json(results_file)
    return results_file


def checkSettings(config, section, settings):
    for s in settings:
        if not config.has_option(section, s):
            raise ValueError("Section [%s] missing configuration %s" % (section, s))
    pass


def runCommand(cmd):
    print("RUNNING "+cmd)
    subprocess.check_call(cmd, shell=True)
