"""Parse elasticsearch explains into tensorflow graphs

== Usage

The primary entry point for users of the explain_parser library is
`explain_parser_from_root`. This accepts the same query that would be passed to
elasticsearch _search endpoint and returns a RootExplainParser object. The
query passed in here must have any places that would be replaced with a users
search terms set to `{{query_string}}`.

    import relforge.explain_parser as ep
    parser = ep.explain_parser_from_root({'query': {'match': {'title': '{{query_string}}'}}})

Individual hits can be parsed into Explain instances:

    import elasticsearch
    es = elasticsearch.Elasticsearch()
    res = es.search(index='fizzbuzz', body={'query': {'match': {'title': 'zamboni'}}})
    explains = ep.parse_hits(parser, res['hits']['hits'])

Feature vectors can be extracted from the individual explains and written to .tfrecords:

    import tensorflow as tf
    writer = tf.python_io.TFRecordWriter(out_path)
    for explain in explains:
        example = tf.train.Example(features=tf.train.Features(features=dict({
            'lucene_value': tf.train.Feature(float_list=tf.train.FloatList(value=[explain.value])),
        }, **{
            name: tf.train.Feature(float_list=tf.train.FloatList(value=value))
            for name, value in explain.feature_vec('fizzbuzz').items()
        }))
        writer.write(example.SerializeToString())

The extracted vectors can be read back in:

    def parse_record(example_proto):
        return tf.parse_single_example(example_proto, {
            name: tf.VarLenFeature(dtype=tf.float32)
            for name in merged_explain.feature_vec('fizzbuzz').keys()
        })

    def decode_sparse(parsed_features)
        for k, v in parsed_features.items()
            if isinstance(v, (tf.SparseTensor, tf.sparse.SparseTensor)):
                parsed_features[k] = tf.sparse.to_dense(v)
        return parsed_features

    dataset = (
        tf.data.TFRecordDataset(in_path)
        .map(parse_record)
        .batch(65535)
        .map(decode_sparse))

Many explains can be merged together to generate a more complete scoring equation:

    merged_explain = None
    for query in [...]:
        res = es.search(...)
        merged_explain = ep.merge_explains(parser, ep.parse_hits(parser, hits), merged_explain)
        if merged_explain.is_complete:
            break

The merged explain can generate a scoring op that runs against the dataset. At this
point variables can be tuned and scoring evaluated after changing various values.

    iterator = dataset.make_one_shot_iterator()
    next_batch = iterator.get_next()
    score_op = merged_explain.to_tf(next_batch, 'fizzbuzz')
"""

from relforge.explain_parser import core
# Must import all the other modules to have their
# parsers registered
import relforge.explain_parser.bool
import relforge.explain_parser.constant_score
import relforge.explain_parser.dis_max
import relforge.explain_parser.function_score
import relforge.explain_parser.match_all
import relforge.explain_parser.match  # noqa: F401
import relforge.explain_parser.token_count_router  # noqa: F401


__all__ = [
    'explain_parser_from_root', 'explain_parser_from_query', 'register_parser',
    'parse_hits', 'merge_explains',
]

explain_parser_from_root = core.RootExplainParser.from_query
explain_parser_from_query = core.explain_parser_from_query
register_parser = core.register_parser


def parse_hits(parser, hits):
    """Parse hits from search response into doc_id and explain objects

    Parameters
    ----------
    parser : core.RootExplainParser
    hits : iterable of hits from elasticsearch _search api

    Yields
    ------
    doc_id : str
    explain : core.BaseExplain
    """
    for doc in hits:
        if doc['_score'] == 0:
            # Experience says if this happens the explain wont help much
            continue
        explain = parser.parse(doc['_explanation'])
        yield doc['_id'], explain


def merge_explains(parser, explains, base_explain=None):
    """Merge explains from parse_hits into base_explain

    Parameters
    ----------
    parser : core.RootExplainParser
    explains : iterable of (str, core.BaseExplain)
    base_explain : core.BaseExplain or None

    Returns
    -------
    core.BaseExplain
    """
    for doc_id, explain in explains:
        if base_explain is None:
            base_explain = explain
        else:
            base_explain = parser.merge(base_explain, explain)
        if base_explain.is_complete:
            break
    return base_explain
