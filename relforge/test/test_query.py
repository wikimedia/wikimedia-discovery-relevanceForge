from relforge.query import CachedQuery
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
            'servers': [{
                'host': 'pytesthost',
                'cmd': 'foo bar baz',
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
