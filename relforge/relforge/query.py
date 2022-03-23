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
try:
    # py 3.x
    import configparser
except ImportError:
    # py 2.x
    import ConfigParser as configparser
import hashlib
import logging
import os
import pandas as pd
import pickle
import pipes
import subprocess
import yaml

try:
    from yaml import CLoader as Loader
except ImportError:
    from yaml import Loader

try:
    # py 2.x
    unicode()

    def decode_unicode_bytes(x):
        return x.decode('utf-8')
except NameError:
    # py 3.x
    def decode_unicode_bytes(x):
        return x

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
            clean = converter(arg)
            if clean not in {'<', '>'}:
                clean = pipes.quote(clean)
            command.append(clean)
        return ' '.join(command)


class Hive(object):
    def __init__(self, config):
        pass

    def commandline(self):
        return CliCommand([
            'beeline',
            '--silent=true',
            '--outputformat=tsv2',
            '--fastConnect=true',
            '--maxWidth=' + str(int(1e8)),
            '--maxColumnWidth=' + str(int(1e8)),
        ])

    def parse_tsv2_line(self, line):
        """Parse a single line of tsv2 output from beeline

        This format is tab delimited. If a column contains
        a tab the column is quoted with null bytes.
        """
        prefix = None
        for piece in line.split('\t'):
            if prefix is None and len(piece) > 0 and piece[0] == '\0':
                prefix = piece[1:] + '\t'
            elif prefix is None:
                yield None if piece == 'NULL' else piece
            else:
                prefix += piece
                if prefix[-1] == '\0':
                    yield prefix[0:-1]
                    prefix = None
                else:
                    prefix += '\t'
        if prefix is not None:
            raise Exception('Malformed input without \\0 terminator: {}'.format(repr(line)))

    def parse(self, cmd_output):
        # Beeline isn't made for this, so we get some mediocre output
        # to parse through. If we could pass the command instead of
        # piping it in it would be slightly better, but have length
        # problems.
        # Guess what the prompt looks like from the first line
        prompt = cmd_output.pop().split('>', 1)[0] + '> '
        LOG.debug('Detected prompt as: %s', prompt)
        in_results = False
        for line in cmd_output:
            has_prompt = line.startswith(prompt)
            if has_prompt:
                if in_results:
                    LOG.debug('Found junk, stop looking: %s', line)
                    return
                else:
                    # Junk at beginning
                    # Probably not the header we are looking for?
                    LOG.debug('skipping line: %s', line)
                    continue
            elif in_results:
                cols = list(self.parse_tsv2_line(line))
                if any(x is None for x in cols):
                    LOG.debug('Throwing out line with null values: %s', repr(line))
                else:
                    LOG.debug('Yielding query row: %s', cols)
                    yield cols
            else:
                header = list(self.parse_tsv2_line(line))
                LOG.debug('Found results section with header: %s', header)
                in_results = True


class DummyProvider(object):
    def __init__(self, config):
        try:
            self.results = config['dummy'].get('results')
        except KeyError:
            self.results = []

    def commandline(self):
        return CliCommand(['true'])

    def parse(self, cmd_output):
        return self.results


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


def execute_remote(remote_host, cli_command, input):
    command = cli_command.to_shell_string()
    p = subprocess.Popen(['ssh', '-o', 'Compression=yes', remote_host, command],
                         stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE)

    return p.communicate(input=input)


class Query(object):
    PROVIDERS = {
        'mysql': MySql,
        'hive': Hive,
        'dummy': DummyProvider,
    }

    def __init__(self, settings):
        with codecs.open(settings('query'), "r", "utf-8") as f:
            sql_config = yaml.load(f.read(), Loader=Loader)

        try:
            preferred_host = settings('host')
        except configparser.NoOptionError:
            server = sql_config['servers'][0]
        else:
            server = self._choose_server(sql_config['servers'], preferred_host)

        self.columns = sql_config.get('columns', None)
        self.types = sql_config.get('types', {})
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

    def to_df(self):
        df = pd.DataFrame(self.fetch(), columns=self.columns)
        for column, pd_type in self.types.items():
            df[column] = df[column].astype(pd_type)
        return df

    def fetch(self):
        cli_command = self.provider.commandline()
        stdout, stderr = execute_remote(
                self._remote_host, cli_command, self._query.encode('utf8'))
        if len(stdout) == 0:
            raise RuntimeError("Couldn't run SQL query:\n%s" % (stderr))
        if len(stderr):
            LOG.debug('query stderr: %s', stderr)

        try:
            output = decode_unicode_bytes(stdout).split("\n")
        except UnicodeDecodeError:
            # Some unknown problem ... let's just work through it line by line
            # and throw out bad data :(
            output = []
            for line in stdout.split("\n"):
                try:
                    output.append(decode_unicode_bytes(line))
                except UnicodeDecodeError:
                    LOG.debug("Non-utf8 data: %s", line)
        return self.provider.parse(output)


class CachedQuery(Query):
    def __init__(self, settings):
        super(CachedQuery, self).__init__(settings)
        self._cache_dir = os.path.join(settings('workDir'), '/cache')
        query_hash = hashlib.md5(self._query.encode('utf8')).hexdigest()
        self._cache_path = os.path.join(self._cache_dir, query_hash + '.pkl')

    def fetch(self):
        try:
            with codecs.open(self._cache_path, 'r', 'utf-8') as f:
                return pickle.load(f)
        except IOError:
            LOG.debug("No cached query result available.")

        result = super(CachedQuery, self).fetch()

        if not os.path.isdir(self._cache_dir):
            try:
                os.makedirs(self._cache_dir)
            except OSError:
                LOG.debug("cache directory created since checking")
                pass

        with codecs.open(self._cache_path, 'w', 'utf-8') as f:
            pickle.dump(result, f, pickle.HIGHEST_PROTOCOL)
        return result
