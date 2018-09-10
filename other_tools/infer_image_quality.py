#!/usr/bin/env python

"""
Small spark to:
- load queries from a text
- extract pageIds and thumb URLs using the action API
- download image
- run Miriam's quality model
- output a csv file in the local folder

Contains a bunch of hardcoded paths
"""
import tensorflow as tf
import requests
import os
import sys
from time import gmtime, strftime

try:
    import pyspark
except ImportError:
    import findspark
    findspark.init()
    import pyspark

import json
from pyspark.sql import SparkSession, SQLContext
from pyspark.sql import Row
import argparse
from collections import defaultdict
from concurrent import futures
import csv
import glob
import json
import os.path
import random
import re
import sys
import tarfile
import time

from os import listdir
from os.path import isfile, join
import numpy as np
import pyspark.sql
from pyspark.sql import types as T
import requests
from six.moves import urllib
import tensorflow as tf

HEADERS = requests.utils.default_headers()
HEADERS.update({'User-Agent': 'Image Quality Bot (see T202339)'})


def proxies():
    cluster = 'eqiad'  # if random.random() > 0.5 else 'codfw'
    return {
        'http': 'http://webproxy.{}.wmnet:8080/'.format(cluster),
        'https': 'https://webproxy.{}.wmnet:8080/'.format(cluster),
    }


def create_graph():
    """Creates a graph from saved GraphDef file and returns a saver."""
    # Creates graph from saved graph_def.pb.
    local_model_path = pyspark.SparkFiles.get('output_graph_new.pb')
    with tf.gfile.FastGFile(local_model_path, 'rb') as f:
        graph_def = tf.GraphDef()
        graph_def.ParseFromString(f.read())
        _ = tf.import_graph_def(graph_def, name='')


def fetch_result_urls(q):
    params = {
        'action': 'query',
        'format': 'json',
        'prop': 'imageinfo',
        'generator': 'search',
        'formatversion': 2,
        'iiprop': 'url',
        'iiurlwidth': 600,
        'gsrsearch': q + ' filetype:bitmap',
        'gsrnamespace': 6,
        'gsrlimit': 50,  # due to hardlimit of iiurlwidth
        'gsroffset': 0,
        'gsrinfo': '',
        'gsrprop': ''
    }
    with requests.Session() as sess:
        hasMore = True
        offset = 0
        while hasMore:
            params['gsroffset'] = offset
            response = sess.post('https://commons.wikimedia.org/w/api.php',
                                 timeout=120, data=params, headers=HEADERS,
                                 proxies=proxies())
            if response.status_code >= 400:
                time.sleep(10)
                continue
            time.sleep(0.1)
            resp = response.json()
            if 'continue' in resp:
                offset += 50
                hasMore = offset < 8000
            else:
                hasMore = False

            if 'query' not in resp:
                if 'batchcomplete' not in resp or not resp['batchcomplete']:
                    raise ValueError(json.dumps(resp))
                hasMore = False
                continue

            for page in resp['query']['pages']:
                pageId = page['pageid']
                info = page['imageinfo'][0]
                url = info['thumburl'] if 'thumburl' in info else info['url']
                yield pageId, q, url


def buffer_images(image_infos):
    from requests.adapters import HTTPAdapter
    from requests.exceptions import ConnectionError, RetryError
    from requests.packages.urllib3.util.retry import Retry
    from requests_futures.sessions import FuturesSession

    with FuturesSession(max_workers=10) as session:
        retries = defaultdict(int)

        def on_complete(future, page_id, query, url):
            try:
                res = future.result()
                if res.status_code == 200:
                    log('success ' + url)
                    yield page_id, query, url, res.content
                elif (res.status_code == 429 or res.status_code == 503) \
                        and retries[future] < 5:
                    # We can't really pause the in-progress requests be we can
                    # at least stop adding new ones for a bit.
                    # Sleep for 10, 20, 40 seconds
                    if res.status_code == 429:
                        time.sleep(10 * (2 ** (retries[future])))
                    log('retry ' + url)
                    next_future = session.get(url, timeout=120, proxies=proxies())
                    retries[next_future] = retries[future] + 1
                    fs[next_future] = (page_id, query, url)
                # else:
                    # yield page_id, query, title, url, None
            except Exception as e:
                if retries[future] < 5:
                    time.sleep(10 * ((retries[future])))
                    log('retry ' + url)
                    next_future = session.get(url, timeout=120, proxies=proxies())
                    retries[next_future] = retries[future] + 1
                    fs[next_future] = (page_id, query, url)
            finally:
                if future in retries:
                    del retries[future]

        fs = {}
        for page_id, query, url in image_infos:
            log('push ' + url)
            future = session.get(url, timeout=120, proxies=proxies())
            fs[future] = (page_id, query, url)
            while len(fs) >= 10:
                done_and_not_done = futures.wait(fs.keys(),
                                                 return_when=futures.FIRST_COMPLETED)
                for future in done_and_not_done.done:
                    image_info = fs[future]
                    del fs[future]
                    yield from on_complete(future, *image_info)  # noqa: E999
        for future in futures.as_completed(fs):
            yield from on_complete(future, *fs[future])  # noqa: E999


def fetch_image_data(images):
        with requests.Session() as sess:
            for pageId, q, url in images:
                retries = 0
                while retries < 10:
                    log('[' + str(retries) + '] trying to fetch' + url)

                    try:
                        resp = sess.get(url, headers=HEADERS, timeout=120, proxies=proxies())
                    except Exception as e:
                        retries += 1
                        log('[' + str(retries) + '] ' + str(e) + ', sleeping ' + str(10*retries))
                        time.sleep(10*retries)
                        continue

                    if resp.status_code == 429 or resp.status_code == 503:
                        # 503 are quite common :(
                        retries += 1
                        log('[' + str(retries) + '] ' +
                            str(resp.status_code) + ', sleeping ' + str(10*retries))
                        time.sleep(10*retries)
                        continue
                    elif resp.status_code >= 400:
                        raise ValueError('Cannot dl image ' + str(resp.status_code) + ' : ' + url)
                    yield pageId, q, url, resp.content
                    log('Fetched ' + url)
                    break


def log(s):
    print(strftime("%H:%M:%S ", gmtime()) + s + '\n')


def infer_img_qual(images):
    session_conf = tf.ConfigProto(intra_op_parallelism_threads=10, inter_op_parallelism_threads=10)
    create_graph()
    with tf.Session(config=session_conf) as sess:
        # 'softmax:0': A tensor containing the normalized prediction across
        #   1000 labels.
        # 'pool_3:0': A tensor containing the next-to-last layer containing 2048
        #   float description of the image.
        # 'DecodeJpeg/contents:0': A tensor containing a string providing JPEG
        #   encoding of the image.
        # Runs the softmax tensor by feeding the image_data as input to the graph.
        softmax_tensor = sess.graph.get_tensor_by_name('final_result:0')

        for pageId, q, url, imgbytes in images:
            try:
                predictions = sess.run(softmax_tensor, {'DecodeJpeg/contents:0': imgbytes})
                yield Row(pageId=pageId, query=q, url=url, score=float(predictions[0][1]), error='')
            except Exception as e:
                yield Row(pageId=pageId,
                          query=q, url=url, score=float('nan'),
                          error='{}: {}'.format(type(e).__name__, str(e)))


def toRow(d):
    pId, q, url = d
    return Row(pageId=pId, query=q, url=url)


def main():
        conf = pyspark.SparkConf()
        sc = pyspark.SparkContext(appName="commons_image_qual_experiment")
        spark = SparkSession(sc)
        sqlContext = SQLContext(sc)
        sc.addFile('/srv/home/dcausse/commons_img_quality/output_graph_new.pb')
        queries = sc.textFile('/user/dcausse/image_qual/commons_queries_handpicked.lst')

        df = (queries.repartition(40)
              .flatMap(fetch_result_urls)
              .repartition(200)
              .mapPartitions(buffer_images)
              .mapPartitions(infer_img_qual)
              .toDF())
        f = open("preds.csv", "w")
        f.write('pageId,score\n')
        for r in df.collect():
                f.write(str(r['pageId']) + ',' + str(r['score']) + '\n')
        f.close()


if __name__ == '__main__':
        main()
