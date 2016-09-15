#!/usr/bin/env python

# Augment a cirrus dump with data stored in a csv file.
# The augmented is loaded into memory for simplicity reasons and thus
# is only suited for short string or numeric values.
# Example augmenting with defaultsort and wp10:
#
# DUMP=https://dumps.wikimedia.org/other/cirrussearch/current/enwiki-20160829-cirrussearch-content.json.gz
# DEFAULTSORT=/plat/wp_dump/enwiki_defaultsort.csv.gz
# WP10=/plat/wp_dump/wp10-scores-enwiki-20160820.tsv.bz2
# ELASTIC=relforge1001.eqiad.wmnet:9200/enwikisourceprod_content/_bulk
# wget -qO- $DUMP | zcat |\
#   ./augmentdump.py --csv $DEFAULTSORT --id 0 --data 1 --newprop defaultsort |\
#   ./augmentdump.py --csv $WP10 --delim "        " --id page_id --data weighted_sum \
#                    --newprop wp10 --datatype float |\
#   split -l 100 --filter 'curl -s -XPOST $ELASTIC --data-binary "@-" | jq .errors
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
import csv
import json
import sys
import gzip
import bz2


def main():
    parser = argparse.ArgumentParser(description='augment wikimedia elasticsearch dumps',
                                     prog=sys.argv[0])
    parser.add_argument('--csv', required=True,
                        help='csv file with new data')
    parser.add_argument('--delim', default=",",
                        help='csv delimiter, defaults to ,')
    parser.add_argument('--quotechar', default='"',
                        help='csv quote char, defaults to "')
    parser.add_argument('--id', required=True,
                        help='id column name or index in the csv')
    parser.add_argument('--data', required=True,
                        help='data column or index')
    parser.add_argument('--newprop', required=True,
                        help='name of the new property')
    parser.add_argument('--datatype', default="string",
                        help='data type, defaults to (string)')
    args = parser.parse_args()

    data = read_csv_file(args.csv, args.delim, args.quotechar, args.id, args.data,
                         get_convertion_method(args.datatype))
    read_dump(sys.stdin, sys.stdout, data, args.newprop)


def get_convertion_method(datatype):
    if datatype == 'string':
        return str
    elif datatype == 'int':
        return int
    elif datatype == 'float':
        return float
    raise ValueError("Unknown datatype %s" % (datatype))


def read_csv_file(csvfilename, delim, quotechar, idcol, valuecol, datatype):
    csvfile = None
    if csvfilename.endswith('.gz'):
        csvfile = gzip.open(csvfilename, 'rb')
    elif csvfilename.endswith('.bz2'):
        csvfile = bz2.BZ2File(csvfilename, 'rb')
    else:
        csvfile = open(csvfilename, 'rb')
    return read_csv(csvfile, delim, quotechar, idcol, valuecol, datatype)


def read_csv(csvfile, delim, quotechar, idcol, valuecol, datatype):
    data = {}
    csvr = csv.reader(csvfile, delimiter=delim, quotechar=quotechar)
    ididx = 0
    valueidx = 0
    if idcol.isdigit() and valuecol.isdigit():
        ididx = int(idcol)
        valueidx = int(valuecol)
    else:
        headers = csvr.next()
        try:
            ididx = headers.index(idcol)
            valueidx = headers.index(valuecol)
        except ValueError:
            raise ValueError('Cannot find column %s or %s'
                             % (idcol, valuecol))

    for row in csvr:
        if len(row) <= max(ididx, valueidx):
            continue
        val = datatype(row[valueidx])
        rowId = row[ididx]
        if not rowId.isdigit():
            continue
        data[int(rowId)] = val
    return data


def read_dump(inputf, outputf, data, fieldname):
    l = 0
    pageId = -1
    for line in inputf:
        l += 1
        page = {}
        if l % 2 == 1:
            outputf.write(line)
            page = json.loads(line)
            pageId = -1
            if not page['index']['_id'].isdigit():
                continue
            if page['index']['_type'] != 'page':
                continue
            pageId = int(page['index']['_id'])
            continue
        if pageId >= 0 and pageId in data:
            page = json.loads(line)
            page[fieldname] = data[pageId]
            outputf.write(json.dumps(page) + '\n')
        else:
            outputf.write(line)

if __name__ == "__main__":
    main()
