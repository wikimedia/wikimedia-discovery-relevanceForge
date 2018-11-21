"""match, multi_match, similarities, etc. for explain parser"""

from collections import defaultdict
import re

import tensorflow as tf

from relforge.explain_parser.core import (
    BaseExplain,
    BaseExplainParser,
    GlobalConstantExplain,
    IncorrectExplainException,
    PassThruExplain,
    ProductExplain,
    SumExplain,
    TunableVariableExplain,

    merge_children,
    parse_list,
    register_parser,
)
from relforge.explain_parser.utils import isclose, join_name


FLT_MAX = 3.4028235e+38  # in elasticsearch
PARSERS = {}
RE_NAME_FIXER = re.compile(r'[^A-Za-z0-9_.\-/]')


def basic_parser(lucene_explain, name_prefix):
    desc = lucene_explain['description']
    name = None
    children = []
    expected_children = 0
    if desc.startswith('idf, computed as'):
        clazz = PassThruExplain
        name = 'idf'
    elif desc.startswith('termFreq='):
        clazz = PassThruExplain
        name = 'termFreq'
    elif desc == 'parameter b (norms omitted for field)':
        # This isn't even used in the equation, it's a placeholder
        clazz = GlobalConstantExplain
        name = 'b_no_norms'
    elif desc.startswith('parameter '):
        clazz = TunableVariableExplain
        name = desc[len('parameter '):]
    elif desc == 'boost':
        clazz = TunableVariableExplain
        name = desc
    elif desc == 'avgFieldLength':
        clazz = GlobalConstantExplain
        name = desc
    elif desc == 'fieldLength':
        clazz = PassThruExplain
        name = desc
    elif desc.startswith('idf, computed as'):
        clazz = PassThruExplain
        name = 'idf'
    elif desc.startswith('tfNorm, computed as'):
        clazz = TfNormExplain
        name = 'tfNorm'
        expected_children = len(lucene_explain['details'])
        children = [basic_parser(d, name_prefix) for d in lucene_explain['details']]
    else:
        raise NotImplementedError('Unrecognized description: {}'.format(desc))

    return clazz(lucene_explain, name=name, children=children,
                 expected_children=expected_children, name_prefix=name_prefix)


class MatchQueryExplainParser(BaseExplainParser):
    def __init__(self, field, boost, name_prefix):
        super(MatchQueryExplainParser, self).__init__(name_prefix)
        self.field = field
        self.boost = boost
        self.desc_prefix = ['weight({}:'.format(field), 'weight(Synonym({}:'.format(field)]

    def __repr__(self):
        return '<{}: {}^({})>'.format(type(self).__name__, self.field, self.boost)

    def constant_score_desc(self):
        """What this query looks like wrapped in constant score"""
        return self.field

    @staticmethod
    @register_parser('term')
    @register_parser('match')
    def from_query(options, name_prefix):
        if len(options) != 1:
            raise NotImplementedError("only basic form ({field: searchterm}) of term/match query is supported")
        field = next(iter(options.keys()))
        value = options[field]
        if not isinstance(value, str):
            raise IncorrectExplainException('Only simple term/match queries supported: {}'.format(type(options[field])))
        # This fieldname is a slight lie, but we need it to differentiate two
        # function score filters with the same weight. We naively try to guess
        # here if this is a constant query or not
        if '{{query_string}}' not in value.lower():
            field = '{}:{}'.format(field, value)
        return MatchQueryExplainParser(field, options.get('boost', 1.0), name_prefix)

    def _init_similarity_children(self, lucene_details):
        prefix = join_name(self.name_prefix, self.field)
        assert len(lucene_details) == 1
        lucene_explain = lucene_details[0]
        assert lucene_explain['description'].startswith('score(doc=')
        assert lucene_explain['description'].endswith(', product of:')
        # Product here must be tfNorm * idf, or tfNorm * idf * boost. When no boost
        # is presented (for boost = 1.0) add one in so it's tunable.
        if len(lucene_explain['details']) == 2:
            assert not any(d['description'] == 'boost' for d in lucene_explain['details'])
            assert self.boost == 1.0
            lucene_explain = dict(lucene_explain, details=lucene_explain['details'] + [{
                'value': 1.0,
                'description': 'boost',
                'details': [],
            }])
        assert len(lucene_explain['details']) == 3
        children = [basic_parser(d, prefix) for d in lucene_explain['details']]
        product = ProductExplain(
            lucene_explain, children=children,
            expected_children=len(children), name_prefix=prefix)
        return [product]

    def _init_sum_children(self, lucene_details):
        if not all('[PerFieldSimilarity]' in d['description'] for d in lucene_details):
            if any('[PerFieldSimilarity]' in d['description'] for d in lucene_details):
                raise Exception('Mixed PerFieldSimilarity and others')
            raise IncorrectExplainException('Not a PerFieldSimilarity')
        children = []
        for detail in lucene_details:
            detail_children = self._init_similarity_children(detail['details'])
            explain = PerFieldSimilarityExplain(detail, children=detail_children, expected_children=2,
                                                name_prefix=join_name(self.name_prefix, self.field))
            children.append(explain)
        return children

    def parse(self, lucene_explain):
        # A query with a single term is represented differently from
        # multi-term. Make them the same.
        if any(lucene_explain['description'].startswith(prefix) for prefix in self.desc_prefix):
            lucene_explain = {
                'description': 'sum of:',
                'value': lucene_explain['value'],
                'details': [lucene_explain],
            }
        elif lucene_explain['description'] != 'sum of:':
            raise IncorrectExplainException('Not a PerFieldSimilarity or Sum')

        all_children = False
        for child in lucene_explain['details']:
            if not any(child['description'].startswith(prefix) for prefix in self.desc_prefix):
                break
        else:
            all_children = True
        # For some reason the suggest field, only at certain unexplained
        # times, presents as sum(sum(suggest), sum(Synonym(suggest))).
        # Special case with some stupid hacks until we understand why
        if not all_children:
            if self.field != 'suggest':
                raise IncorrectExplainException("Child does not match field")
            if not all(c['description'] == 'sum of:' for c in lucene_explain['details']):
                raise IncorrectExplainException("Children are not sums")
            flat_details = [c2 for c in lucene_explain['details'] for c2 in c['details']]
            lucene_explain = dict(lucene_explain, details=flat_details)
            for child in lucene_explain['details']:
                if not any(child['description'].startswith(prefix) for prefix in self.desc_prefix):
                    raise IncorrectExplainException("Child does not match field")

        children = self._init_sum_children(lucene_explain['details'])
        parsed = PerFieldSumExplain(lucene_explain, children=children, expected_children=len(children),
                                    name_prefix=join_name(self.name_prefix, self.field))
        for child in parsed.children:
            assert isinstance(child, PerFieldSimilarityExplain)
            assert child.field_name == self.field, '{} == {}'.format(child.field_name, self.field)
        parsed.parser_hash = hash(self)
        return parsed

    def merge(self, a, b):
        for x in (a, b):
            assert isinstance(x, PerFieldSumExplain)
            assert x.parser_hash == hash(self)
        # Stupid hack to have a single PerFieldSim per field
        # instead of once per term.
        # TODO: document class with why this works.
        a.children = a.children[0:1]
        a.expected_children = 1
        return a


class MultiMatchQueryExplainParser(BaseExplainParser):
    def __init__(self, fields, boost, match_type, name_prefix):
        super(MultiMatchQueryExplainParser, self).__init__(name_prefix=name_prefix)
        self.fields = fields
        self.query_parsers = []
        for field in fields:
            boost = 1.0
            if '^' in field:
                field, boost = field.split('^', 1)
            self.query_parsers.append(MatchQueryExplainParser(field, boost, self.name_prefix))
        self.boost = boost
        self.match_type = match_type
        # With a single field match_type doesn't matter
        if match_type != 'most_fields':
            raise Exception('Not Implemented, match_type: {}'.format(match_type))

    def __repr__(self):
        return '<{}: [{}]>'.format(
            type(self).__name__,
            ', '.join(repr(parser) for parser in self.query_parsers))

    @staticmethod
    @register_parser("multi_match")
    def from_query(options, name_prefix):
        assert len(options['fields']) > 0
        boost = options.get('boost', 1.0)
        if len(options['fields']) == 1:
            # These present as a MatchQuery. TODO: Check boost handling
            field = options['fields'][0]
            if '^' in field:
                field, field_boost = field.split('^', 1)
                field_boost = float(field_boost)
                boost *= field_boost
            return MatchQueryExplainParser(field, boost, name_prefix)
        else:
            return MultiMatchQueryExplainParser(
                options['fields'], boost, options.get('type', 'best_fields'), name_prefix)

    def parse(self, lucene_explain):
        # If the query had a single term this will roughly be:
        #    (1) sum(weight(a), weight(b), ...
        # Multi term will look like
        #    (2) sum(sum(weight(a1), weight(a2)), ...)
        # Sometimes things look like
        #    (3) sum(sum(weight(a1), sum(sum(weight(a2), ...)))
        # To simplify our lives, flatten all sums until they are gone. Then
        # re-create sums with matching fields that MatchQueryExplainParser
        # can then parse.
        if lucene_explain['description'] != 'sum of:':
            raise IncorrectExplainException('Description must be: sum of:')
        grouped = defaultdict(list)
        # TODO: This appears (?) to work but really needs some test cases
        for child in self.flatten_sums(lucene_explain['details']):
            if not child['description'].startswith('weight('):
                raise IncorrectExplainException("After flattening all children must be weights")
            prefix = child['description'].split(':')[0]
            grouped[prefix].append(child)
        lucene_details = [{
            'description': 'sum of:',
            'value': sum(c['value'] for c in details),
            'details': details,
        } for _, details in grouped.items()]

        remaining_parsers, remaining_details, parsed = parse_list(
                self.query_parsers, lucene_details)
        if remaining_details:
            parse_list(self.query_parsers, lucene_explain['details'], catch_errors=False)
            raise IncorrectExplainException("All children must be consumed")
        if parsed is None:
            raise IncorrectExplainException('Failed to parse similarities')
        sum_explain = SumExplain(lucene_explain, children=parsed, expected_children=len(self.query_parsers),
                                 name_prefix=self.name_prefix)
        sum_explain.parser_hash = hash(self)
        return sum_explain

    def merge(self, a, b):
        # TODO: This is nearly a copy of BoolQueryExplainParser.merge
        for x in (a, b):
            assert isinstance(x, SumExplain)
            assert x.parser_hash == hash(self)
        # Match up sum clauses with our parsers
        a.children = merge_children(a.children, b.children, set(self.query_parsers))
        return a

    def flatten_sums(self, lucene_details):
        for child in lucene_details:
            if child['description'] == 'sum of:':
                for c2 in self.flatten_sums(child['details']):
                    yield c2
            else:
                yield child


class PerFieldSumExplain(SumExplain):
    def __init__(self, *args, **kwargs):
        super(PerFieldSumExplain, self).__init__(*args, **kwargs)
        assert isclose(self.value, float(sum(c.value for c in self.children)))
        assert all(isinstance(c, PerFieldSimilarityExplain) for c in self.children)
        assert len(set(c.field_name for c in self.children)) == 1
        self.field_name = self.children[0].field_name

    def child_tensor(self, vecs):
        # We only have a single field (todo: how to we know?) so we only
        # need a single equation. feture_vec will merge multiple children
        # into the same vectors. Essentially vectors in vecs will be
        # (batch_size, n) rather than (batch_size, 1) like in most explains.
        return self.children[0].to_tf(vecs)

    def feature_vec(self):
        data = defaultdict(list)
        for child in self.children:
            for k, v in child.feature_vec().items():
                data[k].extend(v)

        # Every child must return the same variables every time
        assert(len(set(len(x) for x in data.values()))) == 1
        return data

    def __str__(self):
        return '{} {}: {:.2f}, {}'.format(
            type(self).__name__, self.field_name, self.value, self.description)


class PerFieldSimilarityExplain(BaseExplain):
    desc_re = re.compile(r'weight\((?:Synonym\()?([\w.]+):(.*) in .*\) \[PerFieldSimilarity\].*')

    def __init__(self, *args, **kwargs):
        super(PerFieldSimilarityExplain, self).__init__(*args, **kwargs)
        self.field_name = self.desc_re.match(self.description).group(1)
        # Always a single child,
        assert len(self.children) == 1
        assert isinstance(self.children[0], ProductExplain)
        self.expected_children = 1

    def to_tf(self, vecs):
        return self.children[0].to_tf(vecs)

    def feature_vec(self):
        return self.children[0].feature_vec()


class TfNormExplain(BaseExplain):
    DESC_ALIAS = {
        'termFreq=': 'termFreq',
        'parameter k1': 'k1',
        'parameter b': 'b'
    }
    NO_NORMS_DESC = 'tfNorm, computed as (freq * (k1 + 1)) / (freq + k1) from:'
    W_NORMS_DESC = (
        'tfNorm, computed as ' +
        '(freq * (k1 + 1)) / (freq + k1 * (1 - b + b * fieldLength / avgFieldLength)) from:')

    def __init__(self, *args, **kwargs):
        super(TfNormExplain, self).__init__(*args, **kwargs)
        self.bm25_no_norms = self.description == self.NO_NORMS_DESC
        self.bm25 = not self.bm25_no_norms and self.description == self.W_NORMS_DESC
        assert self.bm25 or self.bm25_no_norms
        child_names = {c.name for c in self.children}
        if self.bm25:
            assert child_names == {'termFreq', 'k1', 'b', 'fieldLength', 'avgFieldLength'}, child_names
        else:
            if child_names != {'termFreq', 'k1', 'b_no_norms'}:
                print(self.children)
                raise Exception()

    def to_tf(self, vecs):
        children = {c.name: c for c in self.children}
        termFreq = children['termFreq'].to_tf(vecs)
        k1 = children['k1'].to_tf(vecs)
        if self.bm25:
            b = children['b'].to_tf(vecs)
            fieldLength = children['fieldLength'].to_tf(vecs)
            # Hits that don't match will still be calculated here with their
            # vectors padded with zeros. We have to add epsilon to prevent
            # dividing by zero.
            epsilon = tf.constant(1e-6)
            avgFieldLength = children['avgFieldLength'].to_tf(vecs) + epsilon
            denom = termFreq + k1 * (1 - b + b * fieldLength / avgFieldLength)
        else:
            denom = termFreq + k1
        return tf.identity((termFreq * (k1 + 1)) / denom, name=join_name(self.name_prefix, self.name))
