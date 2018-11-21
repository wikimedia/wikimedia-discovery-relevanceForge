from relforge.explain_parser.core import (
    BaseExplainParser,
    IncorrectExplainException,
    SumExplain,

    explain_parser_from_query,
    merge_children,
    parse_list,
    register_parser,
)
from relforge.explain_parser.utils import print_explain


class BoolQueryExplainParser(BaseExplainParser):
    def __init__(self, should, must, has_filter, name_prefix):
        super(BoolQueryExplainParser, self).__init__(name_prefix)
        self.should = should
        self.must = must
        self.has_filter = has_filter

    def __repr__(self):
        return '<{}: must [{}] should[{}]>'.format(
            type(self).__name__,
            ', '.join(repr(parser) for parser in self.must),
            ', '.join(repr(parser) for parser in self.should))

    @staticmethod
    @register_parser("bool")
    def from_query(options, name_prefix):
        should = [explain_parser_from_query(q, name_prefix) for q in options.get('should', [])]
        must = [explain_parser_from_query(q, name_prefix) for q in options.get('must', [])]
        return BoolQueryExplainParser(should, must, 'filter' in options, name_prefix)

    def parse(self, lucene_explain):
        if lucene_explain['description'] != 'sum of:':
            raise IncorrectExplainException('Bool must have `sum of:` description')

        lucene_details = list(lucene_explain['details'])
        parsed = []
        # Filter is always (hopefully?) the last entry in details
        if self.has_filter:
            # Multiple filters can be represented here?
            filter_explain = lucene_details[-1]
            lucene_details = lucene_details[:-1]
            if 'match on required clause, product of:' not in filter_explain['description']:
                raise IncorrectExplainException('Filter clause not found')
            # Note that we don't actually know this is our filter, that will require
            # inspecting child['details'] and comparing to our actual filter. We mostly
            # depend on should/must parsers to find which bool explain's are ours and only
            # verify here that this explain has a filter attached to the explain.
            assert filter_explain['value'] == 0.0

        # must and should will be mixed together in lucene_details. Parse out one,
        # then the other from the remainders.
        if self.must:
            try:
                remaining_parsers, remaining_details, parsed_must = parse_list(self.must, lucene_details)
            except IncorrectExplainException:
                # We have a must clause but it's not in the explain
                raise IncorrectExplainException('Must clause not found')
            else:
                if len(remaining_parsers):
                    raise IncorrectExplainException('{} parsers remaining in must clause', len(remaining_parsers))
                parsed.extend(parsed_must)
                lucene_details = remaining_details

        remaining_parsers = None
        if self.should:
            # At this point we must have a single item in details
            # TODO: this condition isn't quite so simple, but this seems to work..
            should_required = not self.must and not self.has_filter
            try:
                remaining_parsers, remaining_details, parsed_should = parse_list(self.should, lucene_details)
                if should_required and len(remaining_parsers) == len(self.should):
                    raise IncorrectExplainException('No parsers were accepted')
                parsed.extend(parsed_should)
                lucene_details = remaining_details
            except IncorrectExplainException:
                if should_required:
                    raise IncorrectExplainException('Should clause not found')
                if remaining_parsers is None:
                    remaining_parsers = self.should

        if lucene_details:
            # This wouldn't be very useful to throw directly, everything ends up bubbling up
            # to the top level bool and erroring there. Try again without catching errors on
            # the remainders to get a hopefully more useful error.
            print('Q'*80)
            print('Has Filter: {}'.format(self.has_filter))
            print('Parsed out: {}'.format(len(parsed)))
            print('Remaining:')
            for x in lucene_details:
                print_explain(x, '\t')
            if self.should:
                print('Should:')
                print("\t" + "\n\t".join([str(x) for x in self.should]))
            if self.must:
                print("Must:")
                print("\t" + "\n\t".join([str(x) for x in self.must]))
            print('W'*80)
            if remaining_parsers:
                parse_list(remaining_parsers, lucene_details, catch_errors=False)
            raise IncorrectExplainException('{} children remain unclaimed'.format(len(lucene_details)))
        expected_children = len(self.should) + len(self.must)
        sum_explain = SumExplain(lucene_explain,
                                 children=parsed,
                                 expected_children=expected_children,
                                 name_prefix=self.name_prefix)
        sum_explain.parser_hash = hash(self)
        return sum_explain

    def merge(self, a, b):
        for explain in (a, b):
            assert isinstance(explain, SumExplain)
            assert explain.parser_hash == hash(self)

        # Match up sum clauses with our parsers
        all_parsers = set(self.should + self.must)
        a.children = merge_children(a.children, b.children, all_parsers)
        return a
