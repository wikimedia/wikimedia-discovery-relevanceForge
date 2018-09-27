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

import codecs
import ConfigParser
import hashlib
import logging
import os
import subprocess
import yaml


LOG = logging.getLogger(__name__)


class CachedQuery:
    def __init__(self, settings):
        self._cache_dir = settings('workDir') + '/cache'

        with codecs.open(settings('query'), "r", "utf-8") as f:
            sql_config = yaml.load(f.read())

        try:
            server = self._choose_server(sql_config['servers'], settings('host'))
        except ConfigParser.NoOptionError:
            server = sql_config['servers'][0]

        self._stats_server = server['host']
        self._mysql_cmd = server.get('cmd')
        self.scoring_config = sql_config['scoring']

        sql_config['variables'].update(settings())
        self._query = sql_config['query'].format(**sql_config['variables'])

    def _choose_server(self, servers, host):
        for server in servers:
            if server['host'] == host:
                return server

        raise RuntimeError("Couldn't locate host %s" % (host))

    def _run_query(self):
        p = subprocess.Popen(['ssh', self._stats_server, self._mysql_cmd],
                             stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE)

        stdout, stderr = p.communicate(input=self._query)
        if len(stdout) == 0:
            raise RuntimeError("Couldn't run SQL query:\n%s" % (stderr))

        try:
            return stdout.decode('utf-8')
        except UnicodeDecodeError:
            # Some unknown problem ... let's just work through it line by line
            # and throw out bad data :(
            clean = []
            for line in stdout.split("\n"):
                try:
                    clean.append(line.decode('utf-8'))
                except UnicodeDecodeError:
                    LOG.debug("Non-utf8 data: %s" % (line))
            return u"\n".join(clean)

    def fetch(self):
        query_hash = hashlib.md5(self._query).hexdigest()
        cache_path = "%s/click_log.%s" % (self._cache_dir, query_hash)
        try:
            with codecs.open(cache_path, 'r', 'utf-8') as f:
                return f.read().split("\n")
        except IOError:
            LOG.debug("No cached query result available.")
            pass

        result = self._run_query()

        if not os.path.isdir(self._cache_dir):
            try:
                os.makedirs(self._cache_dir)
            except OSError:
                LOG.debug("cache directory created since checking")
                pass

        with codecs.open(cache_path, 'w', 'utf-8') as f:
            f.write(result)
        return result.split("\n")
