"""function_score query implementation for explain parser"""
import re

import tensorflow as tf

from relforge_wbsearchentities.explain_parser.core import (
    explain_parser_from_query,
    merge_children,
    parse_list,
    register_parser,

    BaseExplain,
    BaseExplainParser,
    IncorrectExplainException,
    PassThruExplain,
    ProductExplain,
    SumExplain,
    TunableVariableExplain
)
from relforge_wbsearchentities.explain_parser.utils import join_name, isclose

FLT_MAX = 3.4028235e+38  # in elasticsearch
FUNCTION_SCORE_PARSERS = {}


def register_function_score_parser(name):
    def inner(fn):
        assert name not in FUNCTION_SCORE_PARSERS
        FUNCTION_SCORE_PARSERS[name] = fn
        return fn
    return inner


class FunctionScoreFunctionExplainParser(BaseExplainParser):
    def __init__(self, parsers, name_prefix, name=None):
        super(FunctionScoreFunctionExplainParser, self).__init__(name_prefix=name_prefix)
        self.parsers = parsers
        self.name = name

    @staticmethod
    def from_query(options, name_prefix, name=None):
        if 'filter' not in options:
            options['filter'] = {'match_all': {}}
        parsers = {}
        for key, value in options.items():
            try:
                parser = FUNCTION_SCORE_PARSERS[key]
            except KeyError:
                raise Exception('Unknown function score parameter: {}'.format(key))
            else:
                parsers[key] = parser(value, name_prefix)
        return FunctionScoreFunctionExplainParser(parsers, name_prefix=name_prefix, name=name)

    def __repr__(self):
        return '<{}: {}>'.format(
            type(self).__name__,
            ' '.join('{}={}'.format(key, repr(value)) for key, value in self.parsers.items()))

    def parse(self, base_lucene_explain):
        assert base_lucene_explain['description'] == 'function score, product of:'
        assert len(base_lucene_explain['details']) == 2
        filter_lexplain, lucene_explain = base_lucene_explain['details']
        filter_explain = self.parsers['filter'].parse(filter_lexplain)

        assert lucene_explain['description'] == 'product of:'
        parsers = []
        if 'weight' in self.parsers:
            parsers.append(self.parsers['weight'])
        if 'script_score' in self.parsers:
            parsers.append(self.parsers['script_score'])
        else:
            # There will be an extra constant score if no script_score was provided
            assert lucene_explain['details'][0]['description'] == 'constant score 1.0 - no function provided'
            lucene_explain = dict(lucene_explain, details=lucene_explain['details'][1:])
        remaining_parsers, remaining_details, parsed = parse_list(parsers, lucene_explain['details'])
        if remaining_details:
            raise IncorrectExplainException('incomplete match')

        # The weights name ends up being not particularly useful, but we
        # don't want to attach filter name to ourselves as that would
        # double up the name when handling the filter.
        weight_explain = next(x for x in parsed if x.parser_hash == hash(self.parsers['weight']))
        if 'script_score' not in self.parsers:
            weight_explain.name = join_name(filter_explain.name, weight_explain.name)

        score_explain = ProductExplain(lucene_explain, children=parsed, expected_children=len(parsers),
                                       name_prefix=self.name_prefix)
        explain = ProductExplain(
            base_lucene_explain, name=self.name, expected_children=2,
            children=[filter_explain, score_explain], name_prefix=self.name_prefix)
        explain.parser_hash = hash(self)
        return explain

    def merge(self, a, b):
        if a.is_complete:
            return a
        raise NotImplementedError('Unreachable, parsed explains are always complete')


re_float = r'(\d+(?:\.\d*)?)'
re_doc = r"doc\['([^']+)'\]\.value"
re_pow_doc = r"pow\({re_doc} ?, ?{re_float}\)".format(re_doc=re_doc, re_float=re_float)
re_satu = r"{re_pow_doc} / \( {re_pow_doc} \+ pow\({re_float},{re_float}\)\)".format(
    re_pow_doc=re_pow_doc, re_float=re_float)
RE_SATU = re.compile(re_satu)


class FunctionScoreSatuExplainParser(BaseExplainParser):
    def __init__(self, lang, inline, field, a, k, name_prefix):
        super(FunctionScoreSatuExplainParser, self).__init__(name_prefix)
        self.lang = lang
        self.inline = inline
        self.field = field
        self.a = a
        self.k = k
        self.desc = 'script score function, computed with script:"Script{{type=inline, lang=\'{}\', idOrCode=\'{}\', options={{}}, params={{}}}}" and parameters: {{}}'.format(lang, inline)  # noqa: E501

    def parse(self, lucene_explain):
        if lucene_explain['description'] != self.desc:
            raise IncorrectExplainException()
        explain = FunctionScoreSatuExplain(lucene_explain, self.field, self.a, self.k, self.name_prefix)
        explain.parser_hash = hash(self)
        return explain


class FunctionScoreScriptScoreExplainParser(BaseExplainParser):
    def __init__(self, lang, inline, name_prefix):
        super(FunctionScoreScriptScoreExplainParser, self).__init__(name_prefix)
        self.lang = lang
        self.inline = inline
        self.desc = 'script score function, computed with script:"Script{{type=inline, lang=\'{}\', idOrCode=\'{}\', options={{}}, params={{}}}}" and parameters: {{}}'.format(lang, inline)  # noqa: E501

    def __repr__(self):
        return '<{}: lang={}, inline={}>'.format(type(self).__name__, self.lang, self.inline)

    @staticmethod
    @register_function_score_parser('script_score')
    def from_query(options, name_prefix):
        assert len(options) == 1
        # There are more options, but for now support one specific use case
        script = options['script']
        assert len(script) == 2
        satu = RE_SATU.match(script['inline'])
        if satu:
            field = satu.group(1)
            a = float(satu.group(2))
            assert field == satu.group(3)
            assert a == float(satu.group(4))
            k = float(satu.group(5))
            assert a == float(satu.group(6))
            return FunctionScoreSatuExplainParser(
                script['lang'], script['inline'],
                field, a, k, name_prefix)
        else:
            return FunctionScoreScriptScoreExplainParser(script['lang'], script['inline'], name_prefix)

    def parse(self, lucene_explain):
        if lucene_explain['description'] != self.desc:
            raise IncorrectExplainException()
        explain = PassThruExplain(lucene_explain, 'script', name_prefix=self.name_prefix)
        explain.parser_hash = hash(self)
        return explain

    def merge(self, a, b):
        raise Exception('Unreachable, PassThruExplain is always complete')


class FunctionScoreWeightExplainParser(BaseExplainParser):
    def __init__(self, weight, name_prefix):
        super(FunctionScoreWeightExplainParser, self).__init__(name_prefix)
        self.weight = weight

    def __repr__(self):
        return '<{}: {}>'.format(type(self).__name__, self.weight)

    @staticmethod
    @register_function_score_parser('weight')
    def from_query(weight, name_prefix):
        return FunctionScoreWeightExplainParser(weight, name_prefix=name_prefix)

    def parse(self, lucene_explain):
        if lucene_explain['description'] != 'weight':
            raise IncorrectExplainException('Description must be `weight`')
        if not isclose(lucene_explain['value'], self.weight):
            raise IncorrectExplainException('Expected weight of {}'.format(self.weight))
        explain = TunableVariableExplain(lucene_explain, name_prefix=self.name_prefix, name='weight')
        explain.parser_hash = hash(self)
        return explain


class FunctionScoreFilterExplainParser(BaseExplainParser):
    def __init__(self, filter_parser, name_prefix):
        super(FunctionScoreFilterExplainParser, self).__init__(name_prefix=name_prefix)
        self.filter_parser = filter_parser
        self.desc_prefix = "match filter: {}".format(filter_parser.constant_score_desc())

    def __repr__(self):
        return '<{}: {}>'.format(type(self).__name__, self.filter_parser.constant_score_desc())

    @staticmethod
    @register_function_score_parser('filter')
    def from_query(options, name_prefix):
        filter_parser = explain_parser_from_query(options, name_prefix)
        return FunctionScoreFilterExplainParser(filter_parser, name_prefix)

    def parse(self, lucene_explain):
        if not lucene_explain['description'].startswith(self.desc_prefix):
            raise IncorrectExplainException("No match for description prefix")
        # Pass through will give the filter a value of 1 on hits that match the filter,
        # and default to 0 when not provided later
        explain = PassThruExplain(lucene_explain, name_prefix=self.name_prefix,
                                  name=self.filter_parser.constant_score_desc())
        explain.parser_hash = hash(self)
        return explain


class FunctionScoreExplainParser(BaseExplainParser):
    def __init__(self, boost_mode, score_mode, max_boost, query, functions, name_prefix):
        super(FunctionScoreExplainParser, self).__init__(name_prefix)
        self.boost_mode = boost_mode
        self.score_mode = score_mode
        self.max_boost = max_boost
        self.query = query
        self.functions = functions

    @staticmethod
    @register_parser('function_score')
    def from_query(options, name_prefix):
        prefix = join_name(name_prefix, 'function_score')
        options = dict(options)
        query = explain_parser_from_query(options.pop('query', {'match_all': {}}), prefix)
        # Controls how query and function_score combine
        boost_mode = options.pop('boost_mode', 'multiply')
        if boost_mode not in ('sum', 'multiply'):
            raise NotImplementedError('boost_mode only supports sum and multiply, saw {}'.format(boost_mode))
        # Controls how multiple functions are merged together
        score_mode = options.pop('score_mode', 'multiply')
        if score_mode not in ('sum', 'multiply'):
            raise NotImplementedError('score_mode only supports sum and multiply, saw {}'.format(score_mode))
        # Caps the value coming out of score_mode before applying as boost to query
        max_boost = options.pop('max_boost', FLT_MAX)
        if max_boost != FLT_MAX:
            raise NotImplementedError('Only default values of max_boost are supported')
        functions = [FunctionScoreFunctionExplainParser.from_query(f, name_prefix=join_name(prefix, str(i)),
                                                                   name=str(i))
                     for i, f in enumerate(options.pop('functions'))]
        assert len(options) == 0
        return FunctionScoreExplainParser(boost_mode, score_mode, max_boost, query, functions, prefix)

    def parse(self, lucene_explain):
        if self.boost_mode == 'multiply':
            boost_mode_type = ProductExplain
            expected_desc = 'function score, product of:'
        elif self.boost_mode == 'sum':
            boost_mode_type = SumExplain
            # TODO: This can somewhat easily accept unrelated things, and then
            # the assertions will kill the whole parse.
            expected_desc = 'sum of'
        else:
            raise NotImplementedError('Unsupported boost mode {}'.format(self.boost_mode))
        if lucene_explain['description'] != expected_desc:
            raise IncorrectExplainException(
                'Expected description of <{}> but got <{}>'.format(expected_desc, lucene_explain['description']))
        # This top level explain should be boost_mode(query, value).
        assert len(lucene_explain['details']) == 2
        query_lexplain, functions_lexplain = lucene_explain['details']
        # Validate the filter matches what we expect
        query_explain = self.query.parse(query_lexplain)

        # The next level is min(score, max_float). While it could go over, we
        # are going to only support FLT_MAX and pretend the min: doesn't exist either.
        assert functions_lexplain['description'] == 'min of:'
        assert len(functions_lexplain['details']) == 2
        functions_lexplain, max_boost_lexplain = functions_lexplain['details']
        assert self.max_boost == FLT_MAX
        assert max_boost_lexplain == {
          "value": self.max_boost,
          "description": "maxBoost",
          "details": []
        }

        if self.score_mode == 'sum':
            score_mode_type = SumExplain
        elif self.score_mode == 'multiply':
            score_mode_type = ProductExplain
        else:
            raise Exception('Unsupported function score score mode: {}'.format(self.score_mode))

        functions_value = functions_lexplain['value']
        if functions_lexplain['description'] == 'No function matched':
            # This counts as a boost of 1.0 and needs to be represented in the
            # feature vector. Add it to the children and handle it carefully in
            # the merge phase.
            assert functions_lexplain['value'] == 1.0
            functions_lexplain = dict(functions_lexplain, value=0)
            parsed = []
            no_match_value = 1
        else:
            # Double check we have arrived at our top level function score explain
            assert functions_lexplain['description'] == 'function score, score mode [{}]'.format(self.score_mode), \
                (functions_lexplain['description'], self.score_mode)
            remaining_parsers, remaining_details, parsed = parse_list(self.functions, functions_lexplain['details'])
            if remaining_details:
                raise Exception()
            no_match_value = 0
        base_functions_explain = score_mode_type(
            functions_lexplain, expected_children=len(self.functions), children=parsed, name_prefix=self.name_prefix)
        base_functions_explain.parser_hash = hash(self)

        # No match represents as boost of 1.0, so we need a place to inject it.
        no_match_explain = PassThruExplain(
            {'value': no_match_value, 'description': 'No function matched'},
            name='no_function_match', name_prefix=self.name_prefix)
        functions_explain = SumExplain(
            {'value': functions_value, 'description': ''},
            expected_children=2,
            children=[base_functions_explain, no_match_explain], name_prefix=self.name_prefix)

        query_and_functions_explain = boost_mode_type(
            lucene_explain, name='function_score',
            expected_children=2, children=[query_explain, functions_explain], name_prefix=self.name_prefix)
        query_and_functions_explain.parser_hash = hash(self)
        return query_and_functions_explain

    def merge(self, a, b):
        if a.is_complete:
            return a
        if b.is_complete:
            return b

        assert a.children[1].children[1].name == 'no_function_match'
        assert b.children[1].children[1].name == 'no_function_match'
        functions_a = a.children[1].children[0]
        functions_b = b.children[1].children[0]
        assert type(functions_a) == type(functions_b)
        assert type(functions_a) in (SumExplain, ProductExplain)
        assert functions_a.parser_hash == hash(self)
        assert functions_b.parser_hash == hash(self)

        functions_a.children = merge_children(functions_a.children, functions_b.children, self.functions)

        return a


class FunctionScoreSatuExplain(BaseExplain):
    def __init__(self, lucene_explain, field, a, k, name_prefix):
        super(FunctionScoreSatuExplain, self).__init__(
            lucene_explain,
            name=join_name('satu', field),
            expected_children=0,
            name_prefix=name_prefix)
        self.field = field
        self.a = a
        self.k = k

    def reverse_satu(self, value):
        """Calculate satu inputs from output"""
        if value == 0:
            return 0
        a = self.a
        k = self.k
        v = value
        return pow(-((v-1)*pow(k, -a))/v, -1/a)

    def to_tf(self, vecs):
        prefix = join_name(self.name_prefix, self.name)
        a = tf.get_variable(join_name(prefix, 'a'), initializer=self.a)
        k = tf.get_variable(join_name(prefix, 'k'), initializer=self.k)
        x = vecs[prefix]
        pow_x_a = tf.pow(x, a)
        return pow_x_a / (tf.pow(k, a) + pow_x_a)

    def feature_vec(self):
        name = join_name(self.name_prefix, self.name)
        value = self.reverse_satu(self.value)
        return {name: [value]}
