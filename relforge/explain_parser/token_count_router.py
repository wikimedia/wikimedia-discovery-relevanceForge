from relforge.explain_parser.core import (
    BaseExplainParser,
    IncorrectExplainException,
    explain_parser_from_query,
    SumExplain,
    merge_children,
    parse_list,
    register_parser,
)


class TokenCountRouterExplainParser(BaseExplainParser):

    def __init__(self, name_prefix, queries):
        super(TokenCountRouterExplainParser, self).__init__(name_prefix)
        self.queries = queries

    @staticmethod
    @register_parser("token_count_router")
    def from_query(query, name_prefix):
        queries = [explain_parser_from_query(q['query'], name_prefix) for q in query['conditions']]
        queries.append(explain_parser_from_query(query['fallback'], name_prefix))
        return TokenCountRouterExplainParser(name_prefix, queries)

    def parse(self, lucene_explain):
        remaining_parsers, remaining_details, parsed = parse_list(self.queries, [lucene_explain])
        assert len(parsed) == 1
        assert len(remaining_details) == 0
        expected = sum([1 for q in self.queries if not isinstance(q, MatchNoneExplainParser)])
        exp = SumExplain(lucene_explain, self.name_prefix, children=parsed, expected_children=expected)
        exp.parser_hash = hash(self)
        return exp

    def merge(self, a, b):
        merge_children(a, b, self.queries)


class MatchNoneExplainParser(BaseExplainParser):

    @staticmethod
    @register_parser("match_none")
    def from_query(query, name_prefix):
        assert len(query) == 0
        return MatchNoneExplainParser(name_prefix)

    def parse(self, lucene_explain):
        raise IncorrectExplainException('This parser should never be triggered as'
                                        'it never appears in the explanation')

    def merge(self, a, b):
        raise IncorrectExplainException('This parser should never be triggered as'
                                        'it never appears in the explanation')
