       ___      __                             ____                 
      / _ \___ / /__ _  _____ ____  _______   / __/__  _______ ____ 
     / , _/ -_) / -_) |/ / _ `/ _ \/ __/ -_) / _// _ \/ __/ _ `/ -_) *
    /_/|_|\__/_/\__/|___/\_,_/_//_/\__/\__/ /_/  \___/_/  \_, /\__/ 
                                                         /___/

The primary purpose of the Relevance Lab is to allow us<sup>†</sup> to experiment with proposed modifications to our search process and gauge their effectiveness<sup>‡</sup> and impact<sup>§</sup> before releasing them into production, and even before doing any kind of user acceptance or A/B testing. Also, testing in the relevance lab gives an additional benefit over A/B tests (esp. in the case of very targeted changes): with A/B tests we aren't necessarily able to test the behavior of the *same query* with two different configurations.

<small>
\* Also known as RelForge to save a few keystrokes

† Appropriate values of "us" include the Discovery team, other WMF teams, and potentially the wider community of Wiki users and developers.

‡ "Does it do anything good?"

§ "How many searches does it affect?"
</small>

## Prerequisites

* Python: There's nothing too fancy here, and it works with Python 2.7, though a few packages are required:
 * The package `jsonpath-rw` is required by the main Rel Lab.
 * The package `termcolor` is required by the Cirrus Query Debugger.
 * If you don't have one of these packages, you can get it with `pip install <package-name>` (`sudo` may be required to install packages).
* SSH access to the host you intend to connect to.

## Invocation

The main Rel Lab process is `relevancyRunner.py`, which takes a `.ini` config file (see below):

	 relevancyRunner.py -c relevance.ini

### Processes

`relevancyRunner.py` parses the `.ini` file (see below), manages configuration, runs the queries against the Elasticsearch cluster and outputs the results, and then delegates diffing the results to the `jsonDiffTool` specified in the `.ini` file, and delegated the final report to the `metricTool` specified in the `.ini` file. It also archives the original queries and configuration (`.ini` and JSON `config` files) with the Rel Lab run output.

The `jsonDiffTool` is implemented as `jsondiff.py`, "an almost smart enough JSON diff tool". It's actually not that smart: it munges the search results JSON a bit, pretty-prints it, and then uses Python's HtmlDiff to make reasonably pretty output.

The `metricTool` is implemented as `relcomp.py`, which generates an HTML report comparing two relevance lab query runs. A number of metrics are defined, including zero results rate and a generic top-N diffs (sorted or not). Adding and configuring these metrics can be done in `main`, in the array `myMetrics`. Examples of queries that change from one run to the next for each metric are provided, with links into the diffs created by `jsondiff.py`.

Running the queries is typically the most time-consuming part of the process. If you ask for a very large number of results for each query (≫100), the diff step can be very slow. The report processing is generally very quick.

### Configuration

The Rel Lab is configured by way of an .ini file. A sample, `relevance.ini`, is provided. Global settings are provided in `[settings]`, and config for the two test runs are in `[test1]` and `[test2]`.

Additional command line arguments can be added to `searchCommand` to affect the way the queries are run (such as what wiki to run against, changing the number of results returned, and including detailed scoring information.

The number of examples provided by `jsondiff.py` is configurable in the `metricTool` command line.

See `relevance.ini` for more details on the command line arguments.

Each `[test#]` contains the `name` of the query set, and the file containing the `queries` (see Input below). Optionally, a JSON `config` file can be provided, which is passed to `runSearch.php` on the command line. These JSON configurations should be formatted as a single line.

The settings `queries`, `labHost`, `config`, and `searchCommand` can be specified globally under `[settings]` or per-run under `[test#]`. If both exist, `[test#]` will override `[settings]`.

#### Example JSON configs:

* `{"wgCirrusSearchFunctionRescoreWindowSize": 1, "wgCirrusSearchPhraseRescoreWindowSize" : 1}`
	* Set the Function Rescore Window Size to 1, and set the Phrase Rescore Window Size to 1.

* `{"wgCirrusSearchAllFields": {"use": false}}`
	* Set `$wgCirrusSearchAllFields['use']` to `false`.

* `{"wgCirrusSearchClusters":{"default": [{"host":"nobelium.eqiad.wmnet", "port":"80"}]}}`
	* Forward queries to the Nobelium cluster, which uses non-default port 80.

## Input

Queries should be formatted as Unicode text, with one query per line in the file specified under `queries`. Typically, the same queries file would be used by both runs, and the JSON `config` would be the only difference between the runs.

However, you could have different queries in two different files (e.g., one with quotes and one with the quotes removed). Queries are compared sequentially. That is, the first one in one file is compared to the first one in the other file, etc.

Query input should not contain tabs.


## Output

By default, Rel Lab run results are written out to the `relevance/` directory. This can be configured under `workDir` under `[settings]` in the `.ini` file.

A directory for each query set is created in the `relevance/queries/` directory. The directory is a "safe" version of the `name` given under `[test#]`. This directory contains the queries, the results, and a copy of the JSON config file used, if any, under the name `config.json`.

A directory for each comparison between `[test1]` and `[test2]` is created un the `relevance/comparisons/` directory. The name is a concatenation of the "safe" versions of the `name`s given to the query sets. The original `.ini` file is copied to `config.ini`, the final report is in `report.html`, and the diffs are stored in the `diffs/` directory, and are named in order as `diff#.html`.


## Other Tools

There are a few other bits and bobs included with the Rel Lab.

### Cirrus Query Debugger

The Cirrus Query Debugger (`cqd.py`) is a command line tool to display various debugging information for individual queries.

Run `cqd.py --help` for more details.

Note that `cqd.py` requires the `termcolor` package.

Helpful hint: If you want to pipe the output of `cqd.py` through `less`, you will want to use `less`'s `-R` option, which makes it understand and preserve the color output from `cqd.py`, and you might want to use `less`'s `-S` option, which doesn't wrap lines (arrow left and right to see long lines), depending on which part of the output you are using most.

### Index Metadata dump

`metastats.py` is a command line too to export various metadata from cirrus indices. It works by reading dumps on http://dumps.wikimedia.org/other/cirrussearch

Run `python metastats.py -w enwiki -t content -d 20160222 -u en.wikipedia.org > enwiki_meta_20160222.csv` to dump metadata for the enwiki content index.

See `misc/comp_suggest_score.R` for more details on what you can do with this data.

Columns:
* page: The title
* pageId: the page ID
* incomingLinks: number of incoming links
* externalLinks: number of external links
* bytes: text size in bytes
* headings: number of headings
* redirects: number of redirects
* outgoing: number of outgoing links
* pop_score: popularity score based on pageviews (pageview/total project pageviews)
* tmplBoost: product of all the template boosts

### Import Indices

Import Indices (`importindices.py`) downloads elasticsearch indices from wikimedia dumps and imports them to an elasticsearch cluster. It lives with the Rel Lab but is used on the Elasticsearch server you connect to, not your local machine.

### Miscellaneous

The `misc/` directory contains additional useful stuff:

* `fulltextQueriesSample.hql` contains a well-commented example HQL query to run against HIVE to extract a sample query set of fulltext queries.

### Gerrit Config

These files help Gerrit process patches correctly and are not directly part of the Rel Lab:

* `setup.cfg`
* `tox.ini`

## Options!

There are lots of options which can be passed as JSON in `config` files, or as options to the Cirrus Query Debugger (specifically, or generally using the custom `-c` option).

For more details on what the options do, see `CirrusSearch.php` in the [CirrusSearch extension](https://www.mediawiki.org/wiki/Extension:CirrusSearch).

For reference, here are some options and their names in JSON, Cirrus Query Debugger (CDQ), or the web API (API names are available using `-c` with CDQ).

* *Phrase Window*—Default: 512; JSON: `wgCirrusSearchPhraseRescoreWindowSize`; CDQ: `-pw`; API: `cirrusPhraseWindow`.

* *Function Window*—Default: 8196; JSON: `wgCirrusSearchFunctionRescoreWindowSize`; CDQ: `-fw`; API: `cirrusFunctionWindow`.

* *Rescore Profile*—Default: default; CDQ: `-rp`;
 * default: boostlinks and templates by default + optional criteria activated by special syntax (namespaces, prefer-recent, language, ...)
 * default_noboostlinks : default minus boostlinks
 * empty (will be deployed soon)

* *All Fields*—Default: true/yes; JSON: `wgCirrusSearchAllFields`; CDQ: `--allField`; API: `cirrusUseAllFields`.
 * JSON default: {"use": true}

* *Phrase Boost*—Default: 10; JSON: `wgCirrusSearchPhraseRescoreBoost`; API: `cirrusPhraseBoost`.

* *Phrase Slop*—Default: 1; JSON: `wgCirrusSearchPhraseSlop`; API: `cirrusPhraseSlop`.
 * API sets `boost` sub-value
 * JSON default: {"boost": 1, "precise": 0, "default": 0}

* *Boost Links*—Default: true/yes; JSON: `wgCirrusSearchBoostLinks`; API: `cirrusBoostLinks`.

* *Common Terms Query*—Default: false/no; JSON: `wgCirrusSearchUseCommonTermsQuery`; API: `cirrusUseCommonTermsQuery`.

* *Common Terms Query Profile*—Default: default; API: `cirrusCommonTermsQueryProfile`.
 * default: requires 4 terms in the query to be activated
 * strict: requires 6 terms in the query to be activated
 * aggressive_recall: requires 3 terms in the query to be activated

See also the "[more like](https://www.mediawiki.org/wiki/Help:CirrusSearch#morelike:)" options.
