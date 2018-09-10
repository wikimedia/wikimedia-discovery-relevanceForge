#!/usr/bin/env python

# jsondiff.py - a somewhat smarter search result JSON diff tool
#
# This program does diffs of two files with one JSON blob per line,
# outputting one color-coded HTML diff per line into a target directory.
# It performs a diff on the ordered list of results (based on a key value,
# either docId or title). It then notes differences within the details of
# a given result.
#
# It has a number of hacks specific to diffing JSON from CirrusSearch
# results, including munging "searchmatch" markup and bolding elements
# that are most important in comparing results, and numbering results.
#
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301, USA.
# http://www.gnu.org/copyleft/gpl.html

import argparse
import difflib
import json
import os
import sys
from itertools import izip_longest
import urllib


def add_nums_to_results(results):
    res_count = 1
    if 'rows' in results:
        for result in results['rows']:
            result['relLabItemNumber'] = res_count
            res_count += 1
    return results


def extract_ids(results, key):
    retval = []
    if 'rows' in results:
        for result in results['rows']:
            retval.append(result[key])
    return retval


def ascii(the_string):
    if type(the_string) is int:
        return str(the_string)
    return the_string.encode('ascii', 'xmlcharrefreplace')


def munge_explanation(results):
    if 'rows' not in results:
        return {}
    for result in results['rows']:
        if 'explanation' not in result:
            continue
        explanation = result['explanation']
        del result['explanation']
        if explanation:
            result['|scores'] = {
                '1. main': get_main_score(explanation),
                '2. primary': get_primary_score(explanation),
                '3. phrase': get_phrase_score(explanation),
                '4. function': get_function_score(explanation)
            }


def get_main_score(exp):
    return exp['value']


def get_primary_score(exp):
    if has_phrase_rescore(exp):
        return exp['details'][0]['details'][0]['details'][0]['value']
    else:
        return exp['details'][0]['value']


def get_phrase_score(exp):
    if has_phrase_rescore(exp):
        return exp['details'][0]['details'][0]['details'][1]['value']
    else:
        return "N/A"


def get_function_score(exp):
    return exp['details'][0]['value']


def has_phrase_rescore(exp):
    is_ph = ''
    details3 = exp['details'][0]['details'][0]['details'][1]
    if 'details' in details3 and len(details3['details']) > 1:
        details4 = details3['details'][1]
        if 'description' in details4:
            is_ph = details4['description']
    return is_ph == 'secondaryWeight'


def make_map(apageids, bpageids):
    amap = {}
    bmap = {}
    union = list(set(apageids) | set(bpageids))
    for id in union:
        if id in apageids:
            aindex = apageids.index(id) + 1
        else:
            aindex = 0
        if id in bpageids:
            bindex = bpageids.index(id) + 1
        else:
            bindex = 0
        amap[aindex] = bindex
        bmap[bindex] = aindex  # don't care if 0 gets overwritten
    return amap, bmap


def add_diffs(aresults, bresults, key):
    if 'rows' in aresults and 'rows' in bresults:
        arows = aresults['rows']
        brows = bresults['rows']
        for aresult in arows:
            bresult = next((x for x in brows if aresult[key] == x[key]), None)
            if bresult:
                for item in aresult.keys():
                    if item in bresult:
                        add_diff_sub(aresult, bresult, item)


def add_diff_sub(aresult, bresult, item):
    if not (aresult and bresult):
        return
    try:
        aresult[item] and bresult[item]
    except IndexError:
        return
    except KeyError:
        return
    if not aresult[item]:
        return
    if not bresult[item]:
        return
    my_type = type(aresult[item]).__name__
    if my_type in ('unicode', 'str', 'float', 'int', 'long', 'complex'):
        if aresult[item] != bresult[item]:
            aresult[item] = diff_span(ascii(unicode(aresult[item])))
            bresult[item] = diff_span(ascii(unicode(bresult[item])))
    elif my_type in ('dict'):
        for subitem in aresult[item].keys():
            add_diff_sub(aresult[item], bresult[item], subitem)
    elif my_type in ('list', 'tuple'):
        for idx, subitem in enumerate(item):
            add_diff_sub(aresult[item], bresult[item], idx)


def diff_span(item):
    return "<span class='diff'>" + str(item) + "</span>"


def html_results(results, map, filename, key, wiki_url='', explain_url='', baseline=True):
    retval = ''
    this_class = 'baseline'
    this_heading = 'BASELINE'
    this_id = 'base'
    this_missing_class = 'ranklost'
    this_missing_text = '&middot;'

    if not baseline:
        this_class = 'delta'
        this_heading = 'DELTA'
        this_id = 'delta'
        this_missing_class = 'ranknew'
        this_missing_text = '*'

    query = ''
    if 'query' in results:
        query = results['query']
    explain = explain_url + "&search=" + urllib.quote_plus(query.encode('utf-8'))
    query = ascii(query)

    totalHits = ''
    if 'totalHits' in results:
        totalHits = results['totalHits']
    retval = '''\
<div class={}>
<b>{}</b><br>
<span class=indent>{}</span>
    <div>
        <div class=query>
        <b>query:</b> {} [<a href="{}">explain</a>]<br>
        <b>totalHits:</b> {}
        </div>
    <b>results:</b>\n'''.format(this_class, this_heading, filename, query, explain, totalHits)

    res_count = 1
    if 'rows' in results:
        for result in results['rows']:
            mapto = map[res_count]
            extra = ''
            if res_count == mapto:
                rankclass = 'ranksame'
            elif mapto == 0:
                rankclass = this_missing_class
                extra = ' ' + this_missing_text
            elif res_count > mapto:
                if baseline:
                    rankclass = 'rankup'
                    extra = ' &uarr;' + str(res_count - mapto)
                else:
                    rankclass = 'rankdown'
                    extra = ' &darr;' + str(res_count - mapto)
            else:
                if baseline:
                    rankclass = 'rankdown'
                    extra = ' &darr;' + str(mapto - res_count)
                else:
                    rankclass = 'rankup'
                    extra = ' &uarr;' + str(mapto - res_count)

            if baseline:
                comp1, comp2 = res_count, mapto
            else:
                comp1, comp2 = mapto, res_count

            title = ascii(result['title'])
            link = wiki_url + title
            retval += '''\

        <div class=result id={0:}{1:}>
            <span class={2:} onclick="comp({3:},{4:},'{0:}{1:}')"><b>{1:}</b>{5:}</span>
                <b>title:</b> <a href="{7:}">{6:}</a><br>
            <div class=indent>
                '''.format(this_id, res_count, rankclass, comp1, comp2,
                           extra, title, link)
            if key != 'title':
                retval += "<b>{0:}:</b> {1:}<br>".format(key, ascii(result[key]))

            if 'score' in result:
                retval += '''\
                    <b>score:</b> {0:}<br>\n'''.format(result['score'])

            for item in sorted(result.keys()):
                if item not in ('docId', 'score', 'title'):
                    retval += html_result_item(result[item], item)

            retval += '''\

            </div>
        </div>\n'''

            res_count += 1

    retval += '''\

    <div class=lastresult id={}{}></div>
    <div class=lastresult id={}{}></div>

    </div>
</div>\n\n'''.format(this_id, res_count, this_id, res_count+1)

    return retval


# convert various variable types into pretty indented HTML output
def html_result_item(item, label, indent='                '):
    my_type = type(item).__name__
    value = ''
    if my_type in ('unicode', 'str', 'float', 'int', 'long', 'complex'):
        value = ascii(unicode(item))
    elif my_type in ('dict'):
        for subitem in sorted(item.keys()):
            value += html_result_item(item[subitem], subitem, indent + '    ')
    elif my_type in ('list', 'tuple', 'set', 'frozenset'):
        for idx, subitem in enumerate(item, start=1):
            value += html_result_item(subitem, idx, indent + '    ')
    else:
        value = "[unknown type {}]".format(my_type)
    if value == '':
        return ''
    return indent + "<div class='hang compact'><b>{}:</b> {} </div>\n".format(label, value)


# generate proper diff-like layout based on SequenceMatcher results
def html_alignAllDivs(s):
    retval = ""

    for tag, i1, i2, j1, j2 in s.get_opcodes():
        retval += "// %7s a[%d:%d] b[%d:%d]\n" % (tag, i1, i2, j1, j2)

    last_delta = 0
    state = 'start'
    for tag, i1, i2, j1, j2 in s.get_opcodes():
        if (tag == 'equal'):
            for i, j in zip(range(i1, i2), range(j1, j2)):
                retval += "\talignDivs(\"base{}\", \"delta{}\"); // equal\n".format(i+1, j+1)
                last_delta = i
            state = 'e'
        elif (tag == 'replace'):
            last_delta += i2 - i1
            if state == 'start':
                last_delta -= 1
            for j in range(j1, j2):
                retval += "\talignDivs(\"base{}\", \"delta{}\"); // replace\n".format(last_delta+2,
                                                                                      j+1)
                state = 'r'
        else:
            state = 'other'
    return retval


# create the final HTML bits for the diff page
def html_foot():
    return '''\

<script>
window.addEventListener("resize", alignAllDivs);
</script>

</body>
'''


# create the initial HTML bits for the diff page
def html_head(s):
    return '''\
<style>
.result {border:1px solid black; padding:3px; margin-top:16px}
.baseline, .delta {border:1px solid lightgrey; padding:2%; width:45%;}
.baseline {float:left; clear:left}
.delta {float:right; clear:right}
.indent {padding-left:2em}
.hang {padding-left: 1em ; text-indent: -1em}
.searchmatch {color:#00c; font-weight:bold}
.diff {background-color:#ffc}
.ranksame, .rankdown, .rankup, .ranklost, .ranknew {padding-left:0.25em;
    padding-right:0.25em; cursor: pointer;}
.ranksame {border:1px solid grey}
.rankdown {border:1px solid red; background-color:#fee}
.rankup {border:1px solid green; background-color:#efe}
.ranklost {border:1px solid red; background-color:#f00}
.ranknew {border:1px solid green; background-color:#0f0}
.compare {display:none; position:fixed; top: 10px; left:1.5%;
    width:90%; background-color:#fff; padding:3%; border:5px solid blue;
    overflow:scroll; max-height:65%}
.compclose {position:absolute; top:0; right:0; padding:0.15em;
    margin:2px; border:1px solid grey; cursor:pointer;
    font-family:sans-serif; color:grey; font-size:75%;}
.query {font-size:150%; margin-bottom:0.5em; margin-top:0.5em}
</style>

<script>
function comp (base, delta, clickfrom) {
    if (base > 0) {
        document.getElementById('basecomp').innerHTML =
            document.getElementById("base"+base).innerHTML;
        }
    else {
        document.getElementById('basecomp').innerHTML = "Not in baseline results."
        }
    if (delta > 0) {
        document.getElementById('deltacomp').innerHTML =
            document.getElementById("delta"+delta).innerHTML;
        }
    else {
        document.getElementById('deltacomp').innerHTML = "Not in delta results."
        }
    document.getElementById('comp').style.display = "inline";
    document.getElementById('upperpad').style.height =
        document.getElementById('comp').offsetHeight + 10 + "px";

    var top = document.getElementById(clickfrom).offsetTop;
    window.scrollTo(0, top - document.getElementById('comp').offsetHeight - 20);

    }

function closecomp() {
    document.getElementById('comp').style.display = "none";
    document.getElementById('upperpad').style.height = 0;
    }

function alignDivs(base, delta) {
    var bdiv = document.getElementById(base);
    var btop = bdiv.offsetTop;

    var ddiv = document.getElementById(delta);
    var dtop = ddiv.offsetTop;

    var margin = 0
    if (btop > dtop) {
        if (ddiv.style.marginTop) {
            margin = parseInt(ddiv.style.marginTop) - 16
            }
        margin += btop-dtop + 16;
        ddiv.style.marginTop = margin
        }
    else{
        if (bdiv.style.marginTop) {
            margin = parseInt(bdiv.style.marginTop) - 16
            }
        margin += dtop-btop + 16;
        bdiv.style.marginTop = margin
        }
    }

function alignAllDivs() {

    var els = document.getElementsByClassName("result");
    [].forEach.call(els, function (el) {el.style.marginTop = 16});

''' + \
        html_alignAllDivs(s) + '''
    }

</script>

<body onload="alignAllDivs()">

<div class=compare id=comp>
    <div class=compclose onclick="closecomp()">X</div>
    <div class=baseline>
        <b>BASELINE</b><br>
        <div class=compcomp id=basecomp>
        &nbsp;
        </div>
    </div>
    <div class=delta>
        <b>DELTA</b><br>
        <div class=compcomp id=deltacomp>
        &nbsp;
        </div>
    </div>
</div>

<div id=upperpad>
</div>

'''


def main():
    parser = argparse.ArgumentParser(description='line-by-line diff of JSON blobs',
                                     prog=sys.argv[0])
    parser.add_argument('file', nargs=2, help='files to diff')
    parser.add_argument('-d', '--dir', dest='dir', default='./diffs/',
                        help='output directory, default is ./diffs/')
    parser.add_argument("-t", "--bytitle", dest="bytitle", action='store_true', default=False,
                        help="use title rather than docId to match results")
    parser.add_argument("-w", "--baseWiki", dest="bwiki", default='',
                        help="URL for baseline wiki")
    parser.add_argument("-W", "--deltaWiki", dest="dwiki", default='',
                        help="URL for delta wiki")
    parser.add_argument("-e", "--baseExplain", dest="bexplain", default='',
                        help="explain URL for baseline wiki")
    parser.add_argument("-E", "--deltaExplain", dest="dexplain", default='',
                        help="explain URL for delta wiki")
    args = parser.parse_args()

    key = 'docId'
    if (args.bytitle):
        key = 'title'

    (file1, file2) = args.file
    target_dir = args.dir + '/'

    diff_count = 0

    if not os.path.exists(target_dir):
        os.makedirs(os.path.dirname(target_dir))

    with open(file1) as a, open(file2) as b:
        for tuple in izip_longest(a, b, fillvalue='{}'):
            (aline, bline) = tuple
            aline = aline.strip(' \t\n')
            bline = bline.strip(' \t\n')
            if aline == '':
                aline = '{}'
            if bline == '':
                bline = '{}'
            diff_count += 1
            diff_file = open(target_dir + 'diff' + repr(diff_count) + '.html', 'w')

            aresults = json.loads(aline)
            bresults = json.loads(bline)

            # munge lucene explanation
            munge_explanation(aresults)
            munge_explanation(bresults)

            apageids = extract_ids(aresults, key)
            bpageids = extract_ids(bresults, key)

            s = difflib.SequenceMatcher(None, apageids, bpageids)

            amap, bmap = make_map(apageids, bpageids)

            add_diffs(aresults, bresults, key)

            diff_file.writelines(html_head(s))
            diff_file.writelines(html_results(aresults, amap, file1, key, wiki_url=args.bwiki,
                                              explain_url=args.bexplain, baseline=True))
            diff_file.writelines(html_results(bresults, bmap, file2, key, wiki_url=args.dwiki,
                                              explain_url=args.dexplain, baseline=False))
            diff_file.writelines(html_foot())

            diff_file.close()


if __name__ == "__main__":
    main()
