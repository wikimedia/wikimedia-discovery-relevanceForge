import tensorflow as tf

from relforge.explain_parser.core import (
    explain_parser_from_query,
    merge_children,
    parse_list,
    register_parser,

    BaseExplain,
    BaseExplainParser,
    IncorrectExplainException,
)
from relforge.explain_parser.utils import join_name


class DisMaxQueryExplainParser(BaseExplainParser):
    def __init__(self, query_parsers, tie_breaker, name_prefix):
        super(DisMaxQueryExplainParser, self).__init__(name_prefix=name_prefix)
        self.query_parsers = query_parsers
        self.idx_lookup = {hash(parser): i for i, parser in enumerate(query_parsers)}
        self.tie_breaker = tie_breaker
        if tie_breaker == 0.0:
            self.desc = 'max of:'
        else:
            # TODO: float formatting?
            self.desc = 'max plus {} times others of:'.format(tie_breaker)

    def __repr__(self):
        return '<{}: [{}]>'.format(
            type(self).__name__,
            ', '.join(repr(parser) for parser in self.query_parsers))

    @staticmethod
    @register_parser("dis_max")
    def from_query(options, name_prefix):
        options = dict(options)
        prefix = join_name(name_prefix, 'dismax')
        queries = [explain_parser_from_query(q, join_name(prefix, str(idx)))
                   for idx, q in enumerate(options.pop('queries'))]
        tie_breaker = options.pop('tie_breaker', 0.0)
        if len(queries) == 1:
            return queries[0]
        return DisMaxQueryExplainParser(queries, tie_breaker, name_prefix=name_prefix)

    def parse(self, lucene_explain):
        if lucene_explain['description'] != self.desc:
            raise IncorrectExplainException('Explain must be: {}'.format(self.desc))
        remaining_parsers, remaining_details, parsed = parse_list(
                self.query_parsers, lucene_explain['details'])
        if remaining_details:
            parse_list(remaining_parsers, remaining_details, catch_errors=False)
            raise IncorrectExplainException('All details must be consumed')

        dis_max = DisMaxExplain(
            lucene_explain=lucene_explain, name_prefix=self.name_prefix, name='dismax', children=parsed,
            expected_children=len(self.query_parsers),
            tie_breaker=self.tie_breaker)
        dis_max.parser_hash = hash(self)
        return dis_max

    def merge(self, a, b):
        for x in (a, b):
            assert isinstance(x, DisMaxExplain)
            assert x.parser_hash == hash(self)
        a.children = merge_children(a.children, b.children, set(self.query_parsers))
        a.value = float('nan')
        return a


class DisMaxExplain(BaseExplain):
    def __init__(self, tie_breaker, *args, **kwargs):
        super(DisMaxExplain, self).__init__(*args, **kwargs)
        self.tie_breaker = float(tie_breaker)

    def to_tf(self, vecs):
        prefix = join_name(self.name_prefix, self.name)
        child_tensors = [child.to_tf(vecs) for child in self.children]
        child_tensors = [tensor for tensor in child_tensors if tensor is not None]
        if not child_tensors:
            return tf.constant(0.0, name=prefix)

        stack = tf.stack(child_tensors, axis=2)  # shape (?, 1, n_child)
        # top = max(x)
        top = tf.reduce_max(stack, axis=2)  # shape (?, 1)
        # total = sum(x)
        total = tf.reduce_sum(stack, axis=2)
        # rework algebra to only use max and sum once(does that matter?)
        # dismax = max(x) + tie_breaker * (sum(x) - max(x)))
        # = a + b(c - a)
        # = bc + a(1 - b)
        tie_breaker = tf.get_variable(
            join_name(prefix, 'tie_breaker'),
            initializer=self.tie_breaker)
        return tie_breaker * total + top * (1 - tie_breaker)
