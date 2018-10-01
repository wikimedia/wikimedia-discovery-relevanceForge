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
import pipes
import subprocess
import yaml


LOG = logging.getLogger(__name__)


class CliSequence(object):
    def __init__(self, commands):
        self.commands = commands

    def to_shell_string(self):
        return ' && '.join(c.to_shell_string() for c in self.commands)


class CliCommand(object):
    converters = {
        int: str,
        float: str,
        str: str,
    }

    def __init__(self, args):
        self.args = args

    def default_converter(self, arg):
        return arg.to_shell_string()

    def to_shell_string(self):
        command = []
        for arg in self.args:
            converter = self.converters.get(type(arg), self.default_converter)
            command.append(pipes.quote(converter(arg)))
        return ' '.join(command)


class MySql(object):
    def __init__(self, config):
        self.dbserver = config['mysql'].get('dbserver')
        self.defaults_extra_file = config['mysql'].get('defaults-extra-file')
        self.user = config['mysql'].get('user')
        self.password = config['mysql'].get('password')
        self.mwvagrant = config['mysql'].get('mwvagrant')

    def commandline(self):
        args = ['mysql']
        if self.dbserver:
            args += ['--host', self.dbserver]
        if self.defaults_extra_file:
            args.append('--defaults-extra-file=' + self.defaults_extra_file)
        if self.user:
            args += ['-u', self.user]
        if self.password:
            args.append('-p' + self.password)
        command = CliCommand(args)
        if self.mwvagrant:
            command = CliSequence([
                CliCommand(['cd', self.mwvagrant]),
                CliCommand(['mwvagrant', 'ssh', '--', command])
            ])
        return command

    def parse(self, cmd_output):
        # burn the header
        cmd_output.pop(0)
        for line in cmd_output:
            if len(line) == 0:
                continue
            query, title, score = line.strip().split('\t')
            if score == 'NULL':
                score = 0.
            yield query, title, float(score)


class CachedQuery:
    PROVIDERS = {
        'mysql': MySql,
    }

    def __init__(self, settings):
        self._cache_dir = settings('workDir') + '/cache'

        with codecs.open(settings('query'), "r", "utf-8") as f:
            sql_config = yaml.load(f.read())

        try:
            preferred_host = settings('host')
        except ConfigParser.NoOptionError:
            server = sql_config['servers'][0]
        else:
            server = self._choose_server(sql_config['servers'], preferred_host)

        self._remote_host = server['host']
        self.provider = self.PROVIDERS[sql_config['provider']](server)
        self.scoring_config = sql_config['scoring']
        sql_config['variables'].update(settings())
        self._query = sql_config['query'].format(**sql_config['variables'])
        LOG.debug('Loaded SQL query: %s', self._query)

    def _choose_server(self, servers, host):
        for server in servers:
            if server['host'] == host:
                return server
        raise RuntimeError("Couldn't locate host %s" % (host))

    def _run_query(self):
        command = self.provider.commandline().to_shell_string()
        p = subprocess.Popen(['ssh', '-o', 'Compression=yes', self._remote_host, command],
                             stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE)

        stdout, stderr = p.communicate(input=self._query)
        if len(stdout) == 0:
            raise RuntimeError("Couldn't run SQL query:\n%s" % (stderr))
        if len(stderr):
            LOG.debug('query stderr: %s', stderr)

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
                    LOG.debug("Non-utf8 data: %s", line)
            return u"\n".join(clean)

    def fetch(self):
        query_hash = hashlib.md5(self._query).hexdigest()
        cache_path = "%s/click_log.%s" % (self._cache_dir, query_hash)
        try:
            with codecs.open(cache_path, 'r', 'utf-8') as f:
                return self.provider.parse(f.read().split("\n"))
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
        return self.provider.parse(result.split("\n"))
