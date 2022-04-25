import pandas as pd
import pytest
import relforge.query
from relforge.query import CachedQuery, CliCommand, CliSequence, MySql, Query
import tempfile
import yaml


def make_query(query_class=Query, **kwargs):
    with tempfile.NamedTemporaryFile(mode='w') as f:
        # TODO: It's annoying to have to be so indirect...
        settings = dict({
            'workDir': '/dev/null',
            'query': f.name,
            'host': 'pytesthost',
        }, **kwargs.pop('test_settings', {}))
        defaults = {
            'provider': 'dummy',
            'servers': [{
                'host': 'pytesthost',
                'mysql': {},
                'dummy': {
                    'results': []
                }
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
        return query_class(lambda x=None: settings if x is None else settings[x])


def make_cached_query(**kwargs):
    return make_query(CachedQuery, **kwargs)


@pytest.mark.parametrize('provider', Query.PROVIDERS.keys())
def test_minimal_init(provider):
    assert make_cached_query(provider=provider) is not None


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


def test_to_df(mocker):
    mocker.patch.object(
        relforge.query, 'execute_remote',
        return_value=('some useless text', '', 0))
    df = make_query(
        columns=['z', 'y', 'x'],
        servers=[{
            'host': 'pytesthost',
            'dummy': {
                'results': [
                    ('a', 'b', 2),
                    ('c', 'a', 1),
                ]
            }
        }]).to_df()
    assert isinstance(df, pd.DataFrame)
    assert df.columns.tolist() == ['z', 'y', 'x']
    assert len(df) == 2
