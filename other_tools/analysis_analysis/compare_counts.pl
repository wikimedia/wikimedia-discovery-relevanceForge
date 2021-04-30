#! /usr/bin/perl

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

use warnings;
use strict;
use utf8;
no warnings 'utf8';
use IO::Handle;
use Encode;
use Getopt::Std;

# set up output
*STDOUT->autoflush();
*STDERR->autoflush();
binmode(STDERR, ":encoding(UTF-8)");
binmode(STDOUT, ":encoding(UTF-8)");

# initialize data structures
my %config = ();            # general configuration settings/data
my %language_data = ();     # language-specific affix info
my %common_affixes = ();    # prefixes and suffixes found automatically
my %statistics = ();        # general stats on type and token counts, etc.
my %mapping = ();           # list of words that map to the given stem
my @stemming_results = ();  # the results of the new-only stemming grouping
my %old_v_new_results = (); # the results of comparing stemming group changes

# get options
our ($opt_d, $opt_f, $opt_h, $opt_l, $opt_n, $opt_o, $opt_s, $opt_t, $opt_x, $opt_1);
getopts('d:fhl:n:o:s:t:x1');

my $old_file = $opt_o;
my $new_file = $opt_n;

if (!$new_file || ! -e $new_file) {
	usage();
	exit;
	}

# set up the config
$config{data_directory} = $opt_d || 'compare_counts/langdata/';
$config{explore} = $opt_x;
$config{singletons} = $opt_1;
$config{HTML} = $opt_h;
$config{fold} = $opt_f;
$config{min_stem_len} = $opt_s || 5;
$opt_l ||= '';
%{$config{lang}} = map {lc($_) => 1} split(/[, ]+/, $opt_l);
$config{terse} = $opt_t;
$config{terse} ||= 0;

my $min_histogram_link = 10;
my $token_length_examples = 10;
my $token_count_examples = 10;
my $min_alternation_freq = 4;
my $max_lost_found_sample = 100;
my $hi_freq_cutoff = 1000;
my $hi_impact_cutoff = 10;

# get to work
lang_specific_setup();
process_token_count_file($old_file, 'old') if $old_file;
process_token_count_file($new_file, 'new');

# text/HTML formatting
my $bold_open = '';
my $bold_close = '';
my $italic_open = '';
my $italic_close = '';
my $red_open = '';
my $red_close = '';
my $cr = "\n";
my $ws_wrap = "\n" . ' 'x7;	#whitespace wrap
my $indent = "    ";
my $block_open = $indent;
my $block_close = $cr;

if ($config{HTML}) {
	$bold_open = '<b>';
	$bold_close = '</b>';
	$italic_open = '<i>';
	$italic_close = '</i>';
	$block_open = '<blockquote>';
	$block_close = '</blockquote>';
	$red_open = '<span class=red>';
	$red_close = '</span>';
	$cr = "<br>\n";
	$ws_wrap = '';
	$indent = '&nbsp;&nbsp;&nbsp;';
	}

my $HTMLmeta = <<"HTML";
<meta http-equiv='Content-Type' content='text/html; charset=utf-8' />
<style>
    th, td { text-align:left; vertical-align: top; border: 1px solid black; dir:auto; }
    table { border-collapse: collapse; }
    .red { color: red; font-weight: bold; }
    tr:nth-child(even) { background: #f8f8f8 }
    .hang {padding-left: 2em ; text-indent: -2em}
</style>
HTML

if ($old_file) {

	my %is_overlap = ();

	foreach my $final (keys %mapping) {
		if ($mapping{$final}{old} &&
				$mapping{$final}{new} &&
				$mapping{$final}{old} ne $mapping{$final}{new}) {
			my %old = ();
			my %new = ();
			my %lc_old = ();
			my %lc_new = ();
			while ($mapping{$final}{old} =~ /\[(\d+) (.*?)\]/g) {
				$old{$2} += $1;
				$lc_old{lc($2)} = 1;
				}
			while ($mapping{$final}{new} =~ /\[(\d+) (.*?)\]/g) {
				$new{$2} += $1;
				$lc_new{lc($2)} = 1;
				}

			my %counts = ();
			foreach my $term (uniq(keys %old, keys %new)) {
				if ($old{$term} && $new{$term}) {
					$counts{both}{pre_type}++;
					if ($new{$term} != $old{$term}) {
						$counts{both}{net_tokens} += $new{$term} - $old{$term};
						if ($new{$term} > $old{$term}) {
							$counts{gains}{pre_type}++;
							$counts{gains}{token} += $new{$term} - $old{$term};
							}
						elsif ($new{$term} < $old{$term}) {
							$counts{losses}{pre_type}++;
							$counts{losses}{token} += $old{$term} - $new{$term};
							}
						}
					}
				elsif ($old{$term}) {
					$counts{old}{pre_type}++;
					$counts{old}{token} += $old{$term};
					}
				else {
					$counts{new}{pre_type}++;
					$counts{new}{token} += $new{$term};
					}
				}


			if (!defined $counts{both}{pre_type} || $counts{both}{pre_type} == 0) {
				next;
				}

			$is_overlap{$final} = 1;

			if ($counts{new}{pre_type}) {
				$old_v_new_results{collision}{post_type}++;
				$old_v_new_results{collision}{pre_type_total} += $counts{both}{pre_type} +
					$counts{new}{pre_type};
				$old_v_new_results{collision}{pre_type_new} += $counts{new}{pre_type};
				$old_v_new_results{collision}{token} += $counts{new}{token};
				}

			if ($counts{old}{pre_type}) {
				$old_v_new_results{splits}{post_type}++;
				$old_v_new_results{splits}{pre_type_total} += $counts{both}{pre_type} + $counts{old}{pre_type};
				$old_v_new_results{splits}{pre_type_new} += $counts{old}{pre_type};
				$old_v_new_results{splits}{token} += $counts{old}{token};
				}

			if ($counts{gains}{pre_type}) {
				$old_v_new_results{gains}{post_type}++;
				$old_v_new_results{gains}{pre_type} += $counts{gains}{pre_type};
				$old_v_new_results{gains}{token} += $counts{gains}{token};
				}

			if ($counts{losses}{pre_type}) {
				$old_v_new_results{losses}{post_type}++;
				$old_v_new_results{losses}{pre_type} += $counts{losses}{pre_type};
				$old_v_new_results{losses}{token} += $counts{losses}{token};
				}

			foreach my $n (keys %new) {
				my $lc_n = lc($n);
				if ($lc_old{$lc_n}) {
					next;
					}
				if ( $lc_old{fold($lc_n)} || $lc_old{despace($lc_n)} || $lc_old{dehyphenate($lc_n)} ) {
					$old_v_new_results{collision}{near_match}{folded}{type}++;
					$old_v_new_results{collision}{near_match}{folded}{token} += $new{$n};
					next;
					}

				my $morph_match = 0;
				foreach my $ref (@{$language_data{regular_suffixes_array}}) {
					my $alt1 = $ref->[0];
					my $alt2 = $ref->[1];
					my $min_stem_len = $config{min_stem_len};

					if ($lc_n =~ /^(.{$min_stem_len}.*)$alt1$/) {
						my $nn = $1 . $alt2;
						if ($lc_old{$nn}) {
							$old_v_new_results{collision}{near_match}{regulars}{type}++;
							$old_v_new_results{collision}{near_match}{regulars}{token} += $new{$n};
							$morph_match = 1;
							last;
							}
						if ($lc_old{fold($nn)} || $lc_old{despace($nn)} || $lc_old{dehyphenate($nn)} ) {
							$old_v_new_results{collision}{near_match}{folded_regulars}{type}++;
							$old_v_new_results{collision}{near_match}{folded_regulars}{token} += $new{$n};
							$morph_match = 1;
							last;
							}
						} # ends in alt1

					if (!$morph_match && $lc_n =~ /^(.{$min_stem_len}.*)$alt2$/) {
						my $nn = $1 . $alt1;
						if ($lc_old{$nn}) {
							$old_v_new_results{collision}{near_match}{regulars}{type}++;
							$old_v_new_results{collision}{near_match}{regulars}{token} += $new{$n};
							$morph_match = 1;
							last;
							}
						if ($lc_old{fold($nn)} || $lc_old{despace($nn)} || $lc_old{dehyphenate($nn)} ) {
							$old_v_new_results{collision}{near_match}{folded_regulars}{type}++;
							$old_v_new_results{collision}{near_match}{folded_regulars}{token} += $new{$n};
							$morph_match = 1;
							last;
							}
						} # ends in alt2
					}

				if ($morph_match) {
					next;
					}

				foreach my $ref (@{$language_data{regular_prefixes_array}}) {
					my $alt1 = $ref->[0];
					my $alt2 = $ref->[1];
					my $min_stem_len = $config{min_stem_len};
					if ($lc_n =~ /^$alt1(.{$min_stem_len}.*)$/) {
						my $nn = $alt2 . $1;
						if ($lc_old{$nn}) {
							$old_v_new_results{collision}{near_match}{regulars}{type}++;
							$old_v_new_results{collision}{near_match}{regulars}{token} += $new{$n};
							$morph_match = 1;
							last;
							}
						if ($lc_old{fold($nn)} || $lc_old{despace($nn)} || $lc_old{dehyphenate($nn)} ) {
							$old_v_new_results{collision}{near_match}{folded_regulars}{type}++;
							$old_v_new_results{collision}{near_match}{folded_regulars}{token} += $new{$n};
							$morph_match = 1;
							last;
							}
						} # begins in alt1

					if (!$morph_match && $lc_n =~ /^$alt2(.{$min_stem_len}.*)$/) {
						my $nn = $alt1 . $1;
						if ($lc_old{$nn}) {
							$old_v_new_results{collision}{near_match}{regulars}{type}++;
							$old_v_new_results{collision}{near_match}{regulars}{token} += $new{$n};
							$morph_match = 1;
							last;
							}
						if ($lc_old{fold($nn)} || $lc_old{despace($nn)} || $lc_old{dehyphenate($nn)} ) {
							$old_v_new_results{collision}{near_match}{folded_regulars}{type}++;
							$old_v_new_results{collision}{near_match}{folded_regulars}{token} += $new{$n};
							$morph_match = 1;
							last;
							}
						} # begins in alt2
					}

				if ($morph_match) {
					next;
					}

				$old_v_new_results{collision}{near_match}{other}{type}++;
				$old_v_new_results{collision}{near_match}{other}{token} += $new{$n};

				push @{$old_v_new_results{bad_collisions}}, [$final, $new{$n}, $n];
				}

			if ($counts{both}{pre_type}) {
				foreach my $o (keys %old) {
					my $lc_o = lc($o);
					if (!$lc_new{$lc_o}) {
						push @{$old_v_new_results{bad_splits}}, [$final, $old{$o}, $o];
						}
					}
				}

			}
		}

	foreach my $final (sort keys %mapping) {
		next unless $is_overlap{$final};
		if ($mapping{$final}{old} &&
				$mapping{$final}{new} &&
				$mapping{$final}{old} ne $mapping{$final}{new}) {
			my $mapo = $mapping{$final}{old};
			my $mapn = $mapping{$final}{new};
			my %old_tokens = ();
			my %tok_cnt = ();
			my $incr = 0;
			my $decr = 0;

			while ($mapo =~ /\[(\d+) (.*?)\]/g) {
				$tok_cnt{$2} = $1;
				$old_tokens{$2} = 1;
				}

			while ($mapn =~ /\[(\d+) (.*?)\]/g) {
				my $tok = $2;
				$tok_cnt{$2} -= $1;
				if ($old_tokens{$tok}) {
					delete $old_tokens{$tok};
					}
				else {
					$incr++;
					}
				}

			if (scalar(keys %old_tokens)) {
				$decr = scalar(keys %old_tokens);
				}

			if ($config{terse} > 0) {
				$mapo =~ s/\[\d+ /[/g;
				$mapn =~ s/\[\d+ /[/g;
				next if $mapo eq $mapn;
				if ($config{terse} > 1) {
					$mapo = join("|", uniq(map { lc(fold($_, 1)) } ($mapo =~ /\[(.*?)\]/g)));
					$mapn = join("|", uniq(map { lc(fold($_, 1)) } ($mapn =~ /\[(.*?)\]/g)));
					next if $mapo eq $mapn;
					}
				}

			foreach my $tok (keys %tok_cnt) {
				if ($tok_cnt{$tok} < 0) {
					$incr ||= 1;
					}
				elsif ($tok_cnt{$tok} > 0) {
					$decr ||= 1;
					}
				}

			my $incr_decr = '';

			if ($incr && $decr) {
				$incr_decr = 'mixed';
				}
			elsif ($incr) {
				$incr_decr = 'increased';
				}
			else {
				$incr_decr = 'decreased';
				}

			push @{$old_v_new_results{$incr_decr}}, $final;
			$old_v_new_results{magnitude}{$final} = $incr + $decr;
			}
		}

	print_old_v_new_report();

	}

else { # new file only
	foreach my $final (sort keys %mapping) {
		my @terms = uniq(map {affix_fold($_)} $mapping{$final}{new} =~ /\[\d+? (.*?)\]/g);
		my $token_count = 0;
		my $final_len = length($final);

		foreach my $count (map {affix_fold($_)} $mapping{$final}{new} =~ /\[(\d+?) .*?\]/g) {
			$token_count += $count;
			$statistics{token_length}{$final_len} += $count;
			}

		$statistics{count_histogram}{scalar(@terms)}++;

		push @{$statistics{type_length}{$final_len}}, $final;

		my $common = '';

		if (1 < @terms) { # multiple terms
			my $pre = common_prefix(@terms);
			my $suf = common_suffix(@terms);

			if ($config{explore}) { # let's go looking for potential affixes
				if (length($pre) > 1) {
					my @items = @terms;
					@items = map { $_ =~ s/^$pre//; $_; } @items;
					count_alternations('gp', 'suf', @items);
					}
				if (length($suf) > 1) {
					my @items = @terms;
					@items = map { $_ =~ s/$suf$//; $_; } @items;
					count_alternations('gp', 'pre', @items);
					}

				my $num = scalar(@terms) - 1;
				foreach my $i (0 .. $num-1) {
					foreach my $j ($i+1 .. $num) {
						my @items = ($terms[$i], $terms[$j]);
						my $pre1 = common_prefix(@items);
						if (length($pre1) > 1) {
							@items = map { $_ =~ s/^$pre1//; $_; } @items;
							count_alternations('onebyone', 'suf', @items);
							}
						@items = ($terms[$i], $terms[$j]);
						my $suf1 = common_suffix(@items);
						if (length($suf1) > 1) {
							@items = map { $_ =~ s/$suf1$//; $_; } @items;
							count_alternations('onebyone', 'pre', @items);
							}
						}
					}
				}

			if ($pre eq $suf && ($pre eq $terms[0])) {
				$common = "+";
				}
			else {
				$common = "$pre .. $suf";
				if (!$pre && !$suf) {
					if ($config{lang}) {
						my $prefix = $language_data{strippable_prefix_regex};
						my $suffix = $language_data{strippable_suffix_regex};
						@terms = map { $_ =~ s/^($prefix)//; $_; } @terms;
						@terms = map { $_ =~ s/($suffix)$//; $_; } @terms;
						$pre = common_prefix(@terms);
						$suf = common_suffix(@terms);
						$common = "$pre :: $suf";
						}
					if (!$pre && !$suf) {
						@terms = map { $_ = fold($_, 1) } @terms;
						$pre = common_prefix(@terms);
						$suf = common_suffix(@terms);
						$common = "$pre -- $suf";
						}
					}
				}
			}

		if (1 < @terms || $config{singletons}) {
			push @stemming_results, [ $final, $token_count, $common, scalar(@terms) ];
			}
		}

	print_new_report();

	}

exit;

sub common_suffix {
	my @terms = @_;
	my $common = shift @terms;
	foreach my $s (@terms) {
		while ($s !~ /\Q$common\E$/) {
			$common = substr $common, 1;
			}
		}
	return $common;
	}

sub common_prefix {
	my @terms = @_;
	my $common = shift @terms;
	foreach my $s (@terms) {
		while ($s !~ /^\Q$common\E/) {
			chop $common;
			}
		}
	return $common;
	}

###############
# Show usage
#
sub usage {
print <<"USAGE";
usage: $0 -n <new_file> [-o <old_file>] [-d <dir>] [-l <lang,lang,...>]
    [-x] [-1] [-h] [-f] [-s <#>] [-t <#>]

    -n <file>  "new" counts file
    -d <dir>   specify the dir for language data config; default: compare_counts/langdata/
    -l <lang>  specify one or more language configs to load.
               See compare_counts/langdata/example.txt for config details
    -h         generate HTML output instead of text output

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
USAGE
	return;
	}

###############
# Set up language-specific info on expected affix alternation; gather
# data from each file, then create affix data structure
#
sub lang_specific_setup {
	my @strip_pref = ();
	my @strip_suff = ();
	my %regular_suffixes = ();
	my %regular_prefixes = ();
	$language_data{fold}{maxlen} ||= 0;

	if ($config{lang}{'-default'}) {
		delete $config{lang}{'-default'};
		}
	else {
		$config{lang}{'default'} = 1;
		}
	my @langlist = keys %{$config{lang}};

	foreach my $language (@langlist) {
		open(my $FILE, "<:encoding(UTF-8)", $config{data_directory} . "/$language.txt");
		while (<$FILE>) {
			chomp;
			if (/^\s*#/ | /^\s*$/) {
				next;
				}
			my ($type, @data) = split(/\t/);
			if ($type eq 'regular_suffixes') {
				pairwise_cross(\%regular_suffixes, @data);
				}
			elsif ($type eq 'regular_prefixes') {
				pairwise_cross(\%regular_prefixes, @data);
				}
			elsif ($type eq 'strip_prefixes') {
				push @strip_pref, @data;
				}
			elsif ($type eq 'strip_suffixes') {
				push @strip_suff, @data;
				}
			elsif ($type eq 'fold') {
				my ($from, $to) = @data;
				if (!defined $to) {
					$to = '';
					}
				$language_data{fold}{strings}{$from} = $to;
				my $len = length($from);
				if ($len > $language_data{fold}{maxlen}) {
					$language_data{fold}{maxlen} = $len;
					}
				}
			}
		close FILE;
		}

	$language_data{strippable_prefix_regex} = join("|", @strip_pref);
	$language_data{strippable_suffix_regex} = join("|", @strip_suff);

	if (%regular_suffixes) {
		# convert hash to array
		foreach my $suffs (keys %regular_suffixes) {
			my @bits = split(/\|/, $suffs);
			push @{$language_data{regular_suffixes_array}}, \@bits;
			}
		@{$language_data{regular_suffixes_array}} =
			sort { $a->[0] cmp $b->[0] || $a->[1] cmp $b->[1] } @{$language_data{regular_suffixes_array}};

		%{$language_data{regular_suffixes_hash}} = %regular_suffixes;
		}

	if (%regular_prefixes) {
		# convert hash to array
		foreach my $prefs (keys %regular_prefixes) {
			my @bits = split(/\|/, $prefs);
			push @{$language_data{regular_prefixes_array}}, \@bits;
			}
		@{$language_data{regular_prefixes_array}} =
			sort { $a->[0] cmp $b->[0] || $a->[1] cmp $b->[1] } @{$language_data{regular_prefixes_array}};

		%{$language_data{regular_prefixes_hash}} = %regular_prefixes;
		}

	return;
	}

###############
# process token count file
#
sub process_token_count_file {
	my ($filename, $cat) = @_;
	my $ready = 0;
	my $final;
	my $orig;

	open(my $FILE, "<:encoding(UTF-8)", $filename);
	while (<$FILE>) {
		if (/original tokens mapped to final tokens/) {
			$ready = 1;
			next;
			}
		if (/final tokens mapped to original tokens/) {
			$ready = 2;
			next;
			}
		if (!$ready) {
			next;
			}
		chomp;
		if ($ready == 1) {
			if (/^\t/) {
				# final tokens
				my ($empty, $cnt, $tokens) = split(/\t/);
				my $token_cnt = scalar(split(/\|/, $tokens));
				push @{$statistics{token_cnt}{$cat}[$token_cnt]}, $orig unless $old_file;
				}
			else {
				$orig = $_;
				}
			}
		else {
			if (/^\t/) {
				# original tokens
				my ($empty, $cnt, $orig) = split(/\t/);
				count_tokens($orig, $final, $cnt, $cat);
				$statistics{type_count}{orig}{$cat}++;
				$statistics{total_tokens}{$cat} += $cnt;
				}
			else {
				# final tokens
				$final = $_;
				$statistics{type_count}{final}{$cat}++;
				}
			}
		}
	close FILE;
	return;
	}

###############
# gather stats on types and tokens
#
sub count_tokens {
	my ($o, $f, $cnt, $cat) = @_;
	$statistics{token_exists}{original}{$o}{$cat} = $cnt;
	$statistics{token_exists}{final}{$f}{$cat} = $cnt;
	if ($o eq $f) {
		$statistics{token_count}{$cat}{unchanged}{token} += $cnt;
		$statistics{token_count}{$cat}{unchanged}{type}++;
		if ($o =~ /^\d+$/) {
			$statistics{token_count}{$cat}{number}{token} += $cnt;
			$statistics{token_count}{$cat}{number}{type}++;
			}
		}
	if (lc($o) eq lc($f)) {
		$statistics{token_count}{$cat}{lc_unchanged}{token} += $cnt;
		$statistics{token_count}{$cat}{lc_unchanged}{type}++;
		}
	$mapping{$f}{$cat} .= "[$cnt $o]";
	return;
	}

###############
# generate all possible pairs from the uniq'd list of items, except
# self-cross, and increment counts in provided hash ref
#
sub pairwise_cross {
	my ($href, @items) = @_;
	@items = uniq(@items);
	my $num = scalar(@items) - 1;
	foreach my $i (0 .. $num-1) {
		foreach my $j ($i+1 .. $num) {
			my ($a, $b) = sort ($items[$i], $items[$j]);
			$href->{"$a|$b"}++ unless $a eq $b;
			}
		}
	return;
	}

###############
# track all the affix alternations found
#
sub count_alternations {
	my ($group, $affix, @items) = @_;
	pairwise_cross(\%{$common_affixes{$group}{$affix}}, @items);
	pairwise_cross(\%{$common_affixes{tot}{$affix}}, @items);
	return;
	}

###############
# remove hyphens
#
sub dehyphenate {
	my ($term) = @_;
	$term =~ s/­//g;  # hyphen
	$term =~ s/­//g;  # soft hyphen
	$term =~ s/–//g;  # en dash
	$term =~ s/—//g;  # em dash
	return $term;
	}

###############
# remove spaces
#
sub despace {
	my ($term) = @_;
	$term =~ s/ //g;   # normal space
	$term =~ s/　//g;  # ideographic space U+3000
	$term =~ s/﻿//g;   # zero-width non-breaking space U+FEFF
	return $term;
	}

###############
# extremely light folding for normalizing affixes:
#
# normalize common apostrophe-like characters and strip combining acute
# originally for Ukrainian; may need to be refactored as language-specific
#
sub affix_fold {
	my ($item) = @_;
	$item = lc($item);
	$item =~ s/́//g;
	$item =~ s/[’ʼ＇]/'/g;
	return $item;
	}

###############
# do basic ascii/unicode folding, including language specific folding;
# can specify force to override global config setting
#
sub fold {
	my ($term, $force) = @_;
	if (!$config{fold} && !$force) {
		return $term;
		}

	# rather than run all foldings on each word (there can be thousands),
	# look for substrings of appropriate length and see if they have
	# folding mappings. More than 10x faster for Chinese T2S, for example.

	if ($language_data{fold}{strings}) {
		my $maxlen = $language_data{fold}{maxlen};
		my $termlen = length($term);
		if ($termlen < $maxlen) {
			$maxlen = $termlen;
			}
		# match all longer substrings first
		while ($maxlen) {
			for ( my $i = 0 ; $i < $termlen - $maxlen + 1 ; $i++ ) {
				my $from = substr($term, $i, $maxlen);
				my $to = $language_data{fold}{strings}{$from};
				if (defined $to) {
					my $oterm = $term;
					$term =~ s/$from/$to/g;
					# account for differences in string
					# length after substitution, if any
					$i -= length($from) - length($to);
					# account for multiple substitutions
					$termlen -= length($oterm) - length($term);
					}
				}
			$maxlen--;
			}
		}

	return $term;
	}

###############
# generate final report for old vs new analysis, HTML or text, according to
# HTML config
#
sub print_old_v_new_report {

	# set up HTML vs non-HTML values
	my $HTML = $config{HTML};

	print $HTMLmeta if $HTML;

	# config info header
	print $bold_open, "Processing $old_file as \'old\'.", $bold_close, $cr;
	print $bold_open, "Processing $new_file as \'new\'.", $bold_close, $cr;
	if (0 < keys %{$config{lang}}) {
		print $bold_open, "Language processing: ", $bold_close,
			join(", ", sort keys %{$config{lang}}), $cr;
		}
	print $cr;
	print $bold_open, "Total old tokens: ", $bold_close, comma($statistics{total_tokens}{old}), $cr;
	print $bold_open, "Total new tokens: ", $bold_close, comma($statistics{total_tokens}{new}), $cr;
	my $tok_delta = $statistics{total_tokens}{new} - $statistics{total_tokens}{old};
	print $indent, $bold_open, "Token delta: ", $bold_close, comma($tok_delta), " (",
		percentify($tok_delta/$statistics{total_tokens}{old}), ")", $cr;

	# HTML navigation links
	if ($HTML) {
		my $new_split_stats = $old_v_new_results{splits}{post_type} ?
			"$indent<a href='#new_split_stats'>New Split Stats</a><br>" : "";
		my $token_count_increases = $old_v_new_results{gains}{post_type} ?
			"$indent<a href='#token_count_increases'>Token Count Increases</a><br>" : "";
		my $token_count_decreases = $old_v_new_results{losses}{post_type} ?
			"$indent<a href='#token_count_decreases'>Token Count Decreases</a><br>" : "";
		my $empty_token_inputs = ($mapping{''}) ?
			"<a href='#empty_token_inputs'>Empty Token Inputs</a><br>" : "";
		print <<"HTML";
<br>
<a name='TOC'><h3>Table of Contents</h3>
<a href='#PPTTS'>Pre/Post Type & Token Stats</a><br>
$empty_token_inputs
<a href='#new_collision_stats'>New Collision Stats</a><br>
$new_split_stats
$token_count_increases
$token_count_decreases
$indent<a href='#new_collision_near_match_stats'>New Collision Near Match Stats</a><br>
<a href='#lost_and_found'>Lost and Found Tokens</a><br>
<a href='#changed_collisions'>Changed Groups</a><br>
HTML

		my $spacer = 0;
		if ($old_v_new_results{decreased}) {
			print "$indent<a href='#changed_collisions_decreased'>Net Losses</a><br>";
			$spacer = 1;
			}
		if ($old_v_new_results{mixed}) {
			print "$indent<a href='#changed_collisions_mixed'>Mixed</a><br>";
			$spacer = 1;
			}
		if ($old_v_new_results{decreased}) {
			print "$indent<a href='#changed_collisions_increased'>Net Gains</a><br>";
			$spacer = 1;
			}

		if ($old_v_new_results{bad_collisions}) {
			if ($spacer) { print "<br>\n"; $spacer = 0; }
			print "$indent<a href='#bad_collisions_q'>Bad Collisions?</a><br>";
			}
		if ($old_v_new_results{bad_splits}) {
			if ($spacer) { print "<br>\n"; $spacer = 0; }
			print "$indent<a href='#bad_splits_q'>Bad Splits?</a><br>";
			}

		} # if HTML

	print_section_head('Pre/Post Type & Token Stats', 'PPTTS');

	foreach my $tag ('old', 'new') {
		print $bold_open, "\n\u$tag File Info", $bold_close, $cr;
		print $indent, ' pre-analysis types: ', comma($statistics{type_count}{orig}{$tag}), $cr;
		print $indent, 'post-analysis types: ', comma($statistics{type_count}{final}{$tag}), $cr;
		print $cr;
		my @types = ('type', 'token');
		print_table_head(@types, 'change_type');
		foreach my $change ('unchanged', 'lc_unchanged', 'number') {
			print_table_row([(map { comma($statistics{token_count}{$tag}{$change}{$_}); } @types), $change]);
			}
		print_table_foot();
		print $cr;
		}

	print_table_key ('Key', '',
		'Categories overlap. Numbers are usually unchanged, and all lc_unchanged are also unchanged.',
		'unchanged', 'pre-analysis token is the same as post-analysis token',
		'lc_unchanged', "pre-analysis token is the same as post-analysis$ws_wrap token after lowercasing",
		'number', 'pre-analysis token is all numerical digits'
		);

	if ($mapping{''}) {
		print_section_head('Empty Token Inputs', 'empty_token_inputs');

		foreach my $tag ('old', 'new') {
			if ($mapping{''}{$tag}) {
				print $indent, $bold_open, "\u$tag empty token inputs: ", $bold_close, $mapping{''}{$tag}, $cr;
				}
			}
		}

	{ # block to limit scope of temporary variables
		print_section_head('New Collision Stats', 'new_collision_stats');
		my $post = $old_v_new_results{collision}{post_type} || 0;
		my $pre_new = $old_v_new_results{collision}{pre_type_new} || 0;
		my $pre_tot = $old_v_new_results{collision}{pre_type_total} || 0;
		my $tok = $old_v_new_results{collision}{token} || 0;
		my $type_old = $statistics{type_count}{final}{old};
		my $pre_old = $statistics{type_count}{orig}{old};
		my $tok_old = $statistics{total_tokens}{old};

		my $post_pct = percentify($post/$type_old);
		my $pre_new_pct = percentify($pre_new/$pre_old);
		my $pre_tot_pct = percentify($pre_tot/$pre_old);
		my $tok_pct = percentify($tok/$tok_old);

		$post = comma($post);
		$pre_new = comma($pre_new);
		$pre_tot = comma($pre_tot);
		$tok = comma($tok);

		print "New collisions: $post ($post_pct of post-analysis types)", $cr;
		print $indent, "added types: $pre_new ($pre_new_pct of pre-analysis types)", $cr if $pre_new;
		print $indent, "added tokens: $tok ($tok_pct of tokens)", $cr if $tok;
		print $indent, "total types in collisions: $pre_tot ($pre_tot_pct of pre-analysis types)", $cr if $pre_tot;
		print $cr;
		print "Narrative: $pre_new pre-analysis types ($pre_new_pct of pre-analysis types) / $tok tokens ($tok_pct of tokens) were added to $post groups ($post_pct of post-analysis types), affecting a total of $pre_tot pre-analysis types ($pre_tot_pct of pre-analysis types) in those groups.", $cr, $cr if $post;
		print 'Note: All percentages are relative to old token/type counts.', $cr;
		}

	if ($old_v_new_results{splits}{post_type}) {
		print_section_head('New Split Stats', 'new_split_stats');
		my $post = $old_v_new_results{splits}{post_type} || 0;
		my $pre_new = $old_v_new_results{splits}{pre_type_new} || 0;
		my $pre_tot = $old_v_new_results{splits}{pre_type_total} || 0;
		my $tok = $old_v_new_results{splits}{token} || 0;
		my $type_old = $statistics{type_count}{final}{old};
		my $pre_old = $statistics{type_count}{orig}{old};
		my $tok_old = $statistics{total_tokens}{old};

		my $post_pct = percentify($post/$type_old);
		my $pre_new_pct = percentify($pre_new/$pre_old);
		my $pre_tot_pct = percentify($pre_tot/$pre_old);
		my $tok_pct = percentify($tok/$tok_old);

		$post = comma($post);
		$pre_new = comma($pre_new);
		$pre_tot = comma($pre_tot);
		$tok = comma($tok);

		print "New splits: $post ($post_pct of post-analysis types)", $cr;
		print $indent, "lost types: $pre_new ($pre_new_pct of pre-analysis types)", $cr if $pre_new;
		print $indent, "lost tokens: $tok ($tok_pct of tokens)", $cr if $tok;
		print $indent, "total types in splits: $pre_tot ($pre_tot_pct of pre-analysis types)", $cr if $pre_tot;
		print $cr;
		print "Narrative: $pre_new pre-analysis types ($pre_new_pct of pre-analysis types) / $tok tokens ($tok_pct of tokens) were lost from $post groups ($post_pct of post-analysis types), affecting a total of $pre_tot pre-analysis types ($pre_tot_pct of pre-analysis types) in those groups.", $cr, $cr;
		print 'Note: All percentages are relative to old token/type counts.', $cr;
		}

	if ($old_v_new_results{gains}{post_type}) {
		print_section_head('Token Count Increases', 'token_count_increases');
		my $post = $old_v_new_results{gains}{post_type} || 0;
		my $pre = $old_v_new_results{gains}{pre_type} || 0;
		my $tok = $old_v_new_results{gains}{token} || 0;
		my $type_old = $statistics{type_count}{final}{old};
		my $pre_old = $statistics{type_count}{orig}{old};
		my $tok_old = $statistics{total_tokens}{old};

		my $post_pct = percentify($post/$type_old);
		my $pre_pct = percentify($pre/$pre_old);
		my $tok_pct = percentify($tok/$tok_old);

		$post = comma($post);
		$pre = comma($pre);
		$tok = comma($tok);

		print "Gains: $post ($post_pct of post-analysis types)", $cr;
		print $indent, "types with gains: $pre ($pre_pct of pre-analysis types)", $cr if $pre;
		print $indent, "tokens gained: $tok ($tok_pct of tokens)", $cr if $tok;
		print $cr;
		print "Narrative: $pre pre-analysis types ($pre_pct of pre-analysis types) gained $tok tokens ($tok_pct of tokens) across $post groups ($post_pct of post-analysis types).", $cr, $cr;
		print 'Note: All percentages are relative to old token/type counts.', $cr;
		}

	if ($old_v_new_results{losses}{post_type}) {
		print_section_head('Token Count Decreases', 'token_count_decreases');
		my $post = $old_v_new_results{losses}{post_type} || 0;
		my $pre = $old_v_new_results{losses}{pre_type} || 0;
		my $tok = $old_v_new_results{losses}{token} || 0;
		my $type_old = $statistics{type_count}{final}{old};
		my $pre_old = $statistics{type_count}{orig}{old};
		my $tok_old = $statistics{total_tokens}{old};

		my $post_pct = percentify($post/$type_old);
		my $pre_pct = percentify($pre/$pre_old);
		my $tok_pct = percentify($tok/$tok_old);

		$post = comma($post);
		$pre = comma($pre);
		$tok = comma($tok);

		print "Losses: $post ($post_pct of post-analysis types)", $cr;
		print $indent, "types with losses: $pre ($pre_pct of pre-analysis types)", $cr if $pre;
		print $indent, "tokens lost: $tok ($tok_pct of tokens)", $cr if $tok;
		print $cr;
		print "Narrative: $pre pre-analysis types ($pre_pct of pre-analysis types) lost $tok tokens ($tok_pct of tokens) across $post groups ($post_pct of post-analysis types).", $cr, $cr;
		print 'Note: All percentages are relative to old token/type counts.', $cr;
		}

	print_section_head('New Collision Near Match Stats', 'new_collision_near_match_stats');
	my @types = ('type', 'token');
	print_table_head(@types, 'kind');
	foreach my $kind (sort keys %{$old_v_new_results{collision}{near_match}}) {
		print_table_row([(map { comma($old_v_new_results{collision}{near_match}{$kind}{$_}); } @types), $kind]);
		}
	print_table_foot();
	print $cr;

	print_table_key ('Key', 'New collision type is a near match for a type already in the group after...',
		'Categories do not overlap. Types are post-analysis types',
		'folded', "applying generic and language-specific character folding,$ws_wrap de-spacing, and de-hyphenation",
		'regulars', 'removing language-specific regular prefixes and suffixes',
		'folded_regulars', "applying generic and language-specific character$ws_wrap folding, de-spacing, de-hyphenation, and removing language-specific$ws_wrap regular prefixes and suffixes"
		);

	print_section_head('Lost and Found Tokens', 'lost_and_found');
	my %tot = ();
	my %only = ();

	foreach my $orig_final ('original', 'final') {
		my $pre_post = $orig_final eq 'original' ? 'pre' : 'post';

		foreach my $token (keys %{$statistics{token_exists}{$orig_final}}) {
			my $ocnt = $statistics{token_exists}{$orig_final}{$token}{old};
			my $ncnt = $statistics{token_exists}{$orig_final}{$token}{new};
			next if ($ocnt && $ncnt);
			my $type = token_category($token);
			if ($ocnt) {
				$tot{$orig_final}{lost}++;
				$tot{$orig_final}{lost_token} += $ocnt;
				push @{$only{$orig_final}{old}{$type}}, $token;
				}
			else {
				$tot{$orig_final}{found}++;
				$tot{$orig_final}{found_token} += $ncnt;
				push @{$only{$orig_final}{new}{$type}}, $token;
				}
			}

		if ($tot{$orig_final}{lost} || $tot{$orig_final}{found}) {
			$tot{$orig_final}{lost} ||= 0;
			$tot{$orig_final}{found} ||= 0;
			$tot{$orig_final}{lost_token} ||= 0;
			$tot{$orig_final}{found_token} ||= 0;
			print $cr;
			print " Lost $pre_post-analysis types/tokens (old only): ", comma($tot{$orig_final}{lost}),
				" / ", comma($tot{$orig_final}{lost_token}), $cr;;
			print "Found $pre_post-analysis types/tokens (new only): ", comma($tot{$orig_final}{found}),
				" / ", comma($tot{$orig_final}{found_token}), $cr;
			print $cr;
			}

		my $need_div = $tot{$orig_final}{lost} && $tot{$orig_final}{found} && $config{HTML};

		if ($tot{$orig_final}{lost}) {
			if ($need_div) {
				print "<div style='width:45%; border:1px solid grey; float:left; padding:0.5em; word-wrap: break-word; vertical-align: top;'>\n";
				}
			print_lost_found_token_stats('Lost', $orig_final, 'old', \%only);
			if ($need_div) {
				print "</div>\n";
				}
			}

		if ($tot{$orig_final}{found}) {
			if ($need_div) {
				print "<div style='width:45%; border:1px solid grey; float:right; padding:0.5em; word-wrap: break-word; vertical-align: top;'>\n";
				}
			print_lost_found_token_stats('Found', $orig_final, 'new', \%only);
			if ($need_div) {
				print "</div><br clear=all>\n";
				}
			}

	}

	print_section_head('Changed Groups', 'changed_collisions');

	print_table_key ('', '', '',
		'<<', 'indicates net loss of types/tokens',
		'><', 'indicates mixed gains and losses of types/tokens',
		'>>', 'indicates net gain of types/tokens',
		'#', 'the number following indicates the magnitude of the change (#types affected)',
		'terseness', $config{terse}
		);

	print $cr;

	print_changed_collisions('Net Losses', 'decreased', '<<');
	print_changed_collisions('Mixed', 'mixed', '><');
	print_changed_collisions('Net Gains', 'increased', '>>');


	if ($old_v_new_results{bad_collisions}) {
		print_section_head('Bad Collisions?', 'bad_collisions_q');
		print $indent, scalar(@{$old_v_new_results{bad_collisions}}),
			" collisions vs mininmum stem length: ", $config{min_stem_len}, $cr, $cr;

		print_table_head('stemmed', 'added type -> group');
		foreach my $b (sort { lc($a->[0]) cmp lc($b->[0]) || $a->[0] cmp $b->[0] ||
				lc($a->[2]) cmp lc($b->[2]) || $a->[2] cmp $b->[2] }
				@{$old_v_new_results{bad_collisions}}) {
			my ($final, $cnt, $n) = @{$b};
			print_table_row([$final, colorSample("[$cnt $n] -> " . $mapping{$final}{old})]);
			}
		print_table_foot();
		print $cr;
		}

	if ($old_v_new_results{bad_splits}) {
		print_section_head('Bad Splits?', 'bad_splits_q');
		print $indent, scalar(@{$old_v_new_results{bad_splits}}), " splits", $cr, $cr;

		print_table_head('stemmed', 'removed type <- group');
		foreach my $b (sort { lc($a->[0]) cmp lc($b->[0]) || $a->[0] cmp $b->[0] ||
				lc($a->[2]) cmp lc($b->[2]) || $a->[2] cmp $b->[2] }
				@{$old_v_new_results{bad_splits}}) {
			my ($final, $cnt, $o) = @{$b};
			print_table_row([$final, colorSample("[$cnt $o] <- " . $mapping{$final}{new})]);
			}
		print_table_foot();
		print $cr;
		}

	return;
	}

###############
# generate final report for new-only analysis, HTML or text, according to
# HTML config
#
sub print_new_report {

	# set up HTML vs non-HTML values
	my $HTML = $config{HTML};

	print $HTMLmeta if $HTML;

	# config info header
	print $bold_open, "Processing $new_file as \'new\'.", $bold_close, $cr;
	print $cr;
	print $bold_open, "Total new tokens: ", $bold_close, comma($statistics{total_tokens}{new}), $cr;

	print $indent, $bold_open, 'pre-analysis types: ', $bold_close,
		comma($statistics{type_count}{orig}{new}), $cr;
	print $indent, $bold_open, 'post-analysis types: ', $bold_close,
		comma($statistics{type_count}{final}{new}), $cr;

	print $cr;
	if (0 < keys %{$config{lang}}) {
		print $bold_open, "Language processing: ", $bold_close,
			join(", ", sort keys %{$config{lang}}), $cr;
		}
	print $cr;

	# HTML navigation links
	if ($HTML) {
		print <<"HTML";
<a name='TOC'><h3>Table of Contents</h3>
<a href='#stemmingResults'>Stemming Results</a><br>
$indent<a href="#prob1">Potential Problem Stems</a><br>
HTML
		print <<"HTML" if $config{explore};
<a href='#commonPrefixes'>Common Prefix Alternations</a><br>
<a href='#commonSuffixes'>Common Suffix Alternations</a><br>
HTML
		print <<"HTML";
<a href='#typeCountHistogram'>Histogram of Case-Insensitive Type Group Counts</a><br>
<a href='#tokenCountHistogram'>Histogram of Stemmed Tokens Generated per Input Token</a><br>
<a href='#typeLengthHistogram'>Histogram of Final Type Lengths</a><br>
HTML
		} # if HTML

	# stemming results
	print_section_head("Stemming Results" .
		($config{singletons}?" (singletons)":" (groups only)"), "stemmingResults");

	# stemming results key
	print ".. indicates raw / lowercased string matches", $cr;
	print ":: indicates affix-stripped matches", $cr if $config{lang};
	print "-- indicates ", ($config{lang}?"affix-stripped and ":""), "folded matches", $cr;
	print $cr;

	# stemming results table
	my $prob_ref_cnt = 1;
	my %type_ref_cnt = ();
	print_table_head("stem", "common", "group total", "distinct types", "types (counts)");
	foreach my $aref (@stemming_results) {
		my ($final, $token_count, $common, $type_cnt) = @$aref;

		my $display_final = $final;
		my $display_type_cnt = $type_cnt;
		if ($HTML) {
			if ($common =~ /^ .. $/) {
				$display_final = "<a name='prob" . $prob_ref_cnt . "'><a href='#prob" .
					++$prob_ref_cnt . "'>" . $red_open . $final . $red_close . "</a>";
				$common = $red_open . "&nbsp;$common&nbsp;" . $red_close;
				}
			if ($type_cnt >= $min_histogram_link) {
				if (!$type_ref_cnt{$type_cnt}) {
					$type_ref_cnt{$type_cnt} = 1;
					}
				$display_type_cnt = "<a name='count$type_cnt." . $type_ref_cnt{$type_cnt} .
					"'><a href='#count$type_cnt." . ++$type_ref_cnt{$type_cnt} . "'>" .
					$red_open . $type_cnt . $red_close . "</a>";
				}
			}
		my $the_mapping = $mapping{$final}{new};
		if ($HTML) {
			# this prevents awkward breaks, esp in RTL languages that are confusing for non-RTL readers
			$the_mapping =~ s/ /&nbsp;/g;
			}
		print_table_row([$display_final, $common, $token_count, $display_type_cnt, $the_mapping]);
		}
	print_table_foot();
	if ($HTML) {
		print "<a name='prob" . $prob_ref_cnt ."'>\n";
		}

	# explore: show automatically generated affix candidates
	if ($config{explore}) {
		print_alternations("Common Prefix Alternations", "commonPrefixes", 'pre',
			$language_data{regular_prefixes_hash});
		print_alternations("Common Suffix Alternations", "commonSuffixes", 'suf',
			$language_data{regular_suffixes_hash});
		}

	# some stats
	print_section_head("Histogram of Case-Insensitive Type Group Counts", "typeCountHistogram");
	print_table_head("count", "freq");
	foreach my $cnt (sort {$a <=> $b} keys %{$statistics{count_histogram}}) {
		my $cnt_display = $cnt;
		if ($HTML && $cnt >= $min_histogram_link) {
			$cnt_display = "<a name='count$cnt." . $type_ref_cnt{$cnt} ."'><a href='#count$cnt.1'>$cnt</a>";
			}
		print_table_row([$cnt_display, $statistics{count_histogram}{$cnt}]);
		}
	print_table_foot();

	print_section_head("Histogram of Stemmed Tokens Generated per Input Token",
		"tokenCountHistogram");
	print_table_head("count", "freq", "example input tokens");
	my $aref = $statistics{token_cnt}{'new'};
	for my $i (0 .. scalar(@$aref)) {
		my $freq = $aref->[$i] ? scalar(@{$aref->[$i]}) : 0;
		if ($freq) {
			my @examples = ();
			if ($freq > $token_count_examples) {
				shuffle (\@{$aref->[$i]});
				@examples = @{$aref->[$i]}[0..$token_count_examples-1];
				}
			else {
				@examples = @{$aref->[$i]};
				}
			my $joiner = $HTML?" &nbsp; &bull; &nbsp; ":"\t";
			print_table_row([$i, $freq, join($joiner, sort @examples)]);
			}
		}
	print_table_foot();

	print_section_head("Histogram of Final Type Lengths", "typeLengthHistogram");
	print_table_head("length", "type freq", "token count", "examples");
	my $href = $statistics{type_length};
	foreach my $len (sort {$a <=> $b} keys %$href) {
		my $freq = scalar(@{$href->{$len}});
		if ($freq) {
			my @examples = ();
			if ($freq > $token_length_examples) {
				shuffle (\@{$href->{$len}});
				@examples = @{$href->{$len}}[0..$token_length_examples-1];
				}
			else {
				@examples = @{$href->{$len}};
				}
			my $joiner = $HTML?" &nbsp; &bull; &nbsp; ":"\t";
			print_table_row([$len, $freq, $statistics{token_length}{$len}, join($joiner, sort @examples)]);
			}
		}
	print_table_foot();

	return;
	}

###############
# print a section heading, along with internal anchor for HTML report
#
sub print_section_head {
	my ($header, $aname, $subhead) = @_;
	if ($config{HTML}) {
		my $head = $subhead?"h$subhead":'h3';
		print "\n<a name='$aname'><$head>$header <a href=#TOC style='font-size:60%'>[TOC]</a></$head>\n";
		}
	else {
		print "\n\n$header\n", "-" x length($header), "\n";
		}
	return;
	}

###############
# print the header for a table, HTML or text as needed
#
sub print_table_head {
	my @items = @_;
	my $table_pre = '';
	my $table_post = '';
	my $joiner = "\t";
	my $table_min = '';

	if ($config{HTML}) {
		$table_pre = "<table><tr><th>";
		$table_post = "</th></tr>";
		$joiner = '</th><th>';
		$table_min = "<table>\n";
		}

	if (@items) {
		print $table_pre, join($joiner, @items), $table_post, "\n";
		}
	else {
		print $table_min;
		}
	return;
	}

###############
# print a row of a table, HTML or text as needed
#
sub print_table_row {
	my ($aref, $class) = @_;
	my $row_pre = '';
	my $row_post = '';
	my $joiner = "\t";

	if ($config{HTML}) {
		$row_pre = "<tr><td>";
		if ($class) {
			$row_pre = "<tr class='$class'><td>";
			}
		$row_post = "</td></tr>";
		$joiner = '</td><td>';
		}

	if (scalar(@$aref)) {
		print $row_pre, join($joiner, map {defined $_ ? $_ : ''} @$aref), $row_post, "\n";
		}
	return;
	}

###############
# finish off the HTML table, if needed
#
sub print_table_foot {
	print "</table>\n" if $config{HTML};
	return;
	}

###############
# print a table key, as a table
#
sub print_table_key {
	my ($title, $header, $footer, @keys_and_values) = @_;

	my $HTML = $config{HTML};

	my $div_open = '';
	my $div_close = $cr;

	if ($HTML) {
		$div_open = '<div class=hang>';
		$div_close = '</div>';
		}

	print $bold_open, $title, $bold_close, $cr if $title;
	if ($header) {
		print $header, $cr;
		}
	while (@keys_and_values) {
		print $div_open, $indent, $bold_open, (shift @keys_and_values), ":", $bold_close,
			" ", (shift @keys_and_values), $div_close;
		}
	if ($footer) {
		print $footer, $cr;
		}
	return;
	}

###############
# print lost and found token stats
#
sub print_lost_found_token_stats {
	my ($lost_found, $orig_final, $oldnew, $only_ref) = @_;

	my $joiner = "\t";

	if ($config{HTML}) {
		$joiner = " &bull; ";
		}

	my $pre_post = $orig_final eq 'original' ? 'pre' : 'post';
	print $bold_open, "$lost_found $pre_post-analysis tokens by category", $bold_close, $cr, $cr;
	foreach my $category (sort keys %{$only_ref->{$orig_final}{$oldnew}}) {
		my $token_tot = 0;
		foreach my $item (@{$only_ref->{$orig_final}{$oldnew}{$category}}) {
			$token_tot += $statistics{token_exists}{$orig_final}{$item}{$oldnew};
			}
		my $type_tot = scalar(@{$only_ref->{$orig_final}{$oldnew}{$category}});
		print $indent, $italic_open, "$category:$italic_close ", comma($type_tot), " types, ",
			comma($token_tot), " tokens",
			($type_tot > $max_lost_found_sample)?" (sample of $max_lost_found_sample)":'', $cr;
		print $block_open;

		my $picks = $max_lost_found_sample;
		my $samples = scalar( @{$only_ref->{$orig_final}{$oldnew}{$category}});
		print join($joiner, sort
			grep { ($picks && rand() < $picks/$samples--)?$picks--:0 }
			@{$only_ref->{$orig_final}{$oldnew}{$category}}), $cr;

		my @hifreq = grep { $statistics{token_exists}{$orig_final}{$_}{$oldnew} >= $hi_freq_cutoff }
			@{$only_ref->{$orig_final}{$oldnew}{$category}};
		if (@hifreq) {
			print $cr;
			print $indent, $italic_open, "hi-freq tokens: ", $italic_close,
				join($joiner, map { "$_ | " . comma($statistics{token_exists}{$orig_final}{$_}{$oldnew}); }
				sort { $statistics{token_exists}{$orig_final}{$b}{$oldnew} <=>
				$statistics{token_exists}{$orig_final}{$a}{$oldnew}} @hifreq), $cr;
			}
		print $block_close;
		}

	return;
	}

###############
# Print the Changed Collision Net Gains and Net Losses
#
sub print_changed_collisions {
	my ($gain_loss, $incr_decr, $arr) = @_;

	if (!defined $old_v_new_results{$incr_decr}) {
		return;
		}

	my $div_open = '<div class=hang>';
	my $div_close = '</div>';

	print_section_head($gain_loss, "changed_collisions_" . $incr_decr, 4);

	my $hic = 1;
	if ($config{HTML}) {
		print "<a href='#hic_$incr_decr\_1'><b>High Impact Changes</b></a><br><br>\n";
		}

	print_table_head();
	foreach my $final (@{$old_v_new_results{$incr_decr}}) {
		# Ugh, this just doesn't want to abstract properly; Hack, hack, hack.
		if ($config{HTML}) {
			my $impact = $old_v_new_results{magnitude}{$final};
			my $hic_open = '';
			my $hic_close = '';
			if ($impact >= $hi_impact_cutoff) {
				$hic_open = "<a name='hic_$incr_decr\_$hic'><a href='#hic_$incr_decr\_" . ++$hic . "'>";
				$hic_close = '</a>';
				}
			print_table_row(["<nobr>$hic_open$final $arr $impact$hic_close</nobr>",
				$div_open . "o: " . colorSample($mapping{$final}{old}) . $div_close .
				$div_open . "n: " . colorSample($mapping{$final}{new}) . $div_close]);
			}
		else {
			print "$final $arr $old_v_new_results{magnitude}{$final}", $cr,
				$indent, "o: $mapping{$final}{old}", $cr,
				$indent, "n: $mapping{$final}{new}", $cr;
			}
		}
	print_table_foot();

	if ($config{HTML}) {
		print "<a name='hic_$incr_decr\_$hic'>\n";
		}

	print $cr;
	return;
	}

###############
# add bolding and color (blue by default) to samples "[### token]" where
# the number is a certain number of digits (4 by default)
#
# - will apply incorrectly if "token" contains a close baracket ]
#
sub colorSample {
	my ($str, $digits, $color) = @_;
	$digits ||= 4;
	$color ||= 'blue';
	$str =~ s!(\[[0-9]{$digits}[^\]]+\])!<b style='color:$color'>$1</b>!g;
	return $str;
	}

###############
# print alternations table for affix with give title
# provide anchor for HTML report
#
sub print_alternations {
	my ($title, $aname, $affix, $known_pairs) = @_;

	my $tot_href = \%{$common_affixes{tot}{$affix}};
	my $oneby_href = \%{$common_affixes{onebyone}{$affix}};
	my $group_href = \%{$common_affixes{gp}{$affix}};

	print_section_head($title, $aname);

	my @headings = ("1x1 count", "group count", "alt 1", "alt 2");
	if ($known_pairs) {
		push @headings, "known";
		}
	print_table_head(@headings);

	my $cnt = 0;
	foreach my $item (sort { $tot_href->{$b} <=> $tot_href->{$a} || $a cmp $b } keys %{$tot_href}) {
		last if ($tot_href->{$item} < $min_alternation_freq);
		my ($a, $b, $z) = split(/\|/, $item);
		my @row_data = ($oneby_href->{$item} || '', $group_href->{$item} || '', $a, $b);
		my $known = '';
		my $red = 'red';
		if ($known_pairs) {
			$known = $known_pairs->{join("|", sort ($a, $b))} ? '*' : '';
			push @row_data, $known;
			}
		else {
			$red = ''; # if nothing is known, no point marking everything as unknown
			}
		print_table_row(\@row_data, ($known ? '' : $red));
		last if (++$cnt >= 250);
		}

	print_table_foot();
	return;
	}

###############
# Determine likely token category based on characters in the token
#
sub token_category {
	my ($token) = @_;
	my $category = ' other';
	my $modifier = '';

	if ($token =~ s/\x{FEFF}|\x{00A0}//g) {
		$modifier .= '+nbsp';
		}
	if ($token =~ s/\x{200B}//g) {
		$modifier .= '+zwsp';
		}
	if ($token =~ s/\x{200C}//g) {
		$modifier .= '+zwnj';
		}
	if ($token =~ s/\x{200D}//g) {
		$modifier .= '+zwj';
		}
	if ($token =~ s/\x{200E}|\x{200F}|\x{202A}|\x{202B}|\x{202C}|\x{202D}|\x{202E}|\x{2066}|\x{2067}|\x{2068}|\x{2069}|\x{061C}//g) {
		$modifier .= '+bidi';
		}
	if ($token =~ s/\x{00AD}//g) {
		$modifier .= '+shy';
		}
	if ($token =~ s/\p{Block: Combining_Diacritical_Marks}//g) {
		$modifier .= '+comb';
		}
	if ($token =~ s/\p{Block: Modifier_Letters}//g) {
		$modifier .= '+mod';
		}
	if ($token =~ s/\$$//g) {
		$modifier .= '+$';
		}
	if ($token =~ s/ //g) {
		$modifier .= '+sp';
		}
	if ($token =~ s/\t//g) {
		$modifier .= '+tab';
		}
	if ($token =~ s/\n//g) {
		$modifier .= '+cr';
		}

	my $num_pat = '(\d+([.,]\d\d\d)*([.,]\d+)?)';
	my $unit_pat = '([ap]\.?m|[AP]\.?M|°|°C|°F|a|b|B|C|cm|d|eV|F|fps|g|GB|GHz|h|Hz|k|K|kbit|keV|kg|kgm|kJ|km|Km|km2|L|lb|m|M|m2|Ma|MeV|mg|MHz|MHZ|ml|mm|mol|mph|º|ºC|ºF|Pa|ppm|rpm|s|T|Ts|W|x)';

	if ($token eq '') { $category = 'empty'; }
	elsif ($token =~ /^([A-Z]\.)+[A-Z]\.?$/) { $category = 'acronyms'; }
	elsif ($token =~ /^\p{Punctuation}+$/i) { $category = 'Punctuation'; }
	elsif ($token =~ /^([A-Z]\.)+[A-Z]\.?$/i) { $category = 'acronym-like'; }
	elsif ($token =~ /^([A-Z]\.){1,3}[A-Z]\p{Latin}+$/) { $category = 'name-like'; }
	elsif ($token =~ /^www\.(\S+\.)+\S{2,3}$/i) { $category = 'web domains'; }
	elsif ($token =~ /^(\S+\.)+(com|org|co\.uk|edu|gov|net|de|info)$/i) { $category = 'web domains'; }
	elsif ($token =~ /^[+-]?\d+$/) { $category = 'numbers, integers'; }
	elsif ($token =~ /^[+-]?\d+\.\d+$/) { $category = 'numbers, decimals'; }
	elsif ($token =~ /^[+-]?\d{1,3}\,(\d\d\d,)*\d\d\d(\.\d+)?$/) { $category = 'numbers, with commas'; }
	elsif ($token =~ /^\d+(,\d+)+$/) { $category = 'numbers lists, comma-sep'; }
	elsif ($token =~ /^[+-]?\d+(\.\d+)+$/) { $category = 'numbers, period-sep'; }
	elsif ($token =~ /^\d*(1st|2nd|3rd|\dth)$/i) { $category = 'numbers, ordinals'; }
	elsif ($token =~ /^[A-Z0-9-]+$/ && $token =~ /[A-Z]/ && $token =~ /[0-9]/) { $category = 'ID-like'; }
	elsif ($token =~ /\p{IPA_Extensions}|\p{Phonetic_Ext}|\p{Phonetic_Ext_Sup}/i) { $category = 'IPA-ish'; }

	elsif ($token =~ /^[a-z'’-]+(\.[a-z'’-]+)+$/i) { $category = 'words, period-sep'; }
	elsif ($token =~ /^[a-z'’-]+(\:[a-z'’-]+)+$/i) { $category = 'words, colon-sep'; }
	elsif ($token =~ /^[a-z'’-]+(\,[a-z'’-]+)+$/i) { $category = 'words, comma-sep'; }

	elsif ($token =~ /^[a-z'’-]+$/i) { $category = 'Latin (Basic)'; }
	elsif ($token =~ /^([a-z'’-]|\p{Latin})+$/i) { $category = 'Latin (Extended)'; }
	elsif ($token =~ /^([́']|\p{Cyrillic})+$/i) { $category = 'Cyrillic'; }
	elsif ($token =~ /^(\\u[0-9A-F]{4})+$/i) { $category = 'Unicode'; }
	elsif ($token =~ /^\p{Greek}+$/i) { $category = 'Greek'; }
	elsif ($token =~ /^(\p{Block: Arabic}|\p{Arabic_Ext_A}|\p{Arabic_Supplement}|\x{200E})+$/i) { $category = 'Arabic'; }
	elsif ($token =~ /^\p{Armenian}+$/i) { $category = 'Armenian'; }
	elsif ($token =~ /^\p{Bopomofo}+$/i) { $category = 'Bopomofo'; }
	elsif ($token =~ /^\p{Bengali}+$/i) { $category = 'Bengali'; }
	elsif ($token =~ /^\p{Devanagari}+$/i) { $category = 'Devanagari'; }
	elsif ($token =~ /^\p{Ethiopic}+$/i) { $category = 'Ethiopic'; }
	elsif ($token =~ /^\p{Georgian}+$/i) { $category = 'Georgian'; }
	elsif ($token =~ /^\p{Gothic}+$/i) { $category = 'Gothic'; }
	elsif ($token =~ /^\p{Gujarati}+$/i) { $category = 'Gujarati'; }
	elsif ($token =~ /^\p{Hangul}+$/i) { $category = 'Hangul'; }
	elsif ($token =~ /^(\p{Hebrew}|[ְָֹּ‎]|["'.])+$/i) { $category = 'Hebrew'; }
	elsif ($token =~ /^(ー|\p{Hiragana})+$/i) { $category = 'Hiragana'; }
	elsif ($token =~ /^\p{Javanese}+$/i) { $category = 'Javanese'; }
	elsif ($token =~ /^\p{Kannada}+$/i) { $category = 'Kannada'; }
	elsif ($token =~ /^(ー|\p{Katakana})+$/i) { $category = 'Katakana'; }
	elsif ($token =~ /^\p{Khmer}+$/i) { $category = 'Khmer'; }
	elsif ($token =~ /^\p{Malayalam}+$/i) { $category = 'Malayalam'; }
	elsif ($token =~ /^\p{Mongolian}+$/i) { $category = 'Mongolian'; }
	elsif ($token =~ /^\p{Myanmar}+$/i) { $category = 'Myanmar'; }
	elsif ($token =~ /^\p{Ogham}+$/i) { $category = 'Ogham'; }
	elsif ($token =~ /^\p{Oriya}+$/i) { $category = 'Oriya'; }
	elsif ($token =~ /^\p{Runic}+$/i) { $category = 'Runic'; }
	elsif ($token =~ /^\p{Sinhala}+$/i) { $category = 'Sinhala'; }
	elsif ($token =~ /^\p{Sundanese}+$/i) { $category = 'Sundanese'; }
	elsif ($token =~ /^\p{Tagalog}+$/i) { $category = 'Tagalog'; }
	elsif ($token =~ /^\p{Tamil}+$/i) { $category = 'Tamil'; }
	elsif ($token =~ /^\p{Telugu}+$/i) { $category = 'Telugu'; }
	elsif ($token =~ /^\p{Thaana}+$/i) { $category = 'Thaana'; }
	elsif ($token =~ /^\p{Thai}+$/i) { $category = 'Thai'; }
	elsif ($token =~ /^\p{Tibetan}+$/i) { $category = 'Tibetan'; }
	elsif ($token =~ /^\p{Ugaritic}+$/i) { $category = 'Ugaritic'; }
	elsif ($token =~ /^\p{Unified_Canadian_Aboriginal_Syllabics}+$/i) { $category = 'Canadian Syllabics'; }
	elsif ($token =~ /^\p{Ideographic}+$/i) { $category = 'Ideographic'; }
	elsif ($token =~ /^$num_pat$unit_pat$/) { $category = 'measurements'; }
	elsif ($token =~ /^$num_pat[xh']$num_pat$/i) { $category = 'measurements'; }
	elsif ($token =~ /^$unit_pat[·]$unit_pat$/i) { $category = 'measurements'; }
	elsif ($token =~ /^$num_pat[x]$num_pat$unit_pat$/i) { $category = 'measurements'; }
	elsif ($token =~ /^\d+[°º](\d+('\d+)?)?$/i) { $category = 'measurements'; }
	elsif ($token =~ /^0x[0-9A-F]+$/i) { $category = 'hex'; }

	return $category . $modifier;
	}

###############
# Shuffle an array in place
#
sub shuffle {
	my $array = shift;
	my $i = @$array;
	while ( --$i ) {
		my $j = int rand( $i+1 );
		@$array[$i,$j] = @$array[$j,$i];
		}
	return;
	}

###############
# Uniquify an array
#
sub uniq {
	my %seen = ();
	return grep { ! $seen{$_}++ } @_;
	}

###############
# Add commas to long numbers
#
sub comma {
    my ($num) = @_;
    $num = reverse $num;
    $num =~ s/(\d\d\d)(?=\d)(?!\d*\.)/$1,/g;
    return scalar reverse $num;
	}

###############
# Convert a number to a percent
#
sub percentify {
	my ($num) = @_;
	return sprintf("%.3f%%", 100 * $num) if $num;
	return "0%";
	}
