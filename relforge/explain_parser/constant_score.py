import tensorflow as tf

from relforge.explain_parser.core import (
    BaseExplain,
    BaseExplainParser,
    IncorrectExplainException,

    explain_parser_from_query,
    register_parser,
)
from relforge.explain_parser.utils import join_name, isclose


class ConstantScoreExplainParser(BaseExplainParser):
    def __init__(self, boost, filter_parser, name_prefix):
        super(ConstantScoreExplainParser, self).__init__(name_prefix=name_prefix)
        self.boost = boost
        self.filter_parser = filter_parser
        self.desc_prefix = 'ConstantScore({}:'.format(filter_parser.constant_score_desc())

    def __repr__(self):
        return '<{}: {} = {}>'.format(type(self).__name__, self.filter_parser.constant_score_desc(), self.boost)

    @staticmethod
    @register_parser('constant_score')
    def from_query(options, name_prefix):
        assert len(options) == 2
        filter_parser = explain_parser_from_query(options['filter'], name_prefix)
        return ConstantScoreExplainParser(options['boost'], filter_parser, name_prefix)

    def parse(self, lucene_explain):
        if not lucene_explain['description'].startswith(self.desc_prefix):
            raise IncorrectExplainException('Not the expected ConstantScore prefix')
        if not isclose(lucene_explain['value'], self.boost):
            raise IncorrectExplainException('Wrong boost')
        explain = ConstantExplain(lucene_explain, self.filter_parser.constant_score_desc(),
                                  name_prefix=self.name_prefix)
        explain.parser_hash = hash(self)
        explain.expected_children = 0
        return explain

    def merge(self, a, b):
        # Should be nothing to merge. Assert they have same value to ensure it's the same thing
        assert a.parser_hash == hash(self)
        assert b.parser_hash == hash(self)
        assert a.value == b.value
        return a


class ConstantExplain(BaseExplain):
    def __init__(self, lucene_explain, field, name_prefix, name='constant_score'):
        super(ConstantExplain, self).__init__(lucene_explain=lucene_explain, name_prefix=name_prefix, name=name)
        self.field = field

    def feature_vec(self):
        # 1 or 0 for hit/miss. Basically 1, because misses dont get explains and
        # default to 0.
        prefix = join_name(join_name(self.name_prefix, self.name), self.field)
        return {prefix: [1.0]}

    def to_tf(self, vecs):
        prefix = join_name(join_name(self.name_prefix, self.name), self.field)
        boost = join_name(prefix, 'boost')
        return vecs[prefix] * tf.get_variable(boost, initializer=self.value)
