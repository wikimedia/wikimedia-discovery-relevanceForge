       ___      __                             ____                 
      / _ \___ / /__ _  _____ ____  _______   / __/__  _______ ____ 
     / , _/ -_) / -_) |/ / _ `/ _ \/ __/ -_) / _// _ \/ __/ _ `/ -_) *
    /_/|_|\__/_/\__/|___/\_,_/_//_/\__/\__/ /_/  \___/_/  \_, /\__/ 
                                                         /___/

The primary purpose of the Relevance Forge is to allow us<sup>†</sup> to experiment with proposed modifications to our search process and gauge their effectiveness<sup>‡</sup> and impact<sup>§</sup> before releasing them into production, and even before doing any kind of user acceptance or A/B testing. Also, testing in the Relevance Forge gives an additional benefit over A/B tests (esp. in the case of very targeted changes): with A/B tests we aren't necessarily able to test the behavior of the *same query* with two different configurations.

<small>
\* Also known as RelForge to save a few keystrokes

† Appropriate values of "us" include the Discovery team, other WMF teams, and potentially the wider community of Wiki users and developers.

‡ "Does it do anything good?"

§ "How many searches does it affect?"
</small>

## Prerequisites

* Python: There's nothing too fancy here, and it works with Python 2.7, though a few packages are required:
 * The packages `jsonpath-rw, numpy` and `matplotlib` are required by the main Rel Forge.
 * The package `termcolor` is required by the Cirrus Query Debugger.
 * The package `scipy` is required by the Engine Score Optimizer
 * The package `matplotlib` is required by the Engine Score Optimizer
 * If you don't have one of these packages, you can get it with `pip install <package-name>` (`sudo` may be required to install packages).
* SSH access to the host you intend to connect to.

## Invocation

The main Rel Forge process is `relevancyRunner.py`, which takes a `.ini` config file (see below):

	 relevancyRunner.py -c relevance.ini

### Processes

`relevancyRunner.py` parses the `.ini` file (see below), manages configuration, runs the queries against the Elasticsearch cluster and outputs the results, and then delegates diffing the results to the `jsonDiffTool` specified in the `.ini` file, and delegated the final report to the `metricTool` specified in the `.ini` file. It also archives the original queries and configuration (`.ini` and JSON `config` files) with the Rel Forge run output.

The `jsonDiffTool` is implemented as `jsondiff.py`, "a somewhat smarter search result JSON diff tool". This version does an automatic alignment at the level of results pages (matching pagIds), munges the JSON results, and does a structural diff of the results. Structural elements that differ are marked as differing (yellow highlight), but no details are given on the diffs (i.e., only binary diffing of leaf nodes of the JSON structure). Changes in position from the baseline to delta are marked (e.g., ↑1 (light green) or ↓2 (light red)). New items are bright green and marked with "\*". Lost items are bright red and marked with "·". Clicking on an item number will display the item in the baseline and delta sife-by-side. Diffing results with explanations (i.e., using `--explain` in the `searchCommand`) is currently *much* slower, so don't enable that unless you are going to use it.

The `metricTool` is implemented as `relcomp.py`, which generates an HTML report comparing two Relevance Forge query runs. A number of metrics are defined, including zero results rate and a generic top-N diffs (sorted or not). Adding and configuring these metrics can be done in `main`, in the array `myMetrics`. Examples of queries that change from one run to the next for each metric are provided, with links into the diffs created by `jsondiff.py`.

Running the queries is typically the most time-consuming part of the process. If you ask for a very large number of results for each query (≫100), the diff step can be very slow. The report processing is generally very quick.

### Configuration

The Rel Forge is configured by way of an .ini file. A sample, `relevance.ini`, is provided. Global settings are provided in `[settings]`, and config for the two test runs are in `[test1]` and `[test2]`.

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

By default, Rel Forge run results are written out to the `relevance/` directory. This can be configured under `workDir` under `[settings]` in the `.ini` file.

A directory for each query set is created in the `relevance/queries/` directory. The directory is a "safe" version of the `name` given under `[test#]`. This directory contains the `queries`, the `results`, and a copy of the JSON config file used, if any, under the name `config.json`. If `results` contains non-JSON lines, these are filtered out to `results.isnotjson` for inspection.

A directory for each comparison between `[test1]` and `[test2]` is created un the `relevance/comparisons/` directory. The name is a concatenation of the "safe" versions of the `name`s given to the query sets. The original `.ini` file is copied to `config.ini`, the final report is in `report.html`, and the diffs are stored in the `diffs/` directory, and are named in order as `diff#.html`.

### Report Metrics

At the moment, report metrics are specified in code, in `relcomp.py`, in function `main()`, in the array `myMetrics`. Metrics are presented in the report in the order they are listed in `myMetrics`.

**`QueryCount`** gives a count of queries in each of corpus. It was also a convenient place to add statistics and charts (see below) for the number of TotalHits (which can be toggled with the `resultscount` parameter). `QueryCount` does not show any Diffs (see below).

**`ZeroResultsRate`** calculates the zero results rate for each corpus/config combo, and computes the difference between these rates between baseline and delta. `ZeroResultsRate` does show Diffs (see below).

**`TopNDiff`** looks at and reports the number of queries with differences in the top *n* results returned. *n* can be set to any integer (but shouldn't be larger than the number of results requested by the `searchCommand`, or the results won't be very meaningful. Differences can be considered `sorted` or not; e.g., if `sorted=True`, then swapping the top two results counts as a difference, if `sorted=False` then it does not. `TopNDiff` does show Diffs (see below).

`TopNDiff` also includes an option, `showstats`, to show statistics and charts (see below) for unsorted changes. The difference between two results sets is based on the number of items that need to be added, changed, or removed to change one set into another (similar to an unordered edit distance).

It makes sense to have multiple `TopNDiff` metrics—e.g., sorted and unsorted top 3, 5, 10, and 20—since these different stats tell different stories.

**Statistics and Charts:** When statistics and charts are to be displayed, the mean (μ), standard deviation (σ), and median are computed, both for the number/count of differences and the percent differences. These can be very different or nearly identical. For example, if every query got one more result in TotalHits, then that's +1 for every query, but for a query that originally had 1 result, it's +100%, but for a query that had 100 results, it's only +1%. For results that change from 0, (i.e., from 0 results to 5 results), the denominator used is 1 (so 0 to 5 is +500%).

Three charts are currently provided: number/count differences ("All queries, by number of changed ——"), number/count differences after dropping all 0 changes ("Changed queries, by number of changed ——"), and percent differences after dropping all 0 changes ("Changed queries, by percent of changed ——"). Since a change affecting 40% of queries is a pretty big change, the "0 changes" part of the graph often wildly dominates the rest. Dropping them effectively allows zooming in on the rest.

Charts are currently automatically generated by matplotlib, and sometimes have trouble with scale and outliers. Still, it's nice to get some idea of the distribution since the distributions of changes we see are often not normal, and thus μ, σ, and median are useful benchmarks, but don't tell the whole story.

The charts are presented in the report scaled fairly small, though they are presented in a standard order, and each is a link to the full-sized image.

**Diffs and `printnum`:** For metrics that report Diffs, the Diffs section of the report gives examples of queries that show the differences in question. Each metrics takes a `printnum` parameter that determines how many examples to show. By default, the parameter is set on the command line (default to 20) and shared across all metrics, though that can be overriden for any particular metric. If all the instances of a diff are to be shown (e.g., because `printnum` is 20 but there are only 5 examples), then they are shown in the order they appear in the corpora. If the only a sample is to be shown, then a random sample of size `printnum` is randomly selected and shown in a random order.


## Other Tools

There are a few other bits and bobs included with the Rel Forge.

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

Import Indices (`importindices.py`) downloads Elasticsearch indices from wikimedia dumps and imports them to an Elasticsearch cluster. It lives with the Rel Forge but is used on the Elasticsearch server you connect to, not your local machine.

### Piecewise Linear Model of an Empirical Distribution Function

`pwf_edf.py` generates a [piecewise linear model](https://en.wikipedia.org/wiki/Piecewise_linear_function) of an [empirical distribution function](https://en.wikipedia.org/wiki/Empirical_distribution_function) for the [cumulative probability distribution](https://en.wikipedia.org/wiki/Cumulative_distribution_function) of the data given to it.

This allows for a fairly simple empirical normalization of values to percentiles, effectively mapping the distribution of the values onto a straight line from 0 to 1. (Though when there are a very large number of occurrences of a given value—usually 0—that line is broken, alas.)

[RMSE](https://en.wikipedia.org/wiki/Root-mean-square_deviation) and maximum pointwise error are calculated and shown to aid in choosing the appropriate number of segments. More segments are more accurate, but also increase the complexity of calculating a value. In testing so far, 10 segments give a good fit, and 20 segments give a very good fit. Your mileage may vary depending on the smoothness and curviness of your distribution.

#### Stopping criteria

Refinement of the model continues until the stopping criteria is reached. Options include reaching the maximum number of segments allowed, or reaching sufficiently small errors. If both the target RMSE (`--error`) and maximum pointwise error (`--maxerror`) are reached, model refinement stops. By default, the required RMSE error is set to 0 (i.e., it will never be allowed to stop), and maximum pointwise error is set to 1 (i.e., it is always allowed to stop), so if only RMSE is important, it is the only parameter that needs to be supplied.

#### Runtime and sub-sampling

Finding a 20-segment approximation on a set of approximately ~5M data points (number of incoming links for pages in enwiki) takes under 4 minutes on a 2.2GHz laptop with 8G of memory. However, a random one-in-100 sub-sample (50K data points), takes under 3 seconds and generates a very similar model. Increasing the number of segments does not increase running time linearly, since only local changes need to be re-computed for each additional and usually smaller segment.

#### Input and output

Input is a list of numerical values, one per line, in a text file.

Output is... interesting?

Output can be formatted for one or more of the following:

* **[Desmos](https://www.desmos.com/)**—an excellent graphing calculator: output includes a table defining the endpoints of the line segments, which can be pasted directly into Desmos; a [signum](https://en.wikipedia.org/wiki/Sign_function)-based single function (see below) in LaTeX that can be pasted into Desmos; and separate specifications in LaTeX for each piece of the piecewise function, which can be pasted into Desmos (one at a time—which is annoying). These should all give the same resulting graph (with the exception of the table, which does not include points outside the [0-1] range.

* **Python:** Output includes a generic function that takes a point and a data structure holding the segment specification, plus the segment specification (useful if you have multiple EDFs), and a custom function that hard-codes the EDF into a giant switch statment.

* **Signum:** The Elasticsearch Scripting Module allows mathematical functions, but not conditionals. We can create a piecewise linear function using [`signum`](https://en.wikipedia.org/wiki/Sign_function). It's ugly, but we can use signum functions to limit put linear pieces to only by non-zero within the desired range. Then we add all the pieces together to get the final function. Outputs include a human readable format (the first clause handles values below the EDF minimum, the last clause handles values above the EDF maximum, and the middle does the linear interpolations)—which should be readily converted to the programming language of your choice; and a LaTeX format for use in Desmos. If both Desmos and Signum output are given, the LaTeX/Desmos version of the signum formula only occurs under the Desmos output.

Manual simplification and optimization: it may be worth doing manual simplification on the various outputs, especially those to be used in code. No effort has been made to simplify the math (e.g., complicated expressions multiplied by 0 may occur), or optimize the order of operations (e.g., the custom functions may be faster in general if calculated from high to low instead of low to high—you should do whatever you have more of first).

Out of bounds values: values outside the original distribution (i.e., below the smallest or above the largest value seen) are capped to the extreme values (0 and 1 respectively for the EDF).

Segment specification: The segment specification is an array of tuples, `[x, y, slope]`. `(x,y)` is the end of one line segment and the beginning of the next (except for the first and last tuple, naturally), and `slope` is the slope of the line segment from the previous endpoint (used in the generic and custom functions to save on re-computing (y[i]-y[i-1])/(x[i]-x[i-1]) for every single evaluation). The first point is given a `slope` of 0, though it isn't used.

### Engine Scoring Optimizer

The Engine Scoring Optimizer ( engineScore.py ) generates a single number representing the score of the engine for the query set. It can combine this calculation with scipy brute force optimization to explore a multi-dimensional space of numeric config values to attempt to find the best values. This works similar to the main relevancy runner, which is reused here for running the queries.

The Engine Scoring process takes an `.ini` file similar to the main relevancy runner:

    engineScore.py -c engineScore.ini

### Miscellaneous

The `misc/` directory contains additional useful stuff:

* `fulltextQueriesSample.hql` contains a well-commented example HQL query to run against HIVE to extract a sample query set of fulltext queries.

### Gerrit Config

These files help Gerrit process patches correctly and are not directly part of the Rel Forge:

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
