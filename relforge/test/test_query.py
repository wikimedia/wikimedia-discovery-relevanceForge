import pytest
from relforge.query import CachedQuery, CliCommand, CliSequence, MySql
import tempfile
import yaml


def make_query(**kwargs):
    with tempfile.NamedTemporaryFile() as f:
        # TODO: It's annoying to have to be so indirect...
        settings = dict({
            'workDir': '/dev/null',
            'query': f.name,
            'host': 'pytesthost',
        }, **kwargs.pop('test_settings', {}))
        defaults = {
            'provider': 'mysql',
            'servers': [{
                'host': 'pytesthost',
                'mysql': {},
            }],
            'scoring': {
                'algorithm': 'pytestalgo',
                'options': {}
            },
            'variables': {},
            'query': 'SELECT x, y FROM ...',
        }
        f.write(yaml.dump(dict(defaults, **kwargs)))
        f.flush()
        return CachedQuery(lambda x=None: settings if x is None else settings[x])


def test_minimal_init():
    assert make_query() is not None


def test_query_templating():
    q = make_query(
        query='select {a} from {b}',
        variables={'a': 'hello', 'b': 'world'})
    assert q._query == 'select hello from world'


def test_query_templating_settings_override():
    q = make_query(
        query='select {a} from {b}',
        variables={'a': 'hello', 'b': 'world'},
        test_settings={'a': 'qqq'})
    assert q._query == 'select qqq from world'


@pytest.mark.parametrize('expected, args', [
    ('true', ['true']),
    ("""'don'"'"'t' panic""", ["don't", 'panic'])
])
def test_cli_escaping(expected, args):
    assert expected == CliCommand(args).to_shell_string()


def test_basic_cli_sequence():
    assert 'a && b && c' == CliSequence([
        CliCommand(['a']),
        CliCommand(['b']),
        CliCommand(['c'])]).to_shell_string()


@pytest.mark.parametrize('expected, config', [
    ('mysql', {}),
    ('cd /mwv && mwvagrant ssh -- mysql', {'mwvagrant': '/mwv'}),
    ('mysql -u qqq', {'user': 'qqq'}),
    ('mysql -pwww', {'password': 'www'}),
    ('mysql --host testdb', {'dbserver': 'testdb'}),
    ('mysql --defaults-extra-file=/hi/there', {'defaults-extra-file': '/hi/there'}),
    ("""mysql '-ppy'"'"'test'""", {'password': "py'test"}),
    ("""cd /srv/mwv && mwvagrant ssh -- 'mysql '"'"'-ppy'"'"'"'"'"'"'"'"'test'"'"''""", {
        'mwvagrant': '/srv/mwv',
        'password': "py'test"
    })
])
def test_mysql_provider_commandline(expected, config):
    provider = MySql({
        'host': 'relforge.pytestnet',
        'mysql': config})
    assert provider.commandline().to_shell_string() == expected


def test_mysql_provider_parse():
    provider = MySql({
        'host': 'relforge.pytestnet',
        'mysql': {}})
    cmd_output = ["query\ttitle\tscore", "1\t2\t3"]
    result = list(provider.parse(cmd_output))
    assert [('1', '2', 3.0)] == result
