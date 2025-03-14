# Trey's Language Analyzer Analysis Tools

March 2025

These are the tools I use to do analysis of search engine language analyzers and custom analysis
chains. Most of
[my analysis write ups](https://www.mediawiki.org/wiki/User:TJones_%28WMF%29/Notes#Search_Analysis_Chain_Analysis)
are available on MediaWiki.org. The older ones, naturally, used less complex versions of this code—I
update it whenever something weird happens!

<a name="TOC"></a>
## Table of Contents
1. [What's Here?](#WhatsHere)
1. [Running `analyze_counts.pl`](#Runninganalyzecountspl)
    1. [Default Usage](#DefaultUsage)
    1. [Using an External Stemmer](#UsinganExternalStemmer)
1. [Running `compare_counts.pl`](#Runningcomparecountspl)
    1. [A Few Useful Notes](#AFewUsefulNotes)
        1. [On Types and Tokens](#OnTypesandTokens)
        1. [RTL and You](#RTLandYou)
        1. [Vertical Mongolian](#VerticalMongolian)
        1. [Token Categories: Latin & Cyrillic & Greek, Oh My!](#TokenCategoriesLatCyrGrk)
    1. [Comparison Analysis](#ComparisonAnalysis)
        1. [Report Details](#ReportDetails_1)
        1. [Folding & Languages](#FoldingLanguages_1)
            1. [Stem Length](#StemLength)
            1. [Terseness](#Terseness)
        1. [Things to Investigate](#ThingstoInvestigate_1)
    1. [Self Analysis](#SelfAnalysis)
        1. [Report Details](#ReportDetails_2)
        1. [Singletons](#Singletons)
        1. [Folding & Languages](#FoldingLanguages_2)
        1. [Samples for Speaker Review](#SamplesforSpeakerReview)
        1. [Explore (Automatic Prefix and Suffix Detection)](#ExploreAutomaticPrefixandSuffixDetection)
        1. [Things to Investigate](#ThingstoInvestigate_2)
    1. [Hidden Params](#HiddenParams)
1. [Analysis Example: English](#AnalysisExampleEnglish)
    1. [My Setup](#MySetup)
    1. [Generate Count Files for English With and Without Folding](#GenerateCountFilesforEnglishWithandWithoutFolding)
        1. [Re-Configure MediaWiki/Search for English *Without* Folding Enabled](#ReConfigureMediaWikiSearchforEnglishWithoutFoldingEnabled)
        1. [Generate the "Before"/Unfolded Counts File](#GeneratetheBeforeUnfoldedCountsFile)
        1. [Re-Configure MediaWiki/Search for English *With* Folding Enabled](#ReConfigureMediaWikiSearchforEnglishWithFoldingEnabled)
        1. [Generate the "After"/Folded Counts File](#GeneratetheAfterFoldedCountsFile)
    1. [Comparison Analysis of the Unfolded and Folded Count Files](#ComparisonAnalysisoftheUnfoldedandFoldedCountFiles)
        1. [Baseline Analysis](#BaselineAnalysis)
        1. [Simple Folded Analysis](#SimpleFoldedAnalysis)
    1. [Folded English Self Analysis](#FoldedEnglishSelfAnalysis)
    1. [Highlights from Other Analyses](#HighlightsfromOtherAnalyses)
1. [Stuff Yet To Do](#StuffYetToDo)
1. [Disclaimer](#Disclaimer)


<a name="WhatsHere"></a>
## What's Here? <small><small>[ [TOC](#TOC) ]</small></small>

Let's see what we've got:

* `analyze_counts.pl`: This is a program to run sample text against a language analyzer. It asks the
  search engine (OpenSearch or Elasticsearch) to analyze the text, maps tokens in the output back to
  strings in the input, and keeps count of how often each mapping occurs. It can also output tokens
  in the middle of the process, allow you to run an external stemmer on them, read them back in, and
  continue counting from there.
* `compare_counts.pl`: This is a much more complex program that does the real analysis of the
  language analyzer. It can perform either a "Self Analysis" on one counts file, or a
  "Comparison Analysis" between two counts files. See more below.
* `samples/data/`: This directory contains 1MB samples of text from articles from various
  Wikipedias. The corpora have had markup removed, and lines have been deduped.
* `samples/output/`: This directory contains output from the English examples below and a Polish
  example, so you can check them out without having to run everything yourself.

<a name="Runninganalyzecountspl"></a>
## Running `analyze_counts.pl`  <small><small>[ [TOC](#TOC) ]</small></small>

Here's the usage for reference:

    usage: ./analyze_counts.pl  [-t <tag>] [-d <dir>]
        [-h <host>] [-p <port>] [-i <index>] [-a <analyzer>]
        [-1] <input_file>.txt | -2 <input_counts>.txt <input_stemmed>.txt

        -t <tag>   tag added to the names of output files (default: baseline)
                     e.g., <input_file>.counts.<tag>.txt
        -d <dir>   directory output files should be written to
                     (default: same as <input_file>.txt or <input_stemmed>.txt)

        -h <host>  specify host for analysis (default: localhost)
        -p <port>  specify port for analysis (default: 9200)
        -i <index> specify index for analysis (default: my_wiki_content)
        -a <analyzer>
                   specify analyzer for analysis (default: text)

          Analyzer information is used for normal processing, or when creating
          output for an external stemmer (-1), but not when using input from an
          external stemmer (-2).

        Create a one-token-per-line output for an external stemmer
        -1         instead of normal counts output file, create two files:
                   - <input_file>.tok-count.<tag>.txt, with original tokens
                        and counts
                   - <input_file>.tok-unstemmed.<tag>.txt, with analyzed
                        tokens to be stemmed

                   The tok-unstemmed file should be stemmed by the external
                     stemmer, returning new tokens on matching lines.

        Use one-token-per-line input from an external stemmer
        -2 <input_counts>.txt <input_stemmed>.txt
                   instead of the normal input text, the original tokens and
                     counts are read from <input_counts>.txt, and the stemmed
                     tokens are read from <input_stemmed>.txt. The normal
                     counts output file is generated as output.

        -1 and -2 cannot be used at the same time.

<a name="DefaultUsage"></a>
### Default Usage <small>[ [TOC](#TOC) ]</small>

(i.e., not using `-1` or `-2`)

* The input file is just a UTF-8–encoded text file with the text to be analyzed.
  * It is not strictly necessary, but it seems helpful to remove markup unless you are testing
    your analyzer's ability to handle markup.
  * I like to deduplicate lines to decrease the apparent importance of domain-specific patterns
    when I'm looking for general language behavior. For example, in Wikipedia, exact paragraphs
    don't repeat often, but headings like "See Also" and "References" certainly do. Deduping
    helps keep the counts for "see", "also", and "references" at more typical levels for
    general text.
  * It is more efficient for `analyze_counts.pl` to batch up lines of text and send them to
    the search engine together. Up to 30,000 characters can be grouped together (over 50K seems
    to cause problems).
    * As of Elasticsearch 7, there is a default limit for API calls to `_analyze` to return no
      more than 10,000 tokens in one call. I've only run into the limit once, when analyzing
      text from Hebrew Wikipedia; Hebrew words are often shorter (so more fit in our 30K
      character limit) and our configuration for Hebrew wikis generates more than one token per
      word on average. Anyway, the error looks like this:

      > The number of tokens produced by calling \_analyze has exceeded the allowed maximum of
      > [10000]. This limit can be set by changing the [index.analyze.max\_token\_count] index
      > level setting.

      If you are in a dev environment (e.g., using MediaWiki Docker) where you can do whatever
      you want without risking putting too much strain on your search server(s), you can
      pre-emptively configure the limit to be arbitrarily high—say, 100K—with this command:

        ```
        curl -X PUT "localhost:9200/my_wiki_content/_settings?pretty" \
         -H 'Content-Type: application/json' \
         -d'{ "index" : { "analyze" : { "max_token_count" : 100000 }}}'
        ```

      (I have this command in the script I use for reindexing locally, so it gets run every
      time I change or update the analysis chain I'm using. I also haven't specifically checked
      if this limit is still an issue in OpenSearch 1.)

* The output file, which I call a "counts file", is pretty self-explanatory, but very long, so
  note that there are two sections: *original tokens mapped to final tokens* and *final tokens
  mapped to original tokens.*
  * The output file name will be `<input_file>.counts.<tag>.txt`. If no `<tag>` is specified with
    `-t`, then `baseline` is used.
  * By default, the counts file will be written to the same directory as the input file. If you'd
    like it to written to a different directory, use `-d <dir>`
  * The output is optimized for human readability, so there's *lots* of extra whitespace.
  * Obviously, if you had another source of pre- and post-analysis tokens, you could readily
    reformat them into the format output by `analyze_counts.pl` and then use
    `compare_counts.pl` to analyze them. (See also [Using an External
    Stemmer](#UsinganExternalStemmer) below.)
* The default host:port, index, analyzer combo is `localhost:9200`, `my_wiki_content`, and
  `text`, which are the defaults used in Mediawiki Docker, our current preferred dev
  environment. You can override any or all of these with `-h`, `-p`, `-i`, and `-a`.
* While the program is running, dots and numbers are output to STDERR as a progress indicator.
  Each dot represents 1000 lines of input and the numbers are running totals of lines of input
  processed. On the 1MB sample files, this isn't really necessary, but when processing bigger
  corpora, I like it.
* The program does some hocus-pocus with 32-bit CJK characters, emoji, and other characters that
  use [high and low
  surrogates](https://en.wikipedia.org/wiki/Universal_Character_Set_characters#Surrogates),
  because these have caused problems with character counts with various tokenizers I've used.
  Search internally counts such characters as two characters, and this breaks the
  offsets into the original string. So, the program adds `^A` ([ASCII code
  1](https://en.wikipedia.org/wiki/C0_and_C1_control_codes#SOH)) after such characters in the
  original string so the offsets are correct. The `^A` is stripped from tokens found in the
  original string. If your input contains `^A`, you are going to have a bad day. Overall, it
  seems to work, but that bit of code has not been severely stress-tested.

<a name="UsinganExternalStemmer"></a>
### Using an External Stemmer  <small>[ [TOC](#TOC) ]</small>

As I ran out of search analyzers to test, I started looking for stemmers (and potentially other
morphological analysis software, but mostly stemmers) that could be wrapped up into search
analyzers. I didn't want to necessarily have to do all the work to create a search analyzer (which
could also involve changing the programming language of the stemmer) just to be able to test it. So
I built out a way to outsource part of the analysis to an external, command line stemmer (or other
analysis software).

The stemmers I've played with have different input and output formats, but they all seem to be able
to handle taking one token per line and returning one token per line.

So, after configuring a search analyzer with some basic tokenization and maybe basic normalization—I
used the standard tokenizer and ICU Normalizer—you can use an external stemmer as follows.

* **Generate Stemmer Input File:** Use `-1` (for "one-token-per-line") to generate a
  one-token-per-line file that can be fed to the stemmer. It will also generate a corresponding
  file with counts for original tokens. (Because of normalization, even if it is just
  lowercasing, you can have multiple original tokens matching one token to be stemmed.) Given
  the command line `./analyze_counts.pl -1 input.txt` (using the default tag `baseline`),
  you'll get two output files:
  * `input.tok-count.baseline.txt`, which contains a tab-separated list of original tokens and
    counts for each normalized token in the other file. For example: `MUSIC 2 Music 3   music   1`.
  * `input.tok-unstemmed.baseline.txt`, which contains the corresponding normalized token, one
    per line. For example: `music`.
* **Stem Your Tokens:** Use your command-line stemmer or whatever other process to generate a
  stemmed version of the `tok-unstemmed` file. For example, if your stemmer has both a "light"
  and "aggressive" version you want to test, you might run these two commands:
  * `cl_stemmer -light < input.tok-unstemmed.baseline.txt > input.light-stem.txt`
  * `cl_stemmer -aggressive < input.tok-unstemmed.baseline.txt > input.aggressive-stem.txt`
* **Generate Counts Files from Stemmer Output Files:** Use `-2` (for "that which comes after 1")
  to generate a normal counts file based on the `tok-count` file and the output of the stemmer.
  So, if you had a counts file named `input.tok-counts.baseline.txt` you could generate counts
  file for your "light" stemmed filed above like this:
  * `./analyze_counts.pl -t light -2 input.tok-counts.baseline.txt input.light-stem.txt`, which
    would generate `input.light-stem.counts.light.txt`.

Yeah, the file names can get mildly ridiculous.

<a name="Runningcomparecountspl"></a>
## Running `compare_counts.pl`  <small><small>[ [TOC](#TOC) ]</small></small>

Here's the usage for reference:

    usage: ./compare_counts.pl -n <new_file> [-o <old_file>] [-d <dir>] [-l <lang,lang,...>]
        [-S <#>] [-x] [-1] [-f] [-s <#>] [-t <#>] > output.html

        -n <file>  "new" counts file
        -d <dir>   specify the dir for language data config; default: langdata/
        -l <lang>  specify one or more language configs to load.
                   See langdata/example.txt for config details
        -S <#>     generate groups of up to <#> samples for speaker review

        Analyzer Self Analysis (new file only)
        -x         explore: automated prefix and suffix detection
        -1         give singleton output, showing one-member stemming groups, too

        Analyzer Comparison Analysis (old vs new file)
        -o <file>  "old" counts file, baseline to compare "new" file against
        -f         apply basic folding when comparing old and new analyzer output
        -s <#>     minimum stem length for recognizing regular prefix and suffix alternations
        -t <#>     terse output:
                     1+ = skip new/old lists with the same words, but different counts
                     2+ = skip new/old lists with the same words, after folding

If you specify two counts files (`-n` & `-o`), then `compare_counts.pl` will run a **Comparison
Analysis.** If you only specify one counts file (`-n`), then you get a **Self Analysis.**

<a name="AFewUsefulNotes"></a>
### A Few Useful Notes  <small>[ [TOC](#TOC) ]</small>

<a name="OnTypesandTokens"></a>
#### On Types and Tokens  <small>[ [TOC](#TOC) ]</small>

A lot of the analysis looks at types and tokens, and it’s important to distinguish the two. Tokens
refer to individual words, counted each time they appear. Types count all instances of a word as one
thing. It's also useful to keep in mind the distinction between pre-analysis and post-analysis
types. Pre-analysis, we have the words (types) as they were split up by the tokenizer.
Post-analysis, words that have also been regularized (by stemming, lowercasing, folding, etc.) are
counted together as one type.

So, in the sentence *The brown dog jumped, the black dog jumps, and the grey dogs are jumping.*
there are fourteen tokens (more or less what you would probably think of as normal words).

Pre-analysis, there are twelve types: *The, brown, dog, jumped, the, black, jumps, and, grey, dogs,
are, jumping*—note that *The* and *the* are still distinct at this point, too!

With a plausible English analyzer, there might only be eight post-analysis types: *the, brown, dog,
jump, black, and, grey, be.* A different English analyzer, that drops stop words, might give five
post-analysis types: *brown, dog, jump, black, grey.*

<a name="RTLandYou"></a>
#### RTL and You  <small>[ [TOC](#TOC) ]</small>

When you analyze a big chunk of data from almost any Wikipedia, you get lots of words in other
languages. Some of those languages are RTL (right-to-left)—with Arabic and Hebrew being the most
common. Depending on how your operating system, editor, and browser are configured, you can get some
ugly results.

If you aren't familiar with RTL languages, when they are displayed you can get flipped arrows,
brackets, and braces, and sometimes in extra confusing ways like `]ℵℵℵ]`,\* where *ℵℵℵ* is anything
in Hebrew or Arabic. Reading right to left, that's an RTL opening bracket, *ℵℵℵ,* and an LTR closing
bracket—because sometimes computers are stupid that way.

<sup>* To make sure this displays <s>correctly</s> incorrectly, I had to cheat and use an LTR
version of Hebrew alef, which is used in
[mathematics](https://en.wikipedia.org/wiki/Aleph_number).</sup>

I've added some CSS to try to encourage chunks of RTL text to display correctly. But
[your mileage may vary](https://en.wiktionary.org/wiki/your_mileage_may_vary).

<a name="VerticalMongolian"></a>
#### Vertical Mongolian  <small>[ [TOC](#TOC) ]</small>

I've added some checks to recognize samples of
[Mongolian script](https://en.wikipedia.org/wiki/Mongolian_script), which is intended to be
written vertically, so that it renders correctly.

<a name="TokenCategoriesLatCyrGrk"></a>
#### Token Categories: <font color=#007700>Latin</font> & <font color=#ff0000>Cyrillic</font> & <font color=#0000ff>Greek</font>, Oh My!  <small>[ [TOC](#TOC) ]</small>

In both the Comparison Analysis and Self Analysis, certain samples of tokens are grouped into
"categories", which are based on character set, the formatting of numbers, and some
(semi-?)easily identified other types, like measurements, acronyms, probable IPA, etc. An
attempt is made to categorize mixed-script tokens according to the scripts they contain (as
*mixed-&lt;script&gt;-&lt;script&gt;-&lt;etc.&gt;*), with additional sub-categories for tokens
containing numbers and/or various separators—including colons, commas, dashes, dots, equals
signs, horizontal and vertical bars, hyphens, periods, semicolons, underscores, and plain old
regular spaces—or a mix of more than one separator. The *unknown* category is a catch-all for
everything else; I sometimes mine the *unknown* category for new categories.

In a Comparison Analysis, *Lost and Found Tokens* are sampled both Pre- and Post-Analysis (see
below) so you can see what's changing. In a Self Analysis, *all* tokens are sampled Pre- and
Post-Analysis, so you can get a sense of what you've got, and what the analysis chain is doing.

* Sub-categories are created for tokens with certain invisible, hard-to-detect, or "unexpected"
  characters—like
  [zero-width non-joiners](https://en.wikipedia.org/wiki/Zero-width_non-joiner) (zwnj),
  [zero-width joiners](https://en.wikipedia.org/wiki/Zero-width_joiner) (zwj),
  [word joiners](https://en.wikipedia.org/wiki/Word_joiner) (wj),
  [zero-width spaces](https://en.wikipedia.org/wiki/Zero-width_space) (zwsp),
  regular and zero-width [non-breaking spaces](https://en.wikipedia.org/wiki/Non-breaking_space)
  (nbsp),
  [narrow non-breaking spaces](https://en.wikipedia.org/wiki/Non-breaking_space#Narrow_non-breaking_space)
  (nnbsp),
  ideographic spaces, leading and trailing "plain" spaces,
  [invisible separators](https://en.wikipedia.org/wiki/Universal_Character_Set_characters#Mathematical_invisibles)
  (invis\_sep),
  [variation selectors](https://en.wikipedia.org/wiki/Variant_form_%28Unicode%29) (var),
  [bi-directional markers](https://en.wikipedia.org/wiki/Bi-directional_text#marks) (bidi),
  [soft-hyphens](https://en.wikipedia.org/wiki/Soft_hyphen) (shy), tabs (tab),
  or new lines (cr)—along with other "interesting" characters, including
  [combining characters](https://en.wikipedia.org/wiki/Combining_character) (combo),
  [modifier letters](https://en.wikipedia.org/wiki/Spacing_Modifier_Letters) (mod),
  and various punctuation not normally found in indexed tokens, like ampersands, apostrophes,
  at signs, dollar signs, double quotes, exclamation points, octothorpes, parentheses, percent
  signs, and plus signs, along with non-combining characters that are often accents—acute,
  grave, primes, and tildes—and various fullwidth, curly, or other variants of any of those.
  * Invisible characters (whitespace, soft hyphens, bidi marks, variation selectors, joiners
    and non-joiners) are replaced with light blue visible characters, with more detail
    available on hover. A general key is also provided for invisibles and script colors.
* Tokens in the *mixed, unknown, IPA-ish, Tonal Transcription,* and *name-like* categories, as
  well as those in the "Stemmed Tokens Generated per Input Token" and "Final Type Lengths"
  sections also have script colorization applied to (so far):
  <span style='color:#ff0000; font-weight:bold'>Cyrillic</span>,
  <span style='color:#0000ff; font-weight:bold'>Greek</span>,
  <span style='color:#007700; font-weight:bold'>Latin</span>;
  <span style='color:#996600; font-weight:bold'>Han</span>,
  <span style='color:#999900; font-weight:bold'>Hiragana</span>,
  <span style='color:#e68d2e; font-weight:bold'>Katakana</span>;
  <span style='color:#107896; font-weight:bold'>Bengali</span>,
  <span style='color:#cc00cc; font-weight:bold'>Devanagari</span>,
  <span style='color:#9400D3; font-weight:bold'>Thai</span>,
  and <span style='color:#808080; font-weight:bold'>Unicode</span>,
  with more detail available on hover. A general key is also provided for invisibles and script
  colors. Script colors make it easier to identify these character sets, particularly those
  with [homoglyphs](https://en.wikipedia.org/wiki/Homoglyph).
  * IPA characters are generally Latin, though certain characters—particularly θ, β, γ, and χ—are
    more likely to use
    [Greek versions](https://en.wikipedia.org/wiki/International_Phonetic_Alphabet#Typography_and_iconicity).
* Tokens in the "Unicode" category are \u-encoded strings (e.g.,
  \uD803\uDC18\uD803\uDC03\uD803\uDC15 for Old Turkic 𐰘𐰃𐰕); these also shown with their
  underlying script as a sub-category (e.g., "Unicode/Old Turkic"), and primarily by their
  decoded form, with the \u-encoded string in parentheses.
* If you have a really big category, only a randomly chosen sub-sample is shown. Currently, 100
  samples are shown for Lost/Found categories in a Comparison Analysis, and 25 samples are shown for
  most Self Analysis categories (100 for the *unknown* category).
* Up to 25 of the most frequent tokens in each category that occur more than 1000 times are
  re-listed with their counts on a separate line labeled "hi-freq tokens".
* A small statistical summary of type lengths (i.e., counting distinct words once each) is also
  given, including the range (e.g., 1–5), count (n), mean (µ), and standard deviation (σ),
  along with a small histogram of length information. Hovering over a column in the histogram
  gives additional information (length and frequency count).
  * Note that the histogram may skip empty columns at the beginning (indicated by ...), and it
    may be so long that it wraps around to the next line—or in extreme cases, several lines.

<a name="ComparisonAnalysis"></a>
### Comparison Analysis  <small>[ [TOC](#TOC) ]</small>

The purpose of a Comparison Analysis is to look at the impact of analysis changes in a
before-and-after style format. Small, relatively focused changes to an analysis chain—including
small to moderate changes to
[character filters](https://www.elastic.co/guide/en/elasticsearch/reference/current/analysis-charfilters.html),
[tokenizers](https://www.elastic.co/guide/en/elasticsearch/reference/current/analysis-tokenizers.html),
and
[token filters](https://www.elastic.co/guide/en/elasticsearch/reference/current/analysis-tokenfilters.html),
like enabling `word_break_helper`, ASCII-folding, or ICU-folding—are generally easier to
understand, but it can be used to look at changes from enabling stemmers, or swapping to
radically different tokenizers (e.g., bigram- vs word-based tokenization).

<a name="ReportDetails_1"></a>
#### Report Details  <small>[ [TOC](#TOC) ]</small>

Among the details reported are:

* The **number of tokens** found by the tokenizers. If this changes, then the tokenizer is
  breaking up your input text differently, or a filter is discarding tokens (like stop words).
* **"Pre"** and **"Post"** type and token stats. "Pre" and "Post" refer to pre-analysis and
  post-analysis. The language analyzer drops some tokens (usually stop words, affecting type
  and token counts) and munges others (affecting type counts). So, if the tokenizer finds *dog*
  and *dogs,* we have two types. After analysis, though, they could both become *dog,* so now
  we only have one type.
  * We also try to categorize the number of types and tokens that are unchanged by the analysis.
    Three big categories (which overlap) are *unchanged* (token in, token out: *dog*
    stays *dog*), *lc_unchanged* (only difference is case, so *DOGGO* becomes *doggo*), and *number*
    (strings of digits—not including commas or periods—tend to remain unchanged).
* **Empty Token Inputs:** This section includes a frequency-sorted list of pre-analysis tokens
  that generate empty (zero-length) post-analysis tokens. An example might be a lone combining
  character or variation selector that then gets normalized to nothing. If there are no empty
  input tokens, this section is omitted.
* **Collisions and Splits:** The original purpose of the distant progenitor of
  `compare_counts.pl` was to look for new collisions, that is, words that are grouped together
  that weren't before. For example, if we enable ASCII-folding, we would expect *resumé* and
  *resume* to both be indexed as *resume,* whereas before they would have been distinct. Splits
  are the opposite—words that used to be grouped together than no longer are.
  * We can currently only reliably detect collisions and splits that result from small to moderate
    changes to the analysis chain; in particular, if the new analyzer significantly changes most
    post-analysis forms, the Comparison Analysis won't be able to reliably detect collisions and
    splits. Thus, it may not make sense to look for collisions and splits when you go from the
    default language analyzer (which doesn't know anything about any language or its morphology and
    grammar, just tokens and characters) to a language-specific analyzer that does know about the
    morphology of the language, depending on how different the stemmed forms are. It also doesn't
    work well when the tokenizer changes dramatically, such as switching from the CJK tokenizer
    (which breaks up CJK characters into overlapping bigrams) to a language-specific tokenizer for
    Chinese or Japanese (which tries to find actual word boundaries). It can still be useful to run
    the Comparison Analysis in these cases, but the collisions and splits are often uselessly
    numerous.
  * Collisions and splits are reported primarily in terms of the number of post-analysis
    types/groups that had one or more merges or splits. Added or lost tokens and pre-analysis types,
    and the total types involved are also reported. Total tokens "involved" are not reported because
    token counts for a given type can change, and that's more complicated than it's worth. A
    "Narrative" section summarizes the stats in a way that's easy to copy into a report, because I
    used to do that a lot.
      * So, if a pre-analysis type with one token (i.e., a word that appeared exactly once) gets
        newly indexed into a group of nine other one-token types, we have 1 post-analysis type, and
        we have 10 pre-analysis types in a collision, with one token added. If a 10-token type
        merges with a 100-token type, that's 2 pre-analysis types and 1 post-analysis type in the
        collision, with 10 new tokens. This doesn't tell you whether changes are good or not, but
        does indicate the relative impact of the changes.
  * The split part of the report is only included if there are splits. Percentages are reported
    relative to the "old" token and type counts.
* **Token Count Increases and Decreases:** Individual post-analysis types can increase or
  decrease in frequency without adding or losing any pre-analysis types. It's rare, but it
  does happen, particularly with changes to tokenizers splitting on underscores, hyphens,
  periods, slashes, etc. The number of post-analysis types/groups and pre-analysis types
  affected are reported, along with the total number of tokens gained or lost. These parts of
  the report are only included if there are gains or losses. Percentages are reported
  relative to the "old" token and type counts.
* **Near Match Stats** are reported as type and token counts for new collisions. The categories
  are *folded* (the new type matches an old type after default and language-specific folding,
  de-spacing, and de-hyphenating the new type), *regulars* (the new type matches an old type
  after taking into account regular morphology, which is just removing regular prefixes and
  suffixes), and *folded_regulars* (the new type matches an old type after both folding and
  regular morphology). These collectively are the "obvious" collisions. For example, we aren't
  too surprised when *resume, resumé, resumes,* and *resumed* collide.
* **Lost and Found Tokens:** One sneaky fact is that the normalization of a token can change
  without causing a split or collision because it doesn't group with any other types. If
  *Foo123bar* was normalized as *foo123bar* before and *foobar* afterwards, we might
  never know because it was always alone in its own group. So, we report lost and found tokens.
  "Lost" tokens are those that were present in the old analysis but are not in the new analysis, and
  "found" tokens are the other way around.
  * Lost and found tokens are listed both pre-analysis—where changes are usually due to the
    tokenizer—and post-analysis—where additional changes are usually due to stemming or folding.
  * Lost and found tokens are grouped into "categories", which are mostly based on character set.
    See [Token Categories](#TokenCategoriesLatCyrGrk) above.
      * If you have a really big lost/found change, only 100 randomly chosen samples are shown for
        each category. This happens in particular when you enable a language analyzer and there
        wasn't one before. Many, many words are now stemmed, and their original unstemmed forms are
        "lost".
      * Tokens in each category that occur more than 1000 times are re-listed with their counts on a
        separate line labeled "hi-freq tokens".
  * Categories that exist only in the Lost *or* Found column are lightly highlighted in yellow for
    ease of identification, like this: *<span
    style='background-color:#ffffe8'>mixed-Cyrillic-Latin</span>.* Categories that exist in both the
    Lost *and* Found columns, but which have different numbers of types or tokens, have the types
    and token counts highlighted in the Found column, like this: <span
    style='background-color:#ffffe8'>36 types, 45 tokens</span>.
* After the Lost and Found Tokens, **Changed Groups** are listed, divided up into new collisions and
  token count increases (**Net Gains**) and new splits and token count decreases (**Net Losses**).
  If the changes are not all in one direction, they are shown as **Mixed.**
  * There is a link to "<font color=red>High Impact Changes 🅸</font>" at the top of each section of
    the **Changed Groups**. This links to the next group that added or removed 10+ types, and each
    group has another <font color=red>🅸</font>, which links to the next. The last high impact
    change (or if there are none, the initial link) takes you to the bottom of the section.
  * There is also link to "<font color=green>Mixed-Script Groups 🅼</font>" at the top of each
    section of the **Changed Groups**. This links to the next mixed-script group. Mixed-script
    groups can have either individual mixed-script tokens, or separate tokens in different scripts.
    Each mixed-script group has another <font color=green>🅼</font>, which links to the next. The
    last mixed-script group (or if there are none, the initial link) takes you to the bottom of the
    section.
  * Diffs between old and new groups are lightly highlighted in yellow for ease of identification,
    like this: <span style='background-color:#ffffe8'>[1 xyz]</span>
  * Individual high-frequency (1000+) tokens are bold and in blue, like this: <span
    style='color:blue'>**[1000 xyz]**</span>

<a name="FoldingLanguages_1"></a>
#### Folding & Languages  <small>[ [TOC](#TOC) ]</small>

For a Comparison Analysis, enabling folding (`-f`) applies the available folding to tokens for
computing Near Match Stats and detecting potential bad collisions. Default folding
(`./langdata/default.txt`) is normally available, and additional folding can be specified in a
language-specific config (e.g., `./langdata/russian.txt`).

So, with folding enabled, *léo* being merged with *Leo* is no longer a potential bad collision
because the difference is gone after default folding. Note that the folding specified in the default
config is intentionally incomplete as all of it has been manually added. If ICU folding or some
other change causes an unexpected collision I don't want to miss it because I was using the same or
a similar library for folding here.

Additional language configs can be supplied. Use `-d` to specify the directory and `-l` to specify a
comma-separated list of languages, though usually only one language is needed. (**NB:** "default" is
normally loaded, but it can be disabled by specifying "-default" with `-l`; see Serbian example
under **Folding across character sets** below.) To specify that `langdata/russian.txt` should be
loaded, use `-d langdata -l russian`. All language config files should end in `.txt`. Note that `-d
langdata` is the default, so if you don't move that directory, you should only need `-l`.

Additional folding, such as Cyrillic Ё/ё to Е/е, or stress accent to nothing can be specified in a
language config file.

Regular morphology<sup>†</sup> used in a Comparison Analysis is specified in `regular_suffixes` and
`regular_prefixes`. (See details under [Self Analysis](#SelfAnalysis) for info on the similar
`strip_prefixes` and `strip_suffixes`.) Regular affixes are specified in groups that can alternate
with each other, and can include the empty string (for affixes that can be removed). For a
simplified version of English, we might specify "ing", "ed", and "" (the empty string) as
alternates. So, if *starting* gets added to a group that already contains *started* or *start,* then
the collision is not considered as a potentially bad collision, because it is explained by the
regular morphology. Such collisions are not always correct—for example, *work/worker* would be a
good collision, while *heath/heather* is not—but they are not unexpected. Only one affix alternation
(i.e., one suffix or one prefix) is allowed per match.

<sup> † While a lot of [morphology](https://en.wikipedia.org/wiki/Morphology_%28linguistics%29) in
many languages is more complex than one simple suffix or prefix, they are much easier to handle than
[infixes](https://en.wikipedia.org/wiki/Infix),
[circumfixes](https://en.wikipedia.org/wiki/Circumfix),
[transfixes](https://en.wikipedia.org/wiki/Transfix),
[strong inflections](https://en.wikipedia.org/wiki/Strong_inflection),
[polysynthesis](https://en.wikipedia.org/wiki/Polysynthetic_language),
[noun incorporation](https://en.wikipedia.org/wiki/Incorporation_%28linguistics%29), and all the
other really cool stuff languages do.
</sup>

See `langdata/example.txt` for examples of how to format a language config file.

As noted, it is possible to specify multiple language configs in a comma-separated list, but it
probably doesn't make sense to do so if the configs are actually for different languages. One
common exception is for digits (`langdata/digits.txt`). Digits in various scripts can be
normalized (e.g., ١, ১, १, ፩, ೧, ១, ൧, ๑, ௧, and ೧ all being normalized to 1), and maintaining
one config to ignore all such changes is easier than replicating it everywhere. I've also used
multiple configs for conservative vs aggressive or computationally cheap vs expensive
morphology and folding in the same language.

<a name="StemLength"></a>
##### Stem Length  <small>[ [TOC](#TOC) ]</small>

The minimum stem length (`-s`, default value: 5) is the minimum length of the string left after
removing a prefix or suffix. So, even if *-able* and *-ation* were allowed to alternate, *stable*
and *station* would count as a potentially bad collision (i.e., one that a human should review)
because the apparent stem, *st,* is too short.

<a name="Terseness"></a>
##### Terseness  <small>[ [TOC](#TOC) ]</small>

Increasing the terseness further limits the groups shown under **Changed Groups.**

With terseness set to 1, groups with the same types, but different token counts are not shown.
Changes in counts are generally caused by changes in tokenization (a common source being word
breaking on underscores, hyphens, periods, and slashes), as no new tokens are being grouped
together, but more or fewer instances of the tokens are being found. With terseness set to 1, the
group below would **_not_** be shown as changed:

<table><tr>
    <td valign=top> xyz >> </td>
    <td>o: [3 XYZ][1 Xyz]<font color=blue><b>[3333 xyz]</b></font><br>
        n: [4 XYZ][1 Xyz]<font color=blue><b>[4444 xyz]</b></font></td>
</tr></table>

With terseness set to 2, groups with the same types after default + language-specific folding, and
possibly with different token counts, are not shown. These are the "expected" changes attributable
to commonly-seen folding. With terseness set to 2, the group below would **_not_** be shown as
changed:

<table><tr>
    <td valign=top> xyz >> </td>
    <td>o: [3 XYZ][1 Xyz][33 xyz]<br>
        n: [3 XYZ][1 Xyz][33 xyz]<span style='background-color:#ffffe8'>[1 xÿž]</span></td>
</tr></table>

<a name="ThingstoInvestigate_1"></a>
#### Things to Investigate  <small>[ [TOC](#TOC) ]</small>

* Look for unexpectedly large changes in the number of tokens found (total and
  pre-/post-analysis). Some changes—particularly due to changes in whether stop words are being
  dropped, and changes in whether underscores, hyphens, periods, and slashes are
  word-breakers—might be expected if you've changed analyzers or tokenizers. Folding changes,
  though, normally shouldn't change the number of total tokens. (Though word breaking on stress
  accents, for example, might!)
* New Collision/Split Stats should reflect a sensible impact. Enabling ASCII-folding in English
  should have minimal impact, since most English words don't have diacritics. For Vietnamese,
  the impact of diacritic folding could be huge! Going from the default analyzer to a
  language-specific analyzer could have a giant impact in a highly inflected language, since
  the stemmed form of most words is different from the original form.
* There's often a lot going on in the Lost and Found Tokens:
  * I like to run a sample of the lost tokens from each category through the analyzer directly on
    the command line to see what's happening to them to explain why they are lost. With
    folding, there are a handful of tokens in several different categories, because there are
    non-canonical forms of letters in several scripts that can get "regularized".
       * e.g., `curl -sk localhost:9200/my_wiki_content/_analyze?pretty -H 'Content-Type: application/json' -d '{"analyzer": "text", "text" : "xÿz" }'`
  * Stop words can be lost if you've enabled a language-specific analyzer where there was none
    before.
  * [IPA](https://en.wikipedia.org/wiki/International_Phonetic_Alphabet)—which is common in
    Wikipedias and Wiktionaries—tends to get murderized by lots of analyzers, which sometimes split
    on the more esoteric characters.
  * Rarely, something really drastic happens, like all tokens in "foreign" scripts are lost. That
    is [double-plus-ungood](https://en.wiktionary.org/wiki/double-plus-ungood).
  * The type length stats and histogram can point to some interesting surprises, like
    unexpected outliers (i.e., many more long or short types than you expect for a given
    category). You can also get a sense of changes from before to after. For example,
    regularizing Greek final sigma (ς) to regular sigma (σ) should have no effect on the stats.
* Changed Groups, Net Losses/Gains—I like to skim through these and then re-run with folding
  enabled. Review of all of these or a sizable random sample of these by a fluent speaker is often
  helpful.
  * Even if you want to review all the changes, enabling folding and looking at the residue can
    highlight different kinds of changes from the basic folded changes.
* I think it's sometimes helpful to take into account the "main" language you are working in when
  reviewing collisions. For example, English pretty much ignores accents. There are a few examples,
  like *resumé, fiancée,* and *Zöe,* where accents are relatively common or even important, but not
  many. So, when working on data from English Wikipedia, I don't really care that German words or
  Russian words are getting folded in a way that a German or Russian speaker wouldn't like. Lots of
  English speakers can't type the *ö* in German *quadratförmig,* so *quadratformig* should match—on
  English-language projects.
  * In general I expect and accept folding of characters that aren't part of the main language of
    the corpus being analyzed. In English—*fold them all!* In Swedish, folding *å, ä,* and *ö*
    is suspect—it might be acceptable, but probably not (it wasn't—see
    [T160562](https://phabricator.wikimedia.org/T160562))—but folding anything else is probably
    fine. On the other hand, the default German language analyzer folds common umlauts! I was
    originally very surprised! The general heuristic I've settled on is that diacritical characters
    that are part of a language's alphabet should not be folded, while others should. There are
    exceptions, of course (like Slovak!—see [T223787](https://phabricator.wikimedia.org/T223787)).

<a name="SelfAnalysis"></a>
### Self Analysis  <small>[ [TOC](#TOC) ]</small>

The original main purpose of a Self Analysis was to assess big changes to an analysis chain, such as
implementing a language analyzer where there was none before. However, it's become useful to also
get a sense of the content of a corpus, and the baseline behavior of an analysis chain.

<a name="ReportDetails_2"></a>
#### Report Details  <small>[ [TOC](#TOC) ]</small>

Among the details reported are:

* **Stemming Results:** Words (types) that are analyzed the same are grouped together in a
  table. The columns of the table are:
  * *stem:* the "stem" returned by the analyzer. Note that some analyzers are stemmers and some are
    lemmatizers. Lemmatizers return a "stem" that attempts to be the actual root/canonical form of
    the word being analyzed. Stemmers just return something reasonable, without worrying whether it
    is an actual word, or the root of the word being stemmed.
  * *common:* This shows the common beginning and common ending<sup>‡</sup> of all word types in the
    group. If all types in the group match a prefix or a suffix or both without modification (other
    than lowercasing), the middle bit is ".."; if a match is only found after affix-stripping (see
    below), the middle bit is "::"; if a match is only found after affix-stripping and default
    character folding (see below), the middle bit is "--". If no match is found, this column will
    have " -- " in it.

      <sup>‡ The terms *prefix* and *suffix* are used non-morphologically to refer to
      beginning and ending substrings, but I'm going to use *beginning* and *ending* because I'm
      already using *prefix* and *suffix* with their linguistic/grammar sense.</sup>

      * Groups with no common beginning or ending are potentially problems. At the top of the table
        you'll see "<font color=red>Potential Problem Stems 🅿</font>". This links to the first
        group in the table with no common beginning or ending substring. The *common* "
        -- " will be red, and the stem itself will be followed by <font color=red>🅿</font>, which
        is a link to the next group with no common beginning or ending substring. The stem in the
        last group with no common beginning or ending substring (or if there are none, the initial
        link) takes you to the bottom of the **Stemming Results** table, so you know you are done.
        There is a note there giving the total number of potential problem stems in the list.

  * *group total:* This is the total number of tokens (instances of a word, more or less) in this
    group.
  * *distinct types:* This is the total number of pre-analysis types (distinct words, ignoring case)
    in this group.
  * *types (counts):* This is a list of the types and their frequencies in the group. The format is
    `[<freq> <type>]`.
* **Empty Token Inputs:** This section includes a frequency-sorted list of pre-analysis tokens
  that generate empty (zero-length) post-analysis tokens. An example might be a lone combining
  character or variation selector that then gets normalized to nothing. If there are no empty
  input tokens, this section is omitted.
* **Case-Insensitive Type Group Counts:** This is a small frequency table of the number of
  case-folded pre-analysis types found in the groups in the Stemming Results. (This slightly blurs
  the lines between pre- and post-analysis types by case-folding—lowercasing—everything before
  counting types. Case rarely seems to be distinctive, while all the other kinds of character
  folding can be.) Depending on the size of the corpus and the grammar of the language, what to
  expect here can vary, but obvious outliers should be investigated. Some languages have many more
  forms of a word than others. Smaller corpora are less likely to have as many different forms of
  any particular word.

  * Count values above a certain threshold (see [Hidden Params](#HiddenParams) below) have a link to
    the first group with that number of case-folded pre-analysis tokens in it. On that row of the
    table, the *distinct types* value (which is the same number as the one from the frequency table
    section) links to the next one. The last one links back to the **Case-Insensitive Type Group
    Counts** table.

* **Stemmed Tokens Generated per Input Token:** Most stemmers generate one stem per input token.
  Some, like HebMorph for Hebrew, deal with ambiguity by generating multiple possible stems. The
  `homoglyph_norm` filter can also generate 2 or 3 versions of a token (the original mixed-script
  token, plus possibly an all-Latin or all-Cyrillic version). Very rarely, a token is stemmed to the
  empty string (giving a count of 0). Anything other than a count of 1 is probably unexpected. Up to
  10 tokens are listed under "example input tokens", and they have script colorization applied to
  make the homoglyphs and mixed-CJK tokens stand out.

* **Final Type Lengths:** This is a frequency table, with examples, of the length of tokens found by
  the analyzer. Up to ten examples (with script colorization applied) are randomly selected from the
  list of tokens of a given length. Common long strings include German compounds, and strings from
  languages that don't have spaces (when parsed by analyzers for other languages—e.g., applying the
  `standard` tokenizer to Thai text). A sometimes unexpected source of long tokens is \u-encoded
  strings for multibyte characters (e.g., \uD803\uDC18\uD803\uDC03\uD803\uDC15 for Old Turkic
  𐰘𐰃𐰕), where the length of the \u-encoded string is typically 12x (6 characters x 2 bytes) the
  length of the original.

* **Token Samples by Category:** This is similar to the **Lost and Found Tokens** in a Comparison
Analysis, except that *all* tokens in the corpus are sampled, pre- and post-analysis.

<a name="Singletons"></a>
#### Singletons  <small>[ [TOC](#TOC) ]</small>

A *lot* of terms only show up once and have unique stems, particularly numbers, proper names, and
foreign words (especially ones in a foreign script). By default these are left out of the Stemming
Results, but you can include them by specifying `-1` on the command line. I've only found this
useful when something weird is going on with stemming and I want to look at more examples.

<a name="FoldingLanguages_2"></a>
#### Folding & Languages  <small>[ [TOC](#TOC) ]</small>

The `-f` option, which enables folding, doesn't do anything for a Self Analysis. The `default`
folding config is normally loaded and used in the Stemming Results as a last-ditch attempt to find a
common substring.

As with Comparison Analysis, additional language configs can be supplied. Use `-d` to specify the
directory and `-͏l` to specify a comma-separated list, though usually only one language is needed.
(**NB:** "default" is normally loaded, but it can be disabled by specifying "-default" with `-l`;
see Serbian example under **Folding across character sets** below.) To specify that
`langdata/polish.txt` should be loaded, use `-d langdata -l polish`. All language config files
should end in `.txt`. Note that `-d langdata` is the default, so if you don't move that directory,
you should only need `-l`.

The config for `strip_prefixes` and `strip_suffixes` is similar to the regular morphology used in a
Comparison Analysis (q.v.) specified by `regular_suffixes` and `regular_prefixes`.<sup>§</sup>

`strip_prefixes` and `strip_suffixes` are strippable affixes that can be stripped off tokens when
looking for common substrings (the *common* column of the Stemming Results, above) in a Self
Analysis. Single-letter affixes should probably not be included here because the possibility for
ambiguity is too high.

The list of `strip_prefixes` and `strip_suffixes` may also be determined in part by the analyzer
being investigated rather than regular morphology. The Stempel Polish analyzer, for example, strips
the prefixes *nie-, naj-, anty-, nad-,* and *bez-* (roughly English "-less", "-est", "anti-",
"super-", and "un-"). Once these were identified (see the
[Explore option](#ExploreAutomaticPrefixandSuffixDetection), below), it was helpful to ignore them
when looking for stemming groups with no common ending or beginning substring.

<sup>§ The primary reason that `strip_*fixes` and `regular_*fixes` are distinct is that I
wasn't sure whether or not they should be the same as I was implementing them. `strip_*fixes`, as
they should not include very short affixes, are probably often a subset of `regular_*fixes`. I
should probably refactor and consolidate them in a future version.
</sup>


<a name="SamplesforSpeakerReview"></a>
#### Samples for Speaker Review  <small>[ [TOC](#TOC) ]</small>

You can generate samples of stemming groups for Speaker Review with the `-S` option and a numerical
argument. 25 is probably a good number unless you expect there are problems that need more in-depth
analysis.

The three types of stemming group samples generated are:

* **Random Stemming Groups:** This is a random sample taken from all stemming groups (excluding the
  outliers in the other two groups). This is the most representative sample of the bunch, because it
  is (almost) a random representative sample. These should generally look good to the speaker doing
  the review.

* **Largest Stemming Groups:** This is a sub-sample of the largest stemming groups. Only groups that
  are high enough frequency to get a link in the **Case-Insensitive Type Group Counts** table (see
  [Hidden Params](#HiddenParams) below) are included, and only up to the top *n* largest as
  specified by `-S` are shown. If any of the largest stemming groups are also potential problem
  stemming groups they are shown below, they will not be duplicated in this listing. These should
  mostly look okay to the speaker doing the review. If any are really bad, they can sometimes be
  remediated through the judicious use of stop word filters.

* **Potential Problem Stemming Groups:** This is a random sub-sample of the potential problem
  stems—i.e., those with neither a common beginning or ending substring—from the **Stemming
  Results**. Sometimes these make perfect sense—like English *Dutch* and *Holland* stemming
  together. Sometimes they capture normalization not accounted for in the folding config—like not
  knowing that ɢ being folded to *g* is perfectly reasonable. Sometimes they are wildly wrong—as
  with the generally accurate Stempel statistical stemmer for Polish. Sometimes they can also be
  remediated through the judicious use of stop word filters or pattern filters.

<a name="ExploreAutomaticPrefixandSuffixDetection"></a>
#### Explore (Automatic Prefix and Suffix Detection)  <small>[ [TOC](#TOC) ]</small>

The "explore" option (`-x`) enables automatic prefix and suffix detection. For boring languages like
English, Polish, and other European languages that use lots of prefixes and suffixes (rather than
more interesting forms of morphology, see note † above), this is a good way to find the most common
prefix and suffix alternations, and to see if your language-specific analyzer is doing anything
particularly interesting or unexpected.

For each stemming group, two tests for alternations—*group* and *one-by-one*—are done for both
prefixes and suffixes.

* In the *group* analysis of suffixes, the common beginning substring of all members of a
  stemming group is removed, and all pairs among the leftovers are considered potential suffix
  alternations.
* In the *one-by-one* analysis of suffixes, for each pair of members of a stemming group, their
  common beginning substring is removed, and the leftovers are considered potential suffix
  alternations.
* For prefixes, the process is essentially the same, but the common *ending* substrings are
  removed in each case, and the leftovers are considered potential *prefix* alternations.

Sometimes there's not a lot of difference between the *group* and *one-by-one* analyses. English,
for example, doesn't use a lot of prefixes and doesn't have a lot of diacritics, so these are often
the same. However, for example, among *resume, resumé, résumé, resumes, resumés, résumés,* the group
common beginning substring is only *r* and there is no common ending substring. The *one-by-one*
analysis finds three instances of the obvious *-/s* suffix alternation, though—along with some other
dodgy alternations.

For languages with alternating diacritics (like German) or prefixes and suffixes (like Polish), the
*one-by-one* analysis finds lots of alternations the *group* analysis would miss. On the other hand,
for languages like English, the *group* analysis is less subject to detecting random junk.

The results of the analysis are presented in two additional sections, **Common Prefix Alternations**
and **Common Suffix Alternations.** The each contain a table with the following columns:

* *1x1 count:* This is the number of times this alternation was seen in the *one-by-one* analysis.
* *group count:* This is the number of times this alternation was seen in the *group* analysis.
* *alt 1 / alt 2:* The two alternating affixes. Order is not important, so they are presented in
  alphabetical order. It is possible for *alt 1* to be empty, which means something alternates
  with the empty string (as with English *dog/dogs,* which demonstrates the *-/s* suffix
  alternation.)
* *known:* If a language config file has been specified (using `-l`), then this column indicates
  whether a given alternation is known, i.e., is specified in the config under
  `regular_suffixes` or `regular_prefixes`, or not. Known alternations are marked with an
  asterisk (*).
  * Rows for unknown alternations are bolded and colored red, so you can more easily pick out the
    ones that are not in your language config file, should you care to consider adding them. (If no
    language config with `regular_suffixes` or `regular_prefixes` has been specified, no bold red
    highlighting occurs, since then everything would be red and bold and that's just annoying.) Both
    the color/bolding and asterisk are used so that you can copy the data into a plain text file for
    further exploration without losing the known/unknown distinction.

The results are sorted by combined *group* and *one-by-one* count. Anything with a combined count
below 4 is ignored.

There's likely to be plenty of junk in the low counts, including the remnants of regular processes.
For example, in English, *stem/stemming, hum/humming,* and *program/programming* all show an
apparent *-/ming* alternation, which is really just the "sometimes double the final consonant before
adding *-ing*" rule.

<a name="ThingstoInvestigate_2"></a>
#### Things to Investigate  <small>[ [TOC](#TOC) ]</small>

There is a *lot* of information here. What to do with it all? The things I generally look for
include:

* Big stemming groups. Surprisingly large groups are more likely to have something strange in
  them. I always investigate the largest groups—definitely any outliers, and usually any count
  with a frequency less than 10 (e.g., if there were only 6 groups with 12 distinct word types in
  them, we should investigate all 6.)
  * Sometimes big groups are readily explained. There could be an ambiguous word that is, say,
    both a noun and a verb, and the stemmer deals with this by just lumping all the noun forms
    and all the verb forms together. It's not great, but it is understandable. Other times,
    things are just incorrectly grouped together.
  * I include the largest groups in my data for speaker review.
* Stemming groups with no common beginning/ending substring. This isn't always a problem; for
  example it's reasonable to group English *good / better / best* together,
  or *is / am / are / be / been / was / were*—but it's best to take a look at such cases.
  * I usually include all the groups with no common beginning/ending substring in my data for
    speaker review, unless there's something about the language that makes this very common.
* Random stemming group sample. It's better when the speakers come back and say that the largest
  groups and the groups with no common substring are fine, but even if they don't, it's not the
  end of the world. A random sample of groups with >1 member (i.e., excluding singletons) will
  be most representative of the accuracy of the analyzer over all.
  * I include 25, 50, or even 100 random groups in my data for speaker review, depending on how
    many big groups and groups with no common substring there are.
* Tokens with ≠1 stem. Unless the stemmer regularly spits out multiple stems, it's best to check
  into tokens that generate multiple stems, or no stem!
* Really long tokens. Any corpus could include a long German compound noun, but it's good to
  check on the unexpectedly long words. Is there a tokenization problem? That has been
  particularly likely for spaceless languages in some analyzers!
* Token category by length. The examples under **Final Type Lengths** are randomly selected, and
  so give a very rough idea of the proportions of the categories found among tokens of a
  particular length. For a language that uses the Latin alphabet, for example, I expect tokens
  of length 1 to include a few numbers, a few Latin characters, and, for Wikipedia samples, a
  few random Unicode characters (which could have been included as individual letters, or have
  been separated out by not-so-great Unicode tokenization). Longer tokens tend to include
  website domains and other non-words (*abcdefghijklmnopqrstuvwxyz* pops up from time to time).
  If anything looks unexpected—like all example tokens of length 8 are in foreign
  alphabet—investigate!
* Unexpected categories of tokens. The *unknown* category and sub-categories contain messy tokens;
  they may be worth a quick glance. Look out for categories that appear or disappear between pre-
  and post-analysis! An uncommon category like *Old Turkic* may disappear—because all of the Old
  Turkic tokens, post-analysis, became \u-encoded strings, and are now in the *Unicode/Old
  Turkic* category.
* Unexpectedly common prefix/suffix alternations. If you are using `-x` for automated prefix and
  suffix detection (see [above](#ExploreAutomaticPrefixandSuffixDetection)), not all of the
  automatically detected prefix and suffix alternations are going to be valid. In English, if
  *better* and *best* are stemmed together, then we have a "suffix" alternation between *-tter* and
  *-st,* which is obviously a fluke in English. If the flukey-looking alternations are very high
  frequency, then you should track down the source and see what's going on.

<a name="HiddenParams"></a>
### Hidden Params  <small>[ [TOC](#TOC) ]</small>

There are currently a few parameters that have been reified into variables (*[magic
  numbers](https://en.wikipedia.org/wiki/Magic_number_%28programming%29#Unnamed_numerical_constants)
  bad!*) but not exposed to the command line. I'm pretty sure the default values are reasonable for
  my most common use cases, but every now and then I change them in the code. You might want to,
  too. I should expose them on the command line, and eventually I probably <s>will</s> won't.

* `$min_freqtable_link = 20;` This is the minimum *count* value in the **Case-Insensitive Type Group
  Counts** that gets a link. 10–20 is usually great, depending on the number of inflections a
  language has, except when nothing goes that high—as can happen with a particularly small
  corpus—then 5 is a good value.
* `$token_length_examples = 10;` This is the number of examples in the **Final Type Lengths.**
  Sometimes when there are only 15 instances of a certain length, I want to see them all.
* `$token_count_examples = 10;` This is the number of example input tokens in the **Stemmed Tokens
  Generated per Input Token.** If there are a lot of tokens generating a count of 0 (i.e., no
  token in the output), I might want to see them all.
* `$min_alternation_freq = 4;` This is the minimum combined *group*/*one-by-one* count in the
  **Common Prefix/Suffix Alternations.** Alternations that occur less frequently are not displayed.
  Sometimes you really want to lower it to zero and see *eatre/éâtre,* *ebec/ébec* and friends.
* `$max_lost_found_sample = 100;` This is the maximum number of samples to be shown in **Lost and
  Found Tokens.**
* `$max_solo_cat_sample = 25;` This is the maximum number of samples to be shown in the Self
  Analysis **Token Samples by Category.**
  * `$min_unknown_cat_sample = 100;` This value overrides `$max_solo_cat_sample` for *unknown*
    categories, because they are more interesting that better-defined categories and I want to see
    more samples.
* `$hi_freq_cutoff = 1000;` This is the minimum frequency to be listed under "*hi-freq tokens*" in
  the **Lost and Found Tokens**.
* `$hi_freq_sample = 25;` This is the max size of the sample shown under "*hi-freq tokens*" in the
  **Lost and Found Tokens**. (Note: The sub-sample isn't random; the highest frequency tokens are
  shown.)
* `$hi_impact_cutoff = 10;` Threshold for highlighting "high impact" collisions in **Changed
  Groups,** which is based on the number of types added or deleted to the affected groups.

<a name="AnalysisExampleEnglish"></a>
## Analysis Example: English  <small><small>[ [TOC](#TOC) ]</small></small>

Below I will walk through sample analyses of the English corpus found in the `samples/data/`
directory.

<a name="MySetup"></a>
### My Setup  <small>[ [TOC](#TOC) ]</small>

Your setup doesn't have to be exactly the same as mine, but this works for me without a lot of
customization beyond re-configuring mediawiki for the analyzer I'm working with. You could set up
specific analyzers, etc., directly within the search server, but I do all my work in the context of
MediaWiki and the various wiki projects, so I just work in Docker. You will need Perl and
OpenSearch or Elasticsearch (or Perl and your command-line stemmer) to run `analyze_counts.pl`, and
just Perl to run `compare_counts.pl`.

I have a reasonably up-to-date install of
[MediaWiki Docker](https://www.mediawiki.org/wiki/MediaWiki-Docker) with the
[CirrusSearch](https://www.mediawiki.org/wiki/MediaWiki-Docker/Extension/CirrusSearch) extension
installed. At the time of this writing, the CirrusSearch extension via Docker comes with the plugins
`analysis-icu`, `cirrus-highlighter`, and `extra`, `extra-analysis-textify`, and several
language-specific plugins installed.

My Docker instance doesn't have a lot of documents indexed so I can quickly and easily
re-config/re-index into another language (with `updateSearchIndexConfig.php`, see below).

<a name="GenerateCountFilesforEnglishWithandWithoutFolding"></a>
### Generate Count Files for English With and Without Folding  <small>[ [TOC](#TOC) ]</small>

The primary purpose of this example is to do a Comparison Analysis between configs with and without
character folding. However, we'll take a look at a Self Analysis on the folded config, too.

Since generating the counts files requires re-configuring search and/or MediaWiki, you can skip
these first few steps and just jump down to **Comparison Analysis of the Unfolded and Folded Count
Files** and use the provided English count files, `samples/output/en.counts.unfolded.txt` and
`samples/output/en.counts.folded.txt`.

To generate the count files, `analyze_counts.pl` needs access to the English language analyzer; it
assumes search is running on host `localhost` at port `9200`, with an index called `my_wiki_content`
and a properly configured analyzer called `text`, which are the defaults when using Docker. You can
change these assumptions as necessary when running `analyze_counts.pl` by using `-h`, `-p`, `-i`,
and `-a`.

<a name="ReConfigureMediaWikiSearchforEnglishWithoutFoldingEnabled"></a>
#### Re-Configure MediaWiki/Search for English *Without* Folding Enabled  <small>[ [TOC](#TOC) ]</small>

* in `LocalSettings.php` set `$wgLanguageCode = "en";`
* in `AnalysisConfigBuilder.php` remove `'asciifolding'` from the list in the `withFilters()` method
  in the function `customize()` under `case 'english'`
* reindex; with docker:
  * `docker compose exec mediawiki php maintenance/run.php /var/www/html/w/extensions/CirrusSearch/maintenance/UpdateSearchIndexConfig --reindexAndRemoveOk --indexIdentifier now`

**Note:** If you have the `analysis-icu` plugin installed, the `lowercase` filter will be replaced
with `icu_normalizer` filter. This is the setup I'm running with.

You can check on your config after running `updateSearchIndexConfig.php` above and going to
[your Cirrus Settings Dump](http://127.0.0.1:8080/w/api.php?action=cirrus-settings-dump). Search the
page for *"text"* (with quotes) to see the current analyzer config.

<a name="GeneratetheBeforeUnfoldedCountsFile"></a>
#### Generate the "Before"/Unfolded Counts File  <small>[ [TOC](#TOC) ]</small>

* run: `./analyze_counts.pl -t unfolded -d samples/output/ samples/data/en.txt`
  * STDERR output: `..... 5385`

`samples/output/en.counts.unfolded.txt` now contains the counts for normalized tokens found by the
English analyzer *without* ASCII/ICU folding. It maps both original tokens (found in the text) to
final tokens (those that would be indexed), and vice versa.

<a name="ReConfigureMediaWikiSearchforEnglishWithFoldingEnabled"></a>
#### Re-Configure MediaWiki/Search for English *With* Folding Enabled  <small>[ [TOC](#TOC) ]</small>

Some of the steps and info are the same as above, but are repeated here for completeness.

* in `LocalSettings.php`, you should still have `$wgLanguageCode = "en";`
* in `AnalysisConfigBuilder.php` re-add `'asciifolding'` to the list in the `withFilters()` method
  (between `'stop'` and `'kstem'`) in the function `customize()` under `case 'english'`
* reindex; with docker:
  * `docker compose exec mediawiki php maintenance/run.php /var/www/html/w/extensions/CirrusSearch/maintenance/UpdateSearchIndexConfig --reindexAndRemoveOk --indexIdentifier now`

**Note:** If you have the `analysis-icu` plugin installed, the `lowercase` filter will be replaced
with `icu_normalizer` and the `asciifolding` filter will be replaced with `icu_folding`. This is the
setup I'm running with.

You can check on your config after running `updateSearchIndexConfig.php` above and going to
[your Cirrus Settings Dump](http://127.0.0.1:8080/w/api.php?action=cirrus-settings-dump). Search the
page for *"text"* (with quotes) to see the current analyzer config.

<a name="GeneratetheAfterFoldedCountsFile"></a>
#### Generate the "After"/Folded Counts File  <small>[ [TOC](#TOC) ]</small>

* run: `./analyze_counts.pl -t folded -d samples/output/ samples/data/en.txt`
  * STDERR output: `..... 5385`

The output to STDERR is the same—it's just a progress indicator on the number of lines in the input
file.

`samples/output/en.counts.folded.txt` now contains the counts for normalized tokens *with* ASCII/ICU
folding.

<a name="ComparisonAnalysisoftheUnfoldedandFoldedCountFiles"></a>
### Comparison Analysis of the Unfolded and Folded Count Files  <small>[ [TOC](#TOC) ]</small>

(**NB:** I have `icu-analysis` and `extra-analysis-textify` installed, so I'm using
`icu_normalizer/icu_folding` rather than `lowercase/asciifolding`, and the `textify_icu_tokenizer`
with `icu_token_repair` rather than the `icu_tokenizer` alone or the `standard` tokenizer. I also am
using the most current analyzer configs with lots of generic processing (to handle homoglyphs,
acronyms, camelCase, etc.). If you regenerated the counts files without any of those installed or
enabled, your results will vary.)

<a name="BaselineAnalysis"></a>
#### Baseline Analysis  <small>[ [TOC](#TOC) ]</small>

The simplest analysis is straightforward, with the unfolded counts file as the "old" file and the
folded counts file as the "new" file:

* `./compare_counts.pl -o samples/output/en.counts.unfolded.txt -n samples/output/en.counts.folded.txt > samples/output/en.comp.unfolded_vs_folded.html`

Open `samples/output/en.comp.unfolded_vs_folded.html` in your favorite browser, and let's see what
we see:

* The **Total old/new tokens** are the same, which is what we'd expect. The additional folding
  here takes place after tokenization and shouldn't affect pre-analysis token count.
* Under **Pre/Post Type & Token Stats** the new file's post-analysis types have decreased. As we
  expect, some words are being folded together.
* **New Collision Stats** show no new splits, and only a very few new collisions—less than 1%.
  The actual impact of folding is somewhat larger; some tokens are singletons both before and
  after folding.
* There are no **Lost/Found pre-analysis** tokens because we didn't change the pre-analysis
  processing, specifically tokenizing.
* Looking at the **Lost post-analysis tokens by category** we see:
  * For several of the non-Latin scripts, you can compare the lost tokens to the found tokens and
    see minor variations that are the result of folding. (*Pssst!* I suggest zooming in a lot in
    your browser or editor when looking at scripts you aren't familiar with. It makes the
    details **pop!**)
      * Arabic أبو loses the [hamza](https://en.wikipedia.org/wiki/Hamza) to become ابو after
        folding.
      * Cyrillic барсуко**ў** loses the [breve](https://en.wikipedia.org/wiki/Breve) to become
        барсуко**у**.
      * Devanagari [conjuncts](https://en.wikipedia.org/wiki/Devanagari#Conjuncts) are expanded
        (e.g., भ**ट्ट**राई becomes भ**टट**राई).
      * Hebrew יִשְׂרְאֵלִית loses the [niqqud](https://en.wikipedia.org/wiki/Niqqud) to become
        ישראליות. Note that not all *lost* tokens have counterparts in the *found* tokens. Unfolded
        לִירָה becomes folded לירה, but since לירה is already in the corpus elsewhere, it is not
        "found". This unfolded/folded pair will show up again later under collisions.
      * IPA doesn't show up in the found tokens, because IPA symbols are either dropped if they are
        diacritic-like or converted to plain Latin letters if they are letter-like.
        e.g., *ˈeːijaˌfjœrðʏr̥* becomes *eijafjoerdyr.*
      * Kannada [ashkara](https://en.wikipedia.org/wiki/Kannada_alphabet#Akshara) are converted from
        diacritics to full forms (e.g., ಸಂಕೇ**ಶ್ವ**ರ becomes ಸಂಕೇ**ಶವ**ರ).
      * Katakana [dakuten](https://en.wikipedia.org/wiki/Dakuten_and_handakuten) are removed (e.g.,
        テレ**ビ** becomes テレ**ヒ**).
      * Note that the number of lost and found *Latin* tokens don't match up exactly because some
        lost tokens will not be "found". For example, if *resumé* and *resume* were both in the
        corpus, then *resumé* would be lost (there are no more instances of it in the output), but
        *resume* would not be found, because it was already in the output.
* A quick skim of the **Changed Groups** doesn't show anything untoward.

<a name="SimpleFoldedAnalysis"></a>
#### Simple Folded Analysis  <small>[ [TOC](#TOC) ]</small>

Let's try it again, but this time enable folding (adding `-f` and, for a comparison analysis,
`-t 2`):

* `./compare_counts.pl -o samples/output/en.counts.unfolded.txt -n samples/output/en.counts.folded.txt -f -t 2 > samples/output/en.comp.unfolded_vs_folded._f.html`

Setting terseness to 2 (`-t 2`) removes all of the folded items from the **Changed Groups/Net
Gains** list. Otherwise, the only difference in the report would be the **New Collision Near Match
Stats** showing a number of folded collisions.

With terseness set to 2, the obvious difference is in the **Net Gains** section. There are now only
10 gains/collisions instead of 68. The other 58 were the "expected" ones, based on the folding rules
specified in `langdata/default.txt`.

Two of the eight are the Hebrew words with niqqud that we saw earlier (and one with two invisible
left-to-right marks). Four of the remaining six, reformatted, are:

        g   [1 ɢ]   -> [18 G][3 g]
        ku  [3 ḵu]  -> [1 ku]
        kun [1 ḵun] -> [1 kun]
        re  [1 ʁɛ̃]  -> [3 Re][24 re]

Those are all quite reasonable. It seems that `langdata/default.txt` doesn't include certain
combining diacritics and variants with rare diacritics. Nothing much to see here.

Another two show diacriticized words that also happen to have possessive apostrophe (one plain, one
curly) + *s,* where there is no undiacriticized possessive.

        glogow [1 Głogów's] -> [1 GLOGOW][12 Głogów]
        rene   [1 René’s]   -> [2 Rene][11 René]


The remaining two, though, show something interesting:

        gab  [1 Gábor]  -> [1 Gabes][1 gabions]
        worn [2 Wörner] -> [6 worn]

If you look in `AnalysisConfigBuilder.php` you'll see that `asciifolding` is configured to happen
right before `kstem`, which does the actual stemming for English. With diacritics, *gábor* and
*wörner* are untouched. Without the diacritics, their final *-er* and *-or* are seen as suffixes
(like *work-er* and *direct-or*) and stripped off.

Unless you try to maintain a complete lexicon of every word in a language—which is impossible!—this
kind of thing is going to happen, because heuristics are never perfect. (If they were, they'd be
*rules,* and English has never met a spelling "rule" it couldn't break.) So, while this isn't
particularly *good,* it is understandable, and more or less expected.

Whether or not ASCII folding should happen before or after stemming in English is something I looked
at with a much earlier (and more confusing) version of these tools. My
[detailed write up](https://www.mediawiki.org/wiki/User:TJones_%28WMF%29/Notes/Re-Ordering_Stemming_and_Ascii-Folding_on_English_Wikipedia)
is on MediaWiki.org.


<a name="FoldedEnglishSelfAnalysis"></a>
### Folded English Self Analysis  <small>[ [TOC](#TOC) ]</small>

For this Self Analysis we'll use the same folded English count file (with `-n`) that we used in the
Comparison Analysis, enable the "explore" option (`-x`) for automatic prefix/suffix detection,
include the English language config (`-l english`) to see what it knows, and ask for a small sample
of 10 (`-S 10`) for speaker review.

* `./compare_counts.pl -n samples/output/en.counts.folded.txt -x -l english -S 10 > samples/output/en.comp.folded_self.html`

Open `samples/output/en.comp.folded_self.html` in your favorite browser. In the Table of Contents,
click on **Stemming Results,** and then <font color=red>Potential Problem Stems 🅿</font>, which
will take you to the first group that doesn't have either a common beginning or ending substring.

1. The stem *committee* includes *<font color=red>с</font><font color=green>ommittee</font>,* where
   the first letter, <font color=red>с</font>, is actually Cyrillic. Click on <font
   color=red>🅿</font> to continue...
1. The stem *dutch* includes tokens *Dutch* and *Holland.* Neat! Continuing...
1. Stem *g* and IPA token *ɢ.* Nothing to see here...
1. Stem *philippines* includes tokens *Filipino* and *Philippines.* Neat again...

... and that's it. Clicking on the last <font color=red>🅿</font> takes you to the end of the
**Stemming Results** where there is a small summary: "[Total of 4 potential problem stems]". If you
scroll up a bit, you can see the last two items, which are in Hebrew.

Nothing terrible, and we learned that there are some specific lexical exceptions in the English
stemmer. And so searching for
*[**holland** east india company](https://en.wikipedia.org/w/index.php?search=holland+east+india+company)*
on English Wikipedia gets you the right thing.

You will also see a link for <font color=green>Mixed-Script Groups 🅼</font> next to <font
color=red>Potential Problem Stems 🅿</font>. In this case, clicking on that will take you to the
*<font color=red>с</font><font color=green>ommittee</font>* example above, which is the only
mixed-script token in this sample. Clicking on <font color=green>🅼</font> takes you to the end of
the **Stemming Results** where there is a small summary: "[Total of 1 mixed-script group]".

The **Samples for Speaker Review** start with a random collection of stemming groups. In this small
sample of English Wikipedia articles, the most common number of words in a group is just two. There
aren't any stemming groups large enough to be counted among the "largest" stemming groups, and the
four potential problem stems from above are gathered together for easy sharing with a speaker.

Next up, English doesn't have any **Common Prefix Alternations,** but it has lots of **Common Suffix
Alternations.** Many of them are in the English language config, but some are not yet. The first
item in red is the possessive *-/'s* alternation; there is a lot more of *'s* throughout the list.
Silent *e,* as in *hope/hoped/hopes* is responsible for the *-/d* and *d/s* alternations (the next
two in red). Pluralizing words ending in *-y* often does indeed give *-ies.* There's some good stuff
at the top of the list. Towards the bottom we see a small number of semi-spurious alternations that
are caused by doubling final letters before adding *-ing* or *-ed.* And some weird but
understandable stuff, like *iness/y* (from _empt**iness**/empt**y**_ and
_lonel**iness**/lonel**y**,_ but fortunately *not* _bus**iness**/bus**y**!_).

Mining these isn't going to do much for English because the stemmer here doesn't seem to know any
prefixes, so common beginning substrings are usually easy to find. But for languages with both
prefixes and suffixes (like Polish) this helps us find regular alternations that will decrease the
number of items with no common beginning or ending substrings—or odd alternations that might
indicate something weird or unexpected is going on.

The **Case-Insensitive Type Group Counts** shows that we skipped 14,620 singletons (which you can
get see with the `-1` option if you want them).

The overly-verbosely titled **Stemmed Tokens Generated per Input Token** shows that the English
analyzer is generally one-token-in, one-token-out, modulo tokens with Cyrillic/Latin homoglyphs.

The **Final Type Lengths** shows <s>that there are lots of 1-character CJK types,
and</s><sup>‖</sup> that the longest types are generally technical and/or German. Most types are
3–10 characters long, and most tokens are 3–8 characters long. More or less as expected.

<sup>‖ There *used* to be lots of 1-character CJK types, but English has been upgraded to the
`textify_icu_tokenizer`, which does a decent or better job with tokenizing several spaceless East
Asian languages. </sup>

The **Token Samples by Category** show a few interesting things that didn't show up in the unfolded
vs folded Comparative Analysis because they don't change:
* The *mixed-Cyrillic-Latin* category includes the mixed-script token *<font color=red>с</font><font
  color=green>ommittee</font>.* Pesky homoglyphs!
* The *Arabic+bidi,* *Hebrew+bidi,* and *Latin+nbsp* categories only exist on the Pre-analysis side
  because many invisible characters (so many left-to-right marks!) get normalized away.
* The *Latin+acronym-like* and *Latin+acronyms* categories also only exist on the Pre-analysis side
  because acronyms now get their dots removed.
* *Latin, grave-sep* disappears because the naked grave is normalized to an apostrophe by the newish
  `globo_norm` filter, which subsumed the former `apostrophe_norm` filter.
* In the *known symbols* and category, we have the token *µ* (the micro sign, U+00B5). It gets
  converted to *μ* (Greek mu, U+03BC) by ICU normalization. *μ* by itself shows up as a
  post-analysis Greek token.
* There are lots of other categories—Greek, Gujarati, Hangul, Ideographic, Tibetan, integers—that
  have tokens that are unchanged by folding, so seeing them here lets us know they exist, and their
  relative proportions.


<a name="HighlightsfromOtherAnalyses"></a>
### Highlights from Other Analyses  <small><small>[ [TOC](#TOC) ]</small></small>

Since the English example ended up being longer than I expected, I'm not going to work another
example. Instead I'll point out some interesting stuff this kind of analysis has let me find,
pointing back to my notes on MediaWiki.org.

* **Unexpected folding in French:** When looking at whether to add ASCII folding to to the French
  analyzer, I discovered that
  [some unexpected folding](https://www.mediawiki.org/wiki/User:TJones_%28WMF%29/Notes/Adding_Ascii-Folding_to_French_Wikipedia#Unexpected_Features_of_French_Analysis_Chain)
  was already being done by the analyzer! In order to get more comprehensive ASCII folding, we
  were using the the guide that Elasticsearch provides for
  [unpacking the default analyzers](https://www.elastic.co/guide/en/elasticsearch/reference/current/analysis-lang-analyzer.html)
  into their constituent parts for customization. We expected the unpacked analyzer to be
  identical; I tested it primarily to make sure I'd configured the unpacked version
  correctly. Turns out, there were some
  [minor differences](https://www.mediawiki.org/wiki/User:TJones_%28WMF%29/Notes/Adding_Ascii-Folding_to_French_Wikipedia#Unexpected_Differences_in_Unpacked_Analysis_Chain)
  triggered by our automatic analysis chain "enhancements" that come out in large corpus
  testing! (There are now *lots* of differences that result from all the automatic upgrades we apply
  to non-monolithic analysis chains.)

* **Upgrading to a real Polish analyzer:** The analysis revealed that the Stempel Polish analyzer
  was unexpectedly
  [stripping non-grammatical prefixes](https://www.mediawiki.org/wiki/User:TJones_%28WMF%29/Notes/Stempel_Analyzer_Analysis#Further_Semi-Automatic_Analysis)—*nie-,
  naj-, anty-, nad-,* and *bez-* (roughly "-less", "-est", "anti-", "super-", and "un-"), as
  previously mentioned above. This isn't necessarily a bad thing, just unexpected, since most
  stemmers only strip grammatical affixes (like verb conjugations and noun declensions).

  More surprisingly, the statistical nature of the stemmer was causing it to
  [glitch](https://www.mediawiki.org/wiki/User:TJones_%28WMF%29/Notes/Stempel_Analyzer_Analysis#Error_Examples),
  especially on numbers and foreign words. This is what lead me to several of my heuristics,
  particularly looking at very big groups and groups with no common beginning or ending
  substrings. Despite the problems, Stempel is still very cool and seems to be an improvement
  overall.

  * If you want to do some Polish analysis for yourself, I've included
    `samples/output/pl.counts.default.txt` and `samples/output/pl.counts.stempel.txt`, which
    are the default and Stempel count files for the 1MB Polish sample in `samples/data/pl.txt`.
    You can generate an example Self Analysis for the Polish sample with this command:

      * `./compare_counts.pl -n samples/output/pl.counts.stempel.txt -x -l polish -S 10 > samples/output/pl.comp.stempel_self.html`

* **Doing exactly the wrong thing in Swedish:** Nothing too exciting came from my initial
  [Swedish analysis](https://www.mediawiki.org/wiki/User:TJones_%28WMF%29/Notes/Swedish_Analyzer_Analysis#Unpacked_vs_Folded.E2.80.94Now_With_Too_Much_Folding.C2.A0),
  except that it made it very clear during speaker review that we were doing *exactly* the
  wrong thing. Once we did it right, there were still some
  [sub-optimal collisions](https://www.mediawiki.org/wiki/User:TJones_%28WMF%29/Notes/Swedish_Analyzer_Analysis#Unpacked_vs_Folded.E2.80.94Folded_Just_Right),
  but the impact was much smaller and much less violent to Swedish words.

* **Ukrainian is very similar to Russian:** For
  [historical reasons](https://phabricator.wikimedia.org/T147959),
  Ukrainian-language projects used to use Russian morphological processing. After
  [discussing it with a Ukrainian speaker](https://phabricator.wikimedia.org/T146358#2700391),
  we decided it was, surprisingly, better than nothing, especially once we made the Russian
  config aware that it was sometimes used for Ukrainian.

  Later, when a Ukrainian analyzer became available,
  [analysis](https://www.mediawiki.org/wiki/User:TJones_%28WMF%29/Notes/Ukrainian_Morfologik_Analysis#Ukrainian-Aware_Russian_config_vs_New_Ukrainian_Morfologik_Analyzer)
  showed lots of new collisions (the Ukrainian analyzer stemming stuff that the Russian
  analyzer missed) and lots of splits (the Russian analyzer stemming stuff it shouldn't
  have). The analysis of Ukrainian also revealed a small number of
  [fairly dodgy-looking groups](https://www.mediawiki.org/wiki/User:TJones_%28WMF%29/Notes/Ukrainian_Morfologik_Analysis#Unexpected_groupings).
  Speaker review revealed that they were generally okay—which restored confidence. And, really,
  should I, as an English speaker, be surprised by anything in any other language, given
  that English has *be / being / been / am / is / are / was / were*?

* **Chinese, Traditional and Simplified:** When I went to implement a new analysis chain for
  Chinese, it included a plugin for
  [Traditional to Simplified](https://en.wikipedia.org/wiki/Debate_on_traditional_and_simplified_Chinese_characters)
  conversion (T2S), which was needed because the available tokenizers only work well on Simplified
  characters. Unfortunately, the search T2S conversion is separate from the MediaWiki display T2S
  conversion, so mismatches were possible. Fortunately, I was able to extract the MediaWiki display
  T2S conversion and convert it to folding info in `langdata/chinese.txt`, which allowed me to
  ignore any collisions caused by mappings that the two independent converters agreed on. Whew! That
  reduced thousands of conversion-related collisions down to a
  [manageable 99](https://www.mediawiki.org/wiki/User:TJones_%28WMF%29/Notes/Chinese_Analyzer_Analysis#Analysis_Results).

* **Hebrew likes affixes and dislikes vowels:** The HebMorph analyzer made me pay attention to
  how many tokens an analyzer generates. There was a huge increase in total tokens in my
  corpus, from 2.5M to 6.1M. Because of the ambiguity in
  Hebrew—[vowels are mostly omitted](https://en.wikipedia.org/wiki/Abjad) and there are lots
  of common one- and two-letter [prefixes](https://en.wikipedia.org/wiki/Prefixes_in_Hebrew)
  and [suffixes](https://en.wikipedia.org/wiki/Suffixes_in_Hebrew)—the analyzer doesn't give just
  *one* best guess at the root form, but
  [typically two and often three](https://www.mediawiki.org/wiki/User:TJones_%28WMF%29/Notes/HebMorph_Analyzer_Analysis#Comparing_Analyzers).
  Using different options for the analyzer got the count as low as 3.8M.

* **Loooooooong Japanese Tokens:** The switch from the default CJK analyzer (which uses
  overlapping bigrams for [CJK characters](https://en.wikipedia.org/wiki/CJK_characters)) to
  the Japanese-specific Kuromoji decreased
  [the number of tokens found from 5.5M to 2.4M](https://www.mediawiki.org/wiki/User:TJones_%28WMF%29/Notes/Kuromoji_Analyzer_Analysis#Baseline_.28CJK.29_vs_Kuromoji)
  in my corpus—that's a lot fewer overlapping tokens, and many words longer than 2 characters.
  However, the lost/found token analysis showed that it was ignoring tokens in at least a dozen
  other scripts, and doing weird things with fullwidth numbers. The Kuromoji analyzer also
  revealed the need to look at
  [really long tokens](https://www.mediawiki.org/wiki/User:TJones_%28WMF%29/Notes/Kuromoji_Analyzer_Analysis#Longest_Tokens).
  In addition to some long Latin-script and Thai tokens, there were some really long Japanese
  tokens, which turned out to be tokenizing errors; these phrases and sentences just weren't
  broken up.

* **Folding across character sets with Japanese Kana and in Serbian:**
  * We got a [request](https://phabricator.wikimedia.org/T176197) to fold Japanese [Hiragana and
    Katakana](https://en.wikipedia.org/wiki/Kana#Hiragana_and_katakana) on English-language
    wikis. There's a straightforward 1-to-1 mapping (in `langdata/kana.txt`) that allows
    `compare_counts.pl` to ignore that alternation and only pay attention to other changes. It
    worked
    [fine for English](https://www.mediawiki.org/wiki/User:TJones_%28WMF%29/Notes/Hiragana_to_Katakana_Mapping_for_English_and_Japanese),
    but when unpacking the CJK analyzer for Japanese it caused too many other problems.

  * Serbian has both a [Cyrillic](https://en.wikipedia.org/wiki/Serbian_Cyrillic_alphabet) and a
    [Latin](https://en.wikipedia.org/wiki/Gaj%27s_Latin_alphabet) alphabet. When
    [assessing a potential Serbian stemmer](https://www.mediawiki.org/wiki/User:TJones_%28WMF%29/Notes/Serbian_Stemmer_Analysis)
    it was helpful to not count Cyrillic/Latin alternations as Potential Problem Stems. There is a
    one-to-one mapping between the Serbian Cyrillic and Serbian Latin alphabets, but the normal
    Serbian Latin alphabet uses characters with diacritics (*ć, č, đ, š,* and *ž*). Using this
    direct Cyrillic-to-Latin mapping (in `langdata/serbian_c2l.txt`) does not play
    well with the `default` mapping. Serbian Cyrillic *ш* is mapped to Latin *š,* but Latin *š* is
    mapped to *s.* The default mapping, which maps *š* to *s,* can be disabled by specifying
    *-default* as a language, as in `-l serbian_c2l,-default`. Alternatively, there is a Serbian
    encoding called "dual1"—used in some academic papers and by the Serbian stemming library I was
    investigating—that uses *x* and *y* to represent characters that have diacritic in the Latin
    alphabet. So, both *ш* and *š* would be represented as *sx* (similar to how the same sound is
    represented in English by *sh*). `-l serbian_dual1` works fine without disabling the `default`
    mapping, but the resulting stems are less transparent.

* **Custom tools:** Sometimes you need custom tools because there is no end to the weird and
  wonderful variation that is the awesomeness of language.
  * Another problem with Japanese was that speakers doing review asked for samples of where the
    tokens had come from. I was able to hack `analyze_counts.pl` to generate samples for a
    specific list of tokens, but it was too messy to keep in the code. A proper implementation
    might be useful.
  * For Chinese and Japanese—both spaceless languages—I used an external tool to evaluate
    segmentation done by the analyzer. For Chinese, the tool came with a segmented corpus. For
    Japanese I had to find an annotated corpus and munge it into a useful form. Fun times!
    (Everything is described in more detail, with links, in my write ups.)

* **Using multiple text editors/viewers is sometimes helpful:** I sometimes use `less` on the
  command line to look at counts files output by `analyze_counts.pl`. Sometimes I use `vim`,
  sometimes [BBEdit](https://en.wikipedia.org/wiki/BBEdit). For the HTML reports, I often use
  Chrome, unless it is giving me trouble with particular character sets, then I use Safari, which
  often renders complex text and non-Latin scripts better. A few interesting things have come up:
  * A doubly accented Russian word, **Ли́́вшиц,** can show up with two accents on top of each
    other, with one accent (presumably actually two overlayed), or with the accents as separate
    characters. When overlayed, they'd be impossible to notice!
  * Some text processors hide
    [bi-directional marks](https://en.wikipedia.org/wiki/Bi-directional_text#marks) and various
    [zero-width Unicode characters](https://en.wikipedia.org/wiki/Zero_width). `compare_counts.pl`
    highlights them now, but I never would've found them in certain editors.

<a name="StuffYetToDo"></a>
## Stuff Yet To Do  <small><small>[ [TOC](#TOC) ]</small></small>

Here are a bunch of things I should probably do, but may never get around to:

* `analyze_counts.pl`
   * *Tech Debt*
      * Proper implementation of context sampling for specified tokens.
   * *New Features*
      * Consider allowing calling out to external command-line stemmer (all in one pass)
* `compare_counts.pl`
   * *Tech Debt*
      * Add checks that language files and other config files exist and/or open properly.
      * Refactor / consolidate `strip_*fixes` and `regular_*fixes`.
         * Consider ordering affix groups to support more heavily-inflected languages. For example,
           Indonesian prefixes include *mem-, ke-, ber-, per-, member-, memper-, keber-,* and
           *keper-.* What's really going on is that *mem-* or *ke-* can be followed by *ber-* or
           *per-,* or any of them can be used alone. At the very least, all combinations should not
           have to be explicitly spelled out in the config file.
      * Better error checking for input format.
      * Add samples to Common Prefix/Suffix Alternations.
      * Expose the hidden parameters.
      * Add a random seed so random examples are consistent between runs (useful during dev).
   * *New Features*
      * Add support for matching root against inflected forms to look for "problem" stems. Very
        simple longest affix matching can get confused, especially when stems include common affix
        bits. Possibly check that non-root part matches known affixes.
      * Allow some folding on "old" tokens to compare to "new" tokens. (This came up in Serbian—old
        token is Cyrillic, new token is Latin, everything is folded to Latin, so new token can't
        match old, generating lots of unneeded "bad" collisions.)
* Why Not Both!
   * *Tech Debt*
      * Add checks that input files exist, open properly, and are properly formatted.
      * Use proper JSON parsing (without introducing external dependencies).
      * Explicitly specify output files.
      * Optionally disable progress indicator.
      * Add some unit tests.
      * Refactor, refactor, refactor: break up larger, more complex, or more indented functions—just
        to hush `perlcritic`.

Contact me if you want to encourage me to prioritize any of these improvements over the others!

<br>
<a name="Disclaimer"></a>

> **Disclaimer:** Believe it or not, these tools started out as various Unix utilities and Perl
> one-liners piped together on the command line. Their development has been a process of discovery
> and evolution, rather than top-down design, because I didn't know what I needed to know until I
> found that I didn't know it. `;)`
>
> As a result, there's some pretty crappy code in here, and all of it needs a top-down refactor,
> which will likely never happen. But I was told—quite correctly—that I should share my tools to up
> the [bus number](https://en.wikipedia.org/wiki/Bus_factor) on this whole "analysis analysis"
> thing.
>
> I've tried to do some basic clean-up with
> [`perlcritic`](https://en.wikipedia.org/wiki/Perl::Critic) and
> *[Perl Best Practices](https://en.wikipedia.org/wiki/Perl_Best_Practices),* but like many
> developers, the horror of ugly-but-working code is often not enough to overcome inertia and/or
> other priorities.
>
> Hopefully the extensive documentation makes up for the sub-optimal code. (And of course, since
> this documentation is so complex, the [Markdown](https://en.wikipedia.org/wiki/Markdown) is
> sufficiently complex that not every renderer is going to do it <s>right</s> the same. I broke down
> in a couple of places and just used HTML. Sorry about that, too!)

<small>**[ [TOC](#TOC) ]**</small>


<!---
Regenerate all sample comparison output files:
./compare_counts.pl -o samples/output/en.counts.unfolded.txt -n samples/output/en.counts.folded.txt > samples/output/en.comp.unfolded_vs_folded.html
./compare_counts.pl -o samples/output/en.counts.unfolded.txt -n samples/output/en.counts.folded.txt -f -t 2 > samples/output/en.comp.unfolded_vs_folded._f.html
./compare_counts.pl -n samples/output/en.counts.folded.txt -x -l english -S 10 > samples/output/en.comp.folded_self.html
./compare_counts.pl -n samples/output/pl.counts.stempel.txt -x -l polish -S 10 > samples/output/pl.comp.stempel_self.html
-->
