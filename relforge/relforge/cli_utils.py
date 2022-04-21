import argparse
from glob import glob
from gzip import GzipFile
import logging
import os
import pickle
import shutil
import sys

import elasticsearch


log = logging.getLogger(__name__)
# Unfortunately the delete on error/exit only work when running main() from
# this module, and not when used from a notebook or repl.
DELETE_ON_ERROR = []
DELETE_ON_EXIT = []


def iterate_pickle(in_path):
    """Load sequential elements from a pickle file"""
    if in_path[-3:] == '.gz':
        loader = GzipFile
    else:
        loader = open
    with loader(in_path, 'rb') as f:
        try:
            while True:
                yield pickle.load(f)
        except EOFError:
            pass


def load_pkl(in_path):
    """Load single element from pickle file"""
    return next(iterate_pickle(in_path))


def load_kv_pairs(pairs_str):
    """Load dict from string formatted as: k1=v1,k2=v2"""
    if not pairs_str:
        return dict()
    return dict(pair.split('=', 2) for pair in pairs_str.split(','))


def load_sql_query(yaml_path, template_variables=None):
    import configparser
    from relforge.query import Query

    if template_variables is None:
        template_variables = {}
    if 'limit' not in template_variables:
        template_variables['limit'] = str(1e9)

    def settings(key=None):
        if key == 'query':
            return yaml_path
        elif key is None:
            return template_variables
        else:
            raise configparser.NoOptionError(key, None)

    return Query(settings)


def make_loader(fn, *arg_names, prune=[], **kwargs):
    # arg names with leading ? optionally pass None
    def inner(args):
        value = fn(*(
            args.get(name[1:]) if name[0] == '?' else args[name]
            for name in arg_names), **kwargs)
        result_args = dict(args, **{arg_names[0]: value})
        for key in prune:
            if key in result_args:
                del result_args[key]
        return result_args
    return inner


def with_arg(*args, **kwargs):
    """Wrap ArgumentParser.add_arugment into a callable.

    Used with @register_command to define per-command cli parameters. Returned
    function can be called with keyword arguments to override keywords already
    set, or with a single argparser.ArgumentParser to apply the current
    argument parameters.
    """
    def fn(*extra_args, **extra_kwargs):
        if len(extra_args) == 1 and isinstance(extra_args[0], argparse.ArgumentParser):
            call_kwargs = dict(kwargs)
            loader = call_kwargs.pop('loader', None)
            extra_args[0].add_argument(*args, **call_kwargs)
            return loader
        elif len(extra_args) != 0:
            raise Exception('Can only be extended with keyword arguments')
        else:
            return with_arg(*args, **dict(kwargs, **extra_kwargs))
    return fn


def bounded_float(min_val, max_val):
    def fn(raw_val):
        val = float(raw_val)
        if min_val <= val <= max_val:
            return val
        raise ValueError('Expected {} to be between {} and {}'.format(val, min_val, max_val))
    return fn


def positive_int(raw_val):
    val = int(raw_val)
    if val >= 0:
        return val
    raise ValueError('Expected {} to be greater than 0'.format(val))


def unlink_path_glob(path_glob):
    for path in glob(path_glob):
        try:
            if path == '/dev/null':
                pass
            elif os.path.isdir(path):
                shutil.rmtree(path)
            elif os.path.exists(path):
                os.unlink(path)
        except OSError:
            log.exception('Exception unlinking %s', path)


def generate_cli():
    commands = {}

    def register_command(*args):
        """Register a CLI command

        Attaches function to module-level commands dict when
        return value is used to decorate a function. Reusable
        cli argument definitions are accepted in *args.

        Parameters
        ----------
        *args : iterable of callables
            Each callable recieves an argparser.ArgumentParser as it's
            only argument when initializing the command. If callable
            has a `loader` property it will be provided the final parsed
            args and should return an updated version with it's value loaded.

        Returns
        -------
        callable
        """
        def parse_args(parser, argv):
            loaders = [arg(parser) for arg in args]
            parsed_args = dict(vars(parser.parse_args(argv)))
            # Let one arg depend on anther arg to load
            for loader in loaders:
                if loader:
                    parsed_args = loader(parsed_args)
            return parsed_args

        def inner(fn):
            fn.parse_args = parse_args
            commands[fn.__name__] = fn
            return fn
        return inner

    def main(argv=None):
        argv = sys.argv[1:] if argv is None else argv

        parser = argparse.ArgumentParser()
        parser.add_argument('mode', choices=commands.keys())
        args = parser.parse_args([argv[0]])
        cmd = commands[args.mode]

        parser = argparse.ArgumentParser()
        parser.add_argument('-o', '--outfile', dest='out_path', type=str, required=True),
        args = cmd.parse_args(parser, argv[1:])
        if not os.path.isdir(args['out_path']) \
                and os.path.exists(args['out_path']) \
                and args['out_path'] != '/dev/null':
            # TODO: What to do with directories?
            raise RuntimeError('Output path already exists! ' + args['out_path'])
        DELETE_ON_ERROR.append(args['out_path'])
        try:
            cmd(**args)
        except:  # noqa: E722
            for path_glob in DELETE_ON_ERROR:
                unlink_path_glob(path_glob)
            raise
        finally:
            for path_glob in DELETE_ON_EXIT:
                unlink_path_glob(path_glob)

    main.command = register_command
    return main


with_pkl_df = with_arg('-d', '--dataframe', dest='df', type=load_pkl, required=True)
with_elasticsearch = with_arg(
    '--elasticsearch', dest='es', default='localhost:9200',
    loader=make_loader(elasticsearch.Elasticsearch, 'es', verify_certs=not os.environ.get('RELFORGE_SKIP_CERTS')))
with_sql_vars = with_arg('--sql-vars', dest='sql_vars', type=load_kv_pairs, default={}, required=False)
with_sql_query = with_arg(
    '--sql-query', dest='sql_query', required=True,
    loader=make_loader(load_sql_query, 'sql_query', '?sql_vars', prune=['sql_vars']))
