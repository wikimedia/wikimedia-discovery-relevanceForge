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
use Unicode::UCD 'charscript';
use List::Util qw( max );

# set up output
*STDOUT->autoflush();
*STDERR->autoflush();
binmode(STDERR, ':encoding(UTF-8)');
binmode(STDOUT, ':encoding(UTF-8)');

# initialize data structures
my %config = ();            # general configuration settings/data
my %language_data = ();     # language-specific affix info
my %common_affixes = ();    # prefixes and suffixes found automatically
my %statistics = ();        # general stats on type and token counts, etc.
my %mapping = ();           # list of words that map to the given stem
my @stemming_results = ();  # the results of the new-only stemming grouping
my %old_v_new_results = (); # the results of comparing stemming group changes

# get options
our ($opt_d, $opt_f, $opt_l, $opt_n, $opt_o, $opt_s, $opt_S, $opt_t, $opt_x, $opt_1);
getopts('d:fl:n:o:s:S:t:x1');

my $old_file = $opt_o;
my $new_file = $opt_n;

my $default_data_dir = 'langdata/';

if (!$new_file || ! -e $new_file) {
	usage();
	exit;
	}

# set up the config
$config{data_directory} = $opt_d || $default_data_dir;
$config{explore} = $opt_x;
$config{singletons} = $opt_1;
$config{fold} = $opt_f;
$config{min_stem_len} = $opt_s || 5;
$opt_l ||= '';
%{$config{lang}} = map {lc($_) => 1} split(/[, ]+/, $opt_l);
$config{terse} = $opt_t;
$config{terse} ||= 0;
$config{Sample} = $opt_S || 0;

my $min_freqtable_link = 20;
my $token_length_examples = 10;
my $token_count_examples = 10;
my $min_alternation_freq = 4;
my $max_lost_found_sample = 100;
my $max_solo_cat_sample = 25;
my $min_unknown_cat_sample = 100;
my $hi_freq_cutoff = 1000;
my $hi_freq_sample = 25;
my $hi_impact_cutoff = 10;

# get to work
lang_specific_setup();
process_token_count_file($old_file, 'old') if $old_file;
process_token_count_file($new_file, 'new');

# HTML formatting
my $bold_open = '<b>';
my $bold_close = '</b>';
my $italic_open = '<i>';
my $italic_close = '</i>';
my $red_open = '<span class=red>';
my $red_close = '</span>';
my $cr = "<br>\n";
my $cr_all = "<br style='clear:both'>\n";
my $indent = '&nbsp;&nbsp;&nbsp;';
my $block_open = '<blockquote class=dirAuto>';
my $block_close = '</blockquote>';
my $ul_open = '<ul><li>';
my $ul_close = '</ul>';

# token categorization constants and data
my %seps = (
	' ' => 'space',        '_' => 'underscore',     '－' => 'fullwidth hyphen',
	'-' => 'hyphen minus', '‐' => 'hyphen hyphen',  '–' => 'en dash',
	'—' => 'em dash',      '―' => 'horizontal bar', ',' => 'comma',
	';' => 'semicolon',    ':' => 'colon',          '：' => 'fullwidth colon',
	'.' => 'period',       '·' => 'middot',         '‧' => 'hyphenation point',
	'|' => 'vertical line',
	);
my $sep_pat = join('', sort keys %seps);
$sep_pat =~ s/-//g; $sep_pat .= '-'; # with hypen-minus on the list, order matters

my $tone_id_pat = 'ꜜꜝꜛꜞꜟ˥˦˧˨˩꜒꜓꜔꜕꜖¹²³⁴⁵⁶⁷⁸⁹⁰₁₂₃₄₅₆₇₈₉₀';
my $tone_incl_pat = $tone_id_pat . '\p{Latin}';

my $tld_pat = '(bh|biz|ca|ch|com|cn|cz|de|dk|edu|eu|fi|fr|gov|ie|info|io|is|it|jp|net|nl|no|nz|org|pl|ru|ua|uk|us|uz|th|tv)';
my $file_type_pat = '(7z|aif|aspx?|avi|bat|bin|bmp|cfm|cgi|cpp|css|csv|dll|dmg|docx?|exe|flv|gif|gz|h264|m?html?|htmx|ico|ini|iso|jar|java|jpe?g|js|jsp|m4v|midi|mkv|mov|mp3|mp4|mpa|mpe?g|msi|odp|ods|odt|ogg|otf|pdf|php|pkg|png|ppt|pptx?|rar|rmp|rss|rtfd?|shtml?|svg|swf|sys|tar|tiff?|tmp|tsv|ttf|txt|wav|wma|wmv|woff2?|xhtml?|xlsx?|xml|zip)';
my $IPA_chars = 'ƈħɩƙŋƥƭȶʓǀǁǂǃ‿';
my $IPA_mods = 'ʰʲʷˤˡʱʵʳʴʶˢʸⁿˠˑː̝̞̪͡‿';

my $num_pat = '(\d+([.,]\d\d\d)*([.,]\d+)?)';
# no single letters in unit_pat_multi
my $unit_pat_multi = '[µμ]?([ap]\.?m|[AP]\.?M|°|°C|°F|Ca|cc|cm|eV|fps|[GkKM][Bb]|GHz|ha|Hz|kcal|kbit|keV|kg|kgm|kJ|lb|M[²³]|[Kkcmnµ]?m[²³]|[Kkcmnµ]m|Ma|MeV|mg|MHz|MHZ|ml|mol|mph|[µμ][gkKLmsΩ]|ºC|ºF|Pa|ppm|rpm|s[²³]|Ts';
my $unit_pat = $unit_pat_multi . '|[gkKLmºsWxΩM])';
$unit_pat_multi .= ")";
my $chem_pat = '(([HBCNOFPSKVYIWU]|He|Li|Be|Ne|Na|Mg|Al|Si|Cl|Ar|Ca|Sc|Ti|Cr|Mn|Fe|Co|Ni|Cu|Zn|Ga|Ge|As|Se|Br|Kr|Rb|Sr|Zr|Nb|Mo|Tc|Ru|Rh|Pd|Ag|Cd|In|Sn|Sb|Te|Xe|Cs|Ba|La|Hf|Ta|Re|Os|Ir|Pt|Au|Hg|Tl|Pb|Bi|Po|At|Rn|Fr|Ra|Ac|Rf|Db|Sg|Bh|Hs|Mt|Ds|Rg|Cn|Nh|Fl|Mc|Lv|Ts|Og|Ce|Pr|Nd|Pm|Sm|Eu|Gd|Tb|Dy|Ho|Er|Tm|Yb|Lu|Th|Pa|Np|Pu|Am|Cm|Bk|Cf|Es|Fm|Md|No|Lr)(1?\d|₁?[₀-₉])?[·‧]?)';

# category label constants (to discourage typos)
my $GREEK = 'Greek';
my $LATIN = 'Latin';
my $IPA_ISH = 'IPA-ish';
my $NON_IPA = 'Non-IPA';
my $IPA_GREEK = 'IPA-Greek';
my $HIRA_KATA = 'Hiragana/Katakana';
my $TONAL = 'Tonal Transcription';
my $MIXED = 'mixed';

# most tokens get recategorized, so keep them in a cache
my %token_cat_cache = ();

# determining charscripts is expensive, so keep them in a cache, too
my %charscript_cache = ();

my @script_colors = (
	# Unicode goes first and can block Latin
	[ 'Unicode',           '(\\\\u[0-9A-F]{4})+', 'uni', '#808080' ],
	# Latin comes before so it doesn't highlight the highlights of the others
	[ 'Latin script',      '\p{Latin}+',        'ltn', '#007700' ],
	[ 'Bengali script',    '\p{Bengali}+',      'ben', '#107896' ],
	[ 'Cyrillic script',   '\p{Cyrillic}+',     'cyr', '#ff0000' ],
	[ 'Devanagari script', '\p{Devanagari}+',   'dev', '#e68d2e' ],
	[ 'Greek script',      '\p{Greek}+',        'grk', '#0000ff' ],
	[ 'Thai script',       '\p{Thai}+',        'thai', '#9400D3' ],
	# likely useful future colors
	# 	[ 'xxx script',        '\p{xxx}+',        'xxx', '#999900' ],
	# 	[ 'xxx script',        '\p{xxx}+',        'xxx', '#FF00FF' ],
	);

# report meta/style ifo
my $HTMLmeta = <<HTML;
<meta http-equiv='Content-Type' content='text/html; charset=utf-8' />
<style>
    body { font-family:Helvetica, Noto Sans CJK JP; font-size:115%; }
    th, td { text-align:left; border: 1px solid black; padding:2px 3px; }
    table { border-collapse: collapse; }
    .vtop tr td, .vtop tr th { vertical-align:top; }
    .vcent tr td, .vcent tr th { vertical-align:center; }
    tr:nth-child(even) { background: #f8f8f8; }
    tr.key td:nth-of-type(3n+1) { text-align:center; }
    .vcent tr th:nth-of-type(3n+1) { text-align:center; }
    .red { color: red; font-weight: bold; }
    .hang { padding-left: 2em ; text-indent: -2em; }
    .invis { color:#57c6eb; cursor: help; }
    .leftCatDiv, .rightCatDiv { width:47%; border:1px solid grey; padding:1%;
        word-wrap:break-word; vertical-align: top; margin-bottom: -1px; }
    .leftCatDiv { float:left; clear:left; }
    .rightCatDiv { float:right; clear:right; }
    .newCat { border-top: 2px solid black; }
    .TOC { font-size:60%; }
    .diff { background-color:#ffffdd; }
    .bigNum { color:blue; }
    .dirAuto, .dirAuto td { text-align: start; unicode-bidi: plaintext; }
    .deemphasized { color:#C0C0C0; }
    .lenStats { font-size: 75%; color:#999; }
    .lenHist, .lenHist0, .lenHistNone { width:0.5em; display:inline-block; margin-top:8px; cursor:help; }
    .lenHist { background-color:#ccc; }
    .lenHist0 { background-color:#f00; }
    .lenHistNone { background-color:#eee; }
    .vertText { writing-mode:vertical-lr; }
    .vertCont { display:inline-block; vertical-align:top; }
HTML

# add custom style info for colorized scripts
foreach my $script ( @script_colors ) {
	my ($s_name, $s_pat, $s_class, $s_color) = @$script;
	$HTMLmeta .= "\t.$s_class { color:$s_color }\n";
	}
$HTMLmeta .= "\t" . join (', ',
	map {'.' . $_->[2]} @script_colors) . " { cursor:help; }\n</style>\n\n";

# info on invisible chars
my %invis_symbol = (
	"\x{00A0}" => '⎵',	"\x{200B}" => '⎵',	"\x{202F}" => '⎵',	"\x{FEFF}" => '⎵',
	"\x{00AD}" => '–',	"\x{0009}" => '→',	"\x{200D}" => '+',	"\x{2060}" => '+',
	"\x{200C}" => '⋮',	"\x{2063}" => '⋮',
	"\x{061C}" => '«',	"\x{200F}" => '«',	"\x{202B}" => '«',	"\x{202E}" => '«',	"\x{2067}" => '«',
	"\x{200E}" => '»',	"\x{202A}" => '»',	"\x{202D}" => '»',	"\x{2066}" => '»',
	"\x{202C}" => '↥',	"\x{2069}" => '↥',	"\x{2068}" => '∷',
	);

my %invis_desc = (
	"\x{00A0}" => 'NO-BREAK SPACE',             # '⎵' spaces
	"\x{200B}" => 'ZERO WIDTH SPACE',
	"\x{202F}" => 'NARROW NO-BREAK SPACE',
	"\x{FEFF}" => 'ZERO WIDTH NO-BREAK SPACE',
	"\x{00AD}" => 'SOFT HYPHEN',                # '–' invisible hyphen
	"\x{0009}" => 'TAB',                        # '→' tab
	"\x{200D}" => 'ZERO WIDTH JOINER',          # '+' joiners
	"\x{2060}" => 'WORD JOINER',
	"\x{200C}" => 'ZERO WIDTH NON-JOINER',      # '⋮' non-joiner
	"\x{2063}" => 'INVISIBLE SEPARATOR',
	"\x{061C}" => 'ARABIC LETTER MARK',         # '«' RTL marks
	"\x{200F}" => 'RIGHT-TO-LEFT MARK',
	"\x{202B}" => 'RIGHT-TO-LEFT EMBEDDING',
	"\x{202E}" => 'RIGHT-TO-LEFT OVERRIDE',
	"\x{2067}" => 'RIGHT-TO-LEFT ISOLATE',
	"\x{200E}" => 'LEFT-TO-RIGHT MARK',         # '»' LTR marks
	"\x{202A}" => 'LEFT-TO-RIGHT EMBEDDING',
	"\x{202D}" => 'LEFT-TO-RIGHT OVERRIDE',
	"\x{2066}" => 'LEFT-TO-RIGHT ISOLATE',
	"\x{202C}" => 'POP DIRECTIONAL FORMATTING', # '↥' pop bidi
	"\x{2069}" => 'POP DIRECTIONAL ISOLATE',
	"\x{2068}" => 'FIRST STRONG ISOLATE',       # '∷' FSI
	);

# Add info for 256 variation selectors
my $vsbase = hex('0xFE00')-1;
foreach my $varsel (1..256) {
	# U+FE00 to U+FE0F = variation selectors 1 to 16
	# U+E0100 to U+E01EF = variation selectors 17 to 256
	if ($varsel == 17) {
		$vsbase = hex('0xE0100')-17;
		}
	$invis_symbol{chr($vsbase + $varsel)} = '∵';
	$invis_desc{chr($vsbase + $varsel)} = "VARIATION SELECTOR-$varsel";
	}

my $invis_pat = '[' . join('', sort keys %invis_symbol) . ']';

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
				if ($lc_old{fold($lc_n)} || $lc_old{despace($lc_n)} ||
						$lc_old{dehyphenate($lc_n)}) {
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
						if ($lc_old{fold($nn)} || $lc_old{despace($nn)} ||
								$lc_old{dehyphenate($nn)}) {
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
						if ($lc_old{fold($nn)} || $lc_old{despace($nn)} ||
								$lc_old{dehyphenate($nn)}) {
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
						if ($lc_old{fold($nn)} || $lc_old{despace($nn)} ||
								$lc_old{dehyphenate($nn)}) {
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
						if ($lc_old{fold($nn)} || $lc_old{despace($nn)} ||
								$lc_old{dehyphenate($nn)}) {
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
					$mapo = join('|', uniq(map { lc(fold($_, 1)) } ($mapo =~ /\[(.*?)\]/g)));
					$mapn = join('|', uniq(map { lc(fold($_, 1)) } ($mapn =~ /\[(.*?)\]/g)));
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

else { # new file only (solo)
	foreach my $final (sort keys %mapping) {
		my @terms = uniq(map {affix_fold($_)} $mapping{$final}{new} =~ /\[\d+? (.*?)\]/g);
		my $token_count = 0;
		my $final_len = length($final);

		foreach my $count (map {affix_fold($_)} $mapping{$final}{new} =~ /\[(\d+?) .*?\]/g) {
			$token_count += $count;
			$statistics{token_length}{$final_len} += $count;
			}

		$statistics{count_freqtable}{scalar(@terms)}++;

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
				$common = '+';
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
						@terms = map { $_ = lc(fold($_, 1)) } @terms;
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
	print <<USAGE;
usage: $0 -n <new_file> [-o <old_file>] [-d <dir>] [-l <lang,lang,...>]
    [-S <#>] [-x] [-1] [-f] [-s <#>] [-t <#>] > output.html

    -n <file>  "new" counts file
    -d <dir>   specify the dir for language data config; default: $default_data_dir
    -l <lang>  specify one or more language configs to load.
               See ${default_data_dir}example.txt for config details
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
		open(my $FILE, '<:encoding(UTF-8)', $config{data_directory} . "/$language.txt");
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

	$language_data{strippable_prefix_regex} = join('|', @strip_pref);
	$language_data{strippable_suffix_regex} = join('|', @strip_suff);

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
	my ($filename, $old_new) = @_;
	my $ready = 0;
	my $final;
	my $orig;

	open(my $FILE, '<:encoding(UTF-8)', $filename);
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
				my ($empty, $cnt, $tokens) = split(/\t/, $_, 3);
				my $token_cnt = scalar(split(/\|/, $tokens));
				push @{$statistics{token_cnt}{$old_new}[$token_cnt]}, $orig unless $old_file;
				}
			else {
				$orig = $_;
				}
			}
		else {
			if (/^\t/) {
				# original tokens
				my ($empty, $cnt);
				($empty, $cnt, $orig) = split(/\t/, $_, 3);
				count_tokens($orig, $final, $cnt, $old_new);
				$statistics{type_count}{orig}{$old_new}++;
				$statistics{total_tokens}{$old_new} += $cnt;
				}
			else {
				# final tokens
				$final = $_;
				$statistics{type_count}{final}{$old_new}++;
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
	my ($o, $f, $cnt, $old_new) = @_;
	$statistics{token_exists}{original}{$o}{$old_new} += $cnt;
	$statistics{token_exists}{final}{$f}{$old_new} += $cnt;
	if ($o eq $f) {
		$statistics{token_count}{$old_new}{unchanged}{token} += $cnt;
		$statistics{token_count}{$old_new}{unchanged}{type}++;
		if ($o =~ /^\d+$/) {
			$statistics{token_count}{$old_new}{number}{token} += $cnt;
			$statistics{token_count}{$old_new}{number}{type}++;
			}
		}
	if (lc($o) eq lc($f)) {
		$statistics{token_count}{$old_new}{lc_unchanged}{token} += $cnt;
		$statistics{token_count}{$old_new}{lc_unchanged}{type}++;
		}
	$mapping{$f}{$old_new} .= "[$cnt $o]";
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
# remove soft hyphen, en dash, em dash, hyphen
#
sub dehyphenate {
	my ($term) = @_;
	$term =~ s/[\x{00AD}\x{2013}\x{2014}-]//g;
	return $term;
	}

###############
# remove spaces
#
# remove ideographic space, zero-width non-breaking space, normal space
#
sub despace {
	my ($term) = @_;
	$term =~ s/[\x{3000}\x{FEFF} ]//g;
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
	$item =~ s/[‘’ʼ＇]/'/g;
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
			for (my $i = 0 ; $i < $termlen - $maxlen + 1 ; $i++) {
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
# generate final report for old vs new analysis
#
sub print_old_v_new_report {

	print $HTMLmeta;

	# config info header
	print $bold_open, "Processing $old_file as 'old'.", $bold_close, $cr;
	print $bold_open, "Processing $new_file as 'new'.", $bold_close, $cr;
	if (0 < keys %{$config{lang}}) {
		print $bold_open, 'Language processing: ', $bold_close,
			join(', ', sort keys %{$config{lang}}), $cr;
		}
	print $cr;
	print $bold_open, 'Total old tokens: ', $bold_close, comma($statistics{total_tokens}{old}), $cr;
	print $bold_open, 'Total new tokens: ', $bold_close, comma($statistics{total_tokens}{new}), $cr;
	my $tok_delta = $statistics{total_tokens}{new} - $statistics{total_tokens}{old};
	print $indent, $bold_open, 'Token delta: ', $bold_close, comma($tok_delta), ' (',
		percentify($tok_delta/$statistics{total_tokens}{old}), ')', $cr;

	# navigation links
	my $new_split_stats = $old_v_new_results{splits}{post_type} ?
		"$indent<a href='#new_split_stats'>New Split Stats</a><br>" : '';
	my $token_count_increases = $old_v_new_results{gains}{post_type} ?
		"$indent<a href='#token_count_increases'>Token Count Increases</a><br>" : '';
	my $token_count_decreases = $old_v_new_results{losses}{post_type} ?
		"$indent<a href='#token_count_decreases'>Token Count Decreases</a><br>" : '';
	my $empty_token_inputs = ($mapping{''}) ?
		"<a href='#empty_token_inputs'>Empty Token Inputs</a><br>" : '';

	print_section_head('Table of Contents', 'TOC');
	print <<HTML;
<a href='#PPTTS'>Pre/Post Type & Token Stats</a><br>
$empty_token_inputs
<a href='#new_collision_stats'>New Collision Stats</a><br>
$new_split_stats
$token_count_increases
$token_count_decreases
$indent<a href='#new_collision_near_match_stats'>New Collision Near Match Stats</a><br>
<a href='#lost_and_found'>Lost and Found Tokens</a><br>
$indent<a href='#lost_and_found_pre'>Pre-analysis Lost and Found</a><br>
$indent<a href='#lost_and_found_post'>Post-analysis Lost and Found</a><br>
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
	if ($old_v_new_results{increased}) {
		print "$indent<a href='#changed_collisions_increased'>Net Gains</a><br>";
		$spacer = 1;
		}

	print <<HTML if $config{Sample};
<a href='#samplesForReview'>Samples for Speaker Review</a><br>
HTML

	print_highlight_key();

	print_section_head('Pre/Post Type & Token Stats', 'PPTTS');

	foreach my $tag ('old', 'new') {
		print "<div style='display:inline-block; margin-right:3em'>\n";
		print $bold_open, "\n\u$tag File Info", $bold_close, $cr;
		print $indent, ' pre-analysis types: ', comma($statistics{type_count}{orig}{$tag}), $cr;
		print $indent, 'post-analysis types: ', comma($statistics{type_count}{final}{$tag}), $cr;
		print $cr;
		my @types = ('type', 'token');
		print_table_head(@types, 'change_type');
		foreach my $change ('unchanged', 'lc_unchanged', 'number') {
			print_table_row([(map { comma($statistics{token_count}{$tag}{$change}{$_}); } @types),
				$change]);
			}
		print_table_foot();
		print "</div>\n";
		}

	print $cr, $cr;

	print_table_key ('Key', '',
		'Categories overlap. Numbers are usually unchanged, and all lc_unchanged are also unchanged.',
		'unchanged', 'pre-analysis token is the same as post-analysis token',
		'lc_unchanged', 'pre-analysis token is the same as post-analysis token after lowercasing',
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
		print $indent, "total types in collisions: $pre_tot ($pre_tot_pct of pre-analysis types)",
			$cr if $pre_tot;
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
		print $indent, "total types in splits: $pre_tot ($pre_tot_pct of pre-analysis types)",
			$cr if $pre_tot;
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
		print_table_row([(map { comma($old_v_new_results{collision}{near_match}{$kind}{$_}); }
			@types), $kind]);
		}
	print_table_foot();
	print $cr;

	print_table_key ('Key',
		'New collision type is a near match for a type already in the group after...',
		'Categories do not overlap. Types are post-analysis types',
		'folded', 'applying generic and language-specific character folding, de-spacing, and de-hyphenation',
		'regulars', 'removing language-specific regular prefixes and suffixes',
		'folded_regulars', 'applying generic and language-specific character folding, de-spacing, de-hyphenation, and removing language-specific regular prefixes and suffixes'
		);

	print_section_head('Lost and Found Tokens', 'lost_and_found');
	my %tot = ();
	my %only = ();

	foreach my $orig_final ('original', 'final') {
		my $pre_post = $orig_final eq 'original' ? 'pre' : 'post';

		print_section_head(ucfirst($pre_post) . '_analysis Lost and Found',
			'lost_and_found_' . $pre_post, 4);

		my %lost_config  = ( desc => "Lost (old only) $pre_post-analysis",
			orig_final => $orig_final,  old_new => 'old', types => 0, tokens => 0,
			token_list => {} );
		my %found_config = ( desc => "Found (new only) $pre_post-analysis",
			orig_final => $orig_final,  old_new => 'new', types => 0, tokens => 0,
			token_list => {} );

		foreach my $token (keys %{$statistics{token_exists}{$orig_final}}) {
			my $ocnt = $statistics{token_exists}{$orig_final}{$token}{old};
			my $ncnt = $statistics{token_exists}{$orig_final}{$token}{new};
			next if ($ocnt && $ncnt);
			if ($ocnt) {
				$lost_config{types}++;
				$lost_config{tokens} += $ocnt;
				push @{$lost_config{token_list}{token_category($token)}}, $token;
				}
			else {
				$found_config{types}++;
				$found_config{tokens} += $ncnt;
				push @{$found_config{token_list}{token_category($token)}}, $token;
				}
			}

		if ($lost_config{types} || $found_config{types}) {
			print_category_stats(\%lost_config, \%found_config, $max_lost_found_sample);
			}
		}

	print_section_head('Changed Groups', 'changed_collisions');
	print_collision_key();

	print_changed_collisions('Net Losses', 'decreased', '<<');
	print_changed_collisions('Mixed', 'mixed', '><');
	print_changed_collisions('Net Gains', 'increased', '>>');

	if ($config{Sample}) {
		# Samples for Speaker Review
		print_section_head('Samples for Speaker Review', 'samplesForReview');
		print_collision_key();
		print $cr;

		print_sampled_collisions('Lost', 'decreased', '<<', 1);
		print_sampled_collisions('Lost & Gained', 'mixed', '><', 1);
		print_sampled_collisions('Gained', 'increased', '>>', 1);
		}
	return;
	}

###############
# print key to net gains/losses/mixed tables
#
sub print_collision_key {
	print_table_key ('', '', '',
		'<<', 'indicates net loss of types/tokens',
		'><', 'indicates mixed gains and losses of types/tokens',
		'>>', 'indicates net gain of types/tokens',
		'#', 'the number following indicates the magnitude of the change (#types affected)',
		'terseness', $config{terse},
		'<span class=diff>[1 diff]</span>', 'diffs between old and new sets',
		'<b class=bigNum>[1000 freq]</b>', 'high-frequency terms'
		);
	}

###############
# print category stats for one or two comparison sets, e.g., lost/found or pre/post
#
sub print_category_stats {
	my ($left_cfg, $right_cfg, $samp_limit) = @_;
	my $last_cat = '';
	my $base_cat = '';
	my $new_cat_left = '';
	my $new_cat_right = '';

	my $has_both = $left_cfg->{types} && $right_cfg->{types};

	print "&bull; $left_cfg->{desc} types/tokens: ",  comma($left_cfg->{types}), ' / ',
		comma($left_cfg->{tokens}), $cr;
	print "&bull; $right_cfg->{desc} types/tokens: ", comma($right_cfg->{types}), ' / ',
		comma($right_cfg->{tokens}), $cr;
	print $cr;

	print "<div class=leftCatDiv>\n" if $has_both;
	print "$bold_open $left_cfg->{desc} tokens by category$bold_close" if $left_cfg->{types};
	print "\n</div>\n<div class=rightCatDiv>\n" if $has_both;
	print "$bold_open $right_cfg->{desc} tokens by category$bold_close" if $right_cfg->{types};
	print "\n</div>\n" if $has_both;
	print $cr_all;
	print $cr unless $has_both;

	my @cats = sort {$a cmp $b} uniq(keys %{$left_cfg->{token_list}},
		keys %{$right_cfg->{token_list}});

	foreach my $category (@cats) {
		$category =~ /^(( mixed-)?\s*\w+)\b/;
		$base_cat = $1 || '';
		if ($base_cat ne $last_cat) {
			print $cr_all if $last_cat;
			$last_cat = $base_cat;
			$new_cat_left = $new_cat_right = ' newCat';
			}
		if ($left_cfg->{types} && $left_cfg->{token_list}{$category}) {
			print "<div class='leftCatDiv$new_cat_left'>\n" if $has_both;
			print_script_category($left_cfg, $category, $samp_limit);
			print "\n</div>\n" if $has_both;
			$new_cat_left = '';
			}
		if ($right_cfg->{types} && $right_cfg->{token_list}{$category}) {
			print "<div class='rightCatDiv$new_cat_right'>\n" if $has_both;
			print_script_category($right_cfg, $category, $samp_limit);
			print "\n</div>\n" if $has_both;
			$new_cat_right = '';
			}
		}

	print $cr_all if $has_both;
	print $cr;

	return;
	}

###############
# output just one script category
#
sub print_script_category {
	my ($cfg, $category, $samp_limit) = @_;
	my $orig_final = $cfg->{orig_final};
	my $old_new = $cfg->{old_new};
	my $token_list_ref = $cfg->{token_list}{$category};

	if ($category =~ /unknown/ && $samp_limit < $min_unknown_cat_sample) {
		$samp_limit = $min_unknown_cat_sample;
		}

	my $token_tot = 0;
	my $len_sum = 0;
	my $len_sum2 = 0;
	my $len_min = -1;
	my $len_max = 0;
	my @len_hist = ();
	my $len_count = scalar(@{$token_list_ref});

	foreach my $item (@{$token_list_ref}) {
		$token_tot += $statistics{token_exists}{$orig_final}{$item}{$old_new} || 0;
		my $len = length($item);
		$len_hist[$len]++;
		$len_max = $len if $len > $len_max;
		$len_min = $len if $len < $len_min || $len_min == -1;
		$len_sum += $len;
		$len_sum2 += $len * $len;
		}

	my $type_tot = scalar(@{$token_list_ref});
	print $indent, $italic_open, $category, ':', $italic_close, ' ',
		comma($type_tot), ' types, ', comma($token_tot), ' tokens',
		($type_tot > $samp_limit) ? " (sample of $samp_limit)" : '', $cr;

	my $colorize = $category =~ /^  unknown|IPA|Tonal|^ mixed|Unicode|name-like/;
	my $isUnicode = $category =~ /Unicode/;
	my $isVertText = $category =~ /Mongolian/;
	my $joiner = $isUnicode ? "\n<li> " : ' &bull; ';

	my $picks = $samp_limit;
	my $samples = $len_count;

	print $isUnicode ? $ul_open : $block_open;
	print show_invisibles(join($joiner,
		map { $isVertText ? "<div class=vertCont><div class=vertText>$_</div></div>" : $_ }
		map { $colorize ? color_scripts($_) : $_ }
		map { $isUnicode ? too_long(defrag($_)) : $_ }
		sort { lc($a) cmp lc($b) || $a cmp $b }
		grep { ($picks && rand() < $picks/$samples--) ? $picks-- : 0 }
		@{$token_list_ref})), $cr;

	my @hifreq = sort { $statistics{token_exists}{$orig_final}{$b}{$old_new} <=>
			$statistics{token_exists}{$orig_final}{$a}{$old_new}}
			grep { ($statistics{token_exists}{$orig_final}{$_}{$old_new} || 0) >=
			$hi_freq_cutoff } @{$token_list_ref};
	my $hifreq_overflow = '';
	if (@hifreq) {
		if ($isUnicode) { print $ul_close; }
		if (@hifreq > $hi_freq_sample) {
			$hifreq_overflow = ' ... and ' . (@hifreq - $hi_freq_sample) . ' more';
			@hifreq = @hifreq[0 .. $hi_freq_sample - 1];
			}
		print $cr, $indent, $italic_open, 'hi-freq tokens: ', $italic_close,
			$isUnicode ? $ul_open : '',
			show_invisibles(join($joiner,
				map { ($isUnicode ? too_long(defrag($_)) : $_) .
					' <span class=deemphasized>| ' .
					comma($statistics{token_exists}{$orig_final}{$_}{$old_new}) . '</span>'; }
				@hifreq)), $hifreq_overflow, $cr;
		}
	print $isUnicode ? $ul_close : $block_close;

	my $no_variance = ($len_min == $len_max);
	print $block_open, '<span class="lenStats">type length',
		$no_variance ? ": $len_min" : "s: $len_min–$len_max",
		', n=', comma($len_count),
		', µ=', $no_variance ? $len_max : sprintf('%.2f', $len_sum/$len_count),
		', σ=', $len_count == 1 ? '0' : sprintf('%.2f', sqrt($len_sum2 / $len_count -
				$len_sum * $len_sum / $len_count / $len_count)), '</span>';

	print_type_len_hist(\@len_hist, $len_min) if $len_count > 1;

	print $block_close, "\n";

	return;
	}

###############
# generate a hacky little HTML in-line histogram of type lengths
#
sub print_type_len_hist {
	my ($aref, $lmin) = @_;
	my @vals = map {$_ || 0} @$aref;
	my $max = max(@vals);
	print $indent;
	my $start = 0;
	if ($lmin > 3) {
		$start = $lmin;
		print '<span class=lenStats>...</span>';
		}
	for my $i ($start .. @vals-1) {
		my $h = int(15*$vals[$i]/$max + 0.5);
		my $class = 'lenHist';
		if ($i == 0) {
			next if $vals[$i] == 0;
			$class = 'lenHist0';
			}
		$class = 'lenHistNone' if $vals[$i] == 0;
		print "<div title=\"len:$i; freq:", comma($vals[$i]), '" class=', $class,
			' style="height:', $h+1, 'px;"></div>';
		}
	print $cr;
	}

###############
# generate final report for new-only analysis
#
sub print_new_report {
	print $HTMLmeta;

	# config info header
	print $bold_open, "Processing $new_file as 'new'.", $bold_close, $cr x2;
	print $bold_open, 'Total new tokens: ', $bold_close, comma($statistics{total_tokens}{new}), $cr;

	print $indent, $bold_open, 'pre-analysis types: ', $bold_close,
		comma($statistics{type_count}{orig}{new}), $cr;
	print $indent, $bold_open, 'post-analysis types: ', $bold_close,
		comma($statistics{type_count}{final}{new}), $cr;
	print $cr;

	if (0 < keys %{$config{lang}}) {
		print $bold_open, 'Language processing: ', $bold_close,
			join(', ', sort keys %{$config{lang}}), $cr;
		}
	print $cr;

	# navigation links
	print <<HTML;
<a name='TOC'><h3>Table of Contents</h3>
<a href='#stemmingResults'>Stemming Results</a><br>
$indent<a href="#prob1">Potential Problem Stems</a><br>
HTML
	print <<HTML if $config{Sample};
<a href='#samplesForReview'>Samples for Speaker Review</a><br>
HTML
	print <<HTML if $config{explore};
<a href='#commonPrefixes'>Common Prefix Alternations</a><br>
<a href='#commonSuffixes'>Common Suffix Alternations</a><br>
HTML
	print <<HTML;
<a href='#typeCountFreqTable'>Case-Insensitive Type Group Counts</a><br>
<a href='#tokenCountFreqTable'>Stemmed Tokens Generated per Input Token</a><br>
<a href='#typeLengthFreqTable'>Final Type Lengths</a><br>
<a href='#tokenCategories'>Token Samples by Category</a><br>
HTML

	print_highlight_key();

	# stemming results
	print_section_head('Stemming Results' .
		($config{singletons} ? ' (singletons)' : ' (groups only)'), 'stemmingResults');

	# stemming results key
	print '.. indicates raw / lowercased string matches', $cr;
	print ':: indicates affix-stripped matches', $cr if $config{lang};
	print '-- indicates ', ($config{lang} ? 'affix-stripped and ' : ''), 'folded matches', $cr;
	print $cr;

	# stemming results table
	my $prob_ref_cnt = 1;
	my %type_ref_cnt = ();
	my @problem_sample = ();
	my @large_sample = ();
	my @random_sample = ();
	print_table_head('stem', 'common', 'group total', 'distinct types', 'types (counts)');
	foreach my $aref (@stemming_results) {
		my ($final, $token_count, $common, $type_cnt) = @$aref;

		my $display_final = too_long($final);
		my $display_type_cnt = $type_cnt;
		if ($common =~ /^ .. $/) {
			$display_final = "<a name='prob" . $prob_ref_cnt . "'>";
			$display_final .= "<a href='#prob" .
				++$prob_ref_cnt . "'>" . $red_open . $final . $red_close . '</a>';
			$common = $red_open . "&nbsp;$common&nbsp;" . $red_close;
			push @problem_sample, $aref if $config{Sample};
			}
		if ($type_cnt >= $min_freqtable_link) {
			if (!$type_ref_cnt{$type_cnt}) {
				$type_ref_cnt{$type_cnt} = 1;
				}
			$display_type_cnt = "<a name='count$type_cnt." . $type_ref_cnt{$type_cnt} .
				"'>";
			$display_type_cnt .= "<a href='#count$type_cnt." . ++$type_ref_cnt{$type_cnt} . "'>" .
				$red_open . $type_cnt . $red_close . '</a>';
			push @large_sample, $aref if $config{Sample};
			}
		my $the_mapping = $mapping{$final}{new};
		$the_mapping =~ s/ /&nbsp;/g;
		$the_mapping = show_invisibles($the_mapping);

		print_table_row([$display_final, $common, comma($token_count), $display_type_cnt,
			$the_mapping], 'dirAuto');
		}
	print_table_foot();
	print "<br><a name='prob", $prob_ref_cnt, "'> [Total of ", ($prob_ref_cnt - 1),
		' potential problem stem', ($prob_ref_cnt == 2 ? '' : 's'), "]<br>\n";

	if ($config{Sample}) {
		# Samples for Speaker Review
		print_section_head('Samples for Speaker Review', 'samplesForReview');

		# sub-sample problem stem samples randomly
		my $set_cnt = scalar(@problem_sample);
		my $samp_cnt = $set_cnt;
		if ($samp_cnt > $config{Sample}) {
			shuffle(\@problem_sample);
			@problem_sample = sort {$a->[0] cmp $b->[0]} @problem_sample[0 .. ($config{Sample}-1)];
			$samp_cnt = $config{Sample};
			}
		my $problem_desc = "<b>Potential Problem Stemming Groups</b> ($samp_cnt of $set_cnt)";

		# sub-sample large group samples by size
		# omit previously seen problem stem samples
		$set_cnt = scalar(@large_sample);
		@large_sample = sort {$b->[3] <=> $a->[3]} set_diff(\@large_sample, \@problem_sample);
		my $repeat_cnt = $set_cnt - scalar(@large_sample);
		$samp_cnt = scalar(@large_sample);
		if ($samp_cnt > $config{Sample}) {
			@large_sample = @large_sample[0 .. ($config{Sample}-1)];
			$samp_cnt = $config{Sample};
			}
		my $repeat_msg = $repeat_cnt
			? " ($repeat_cnt problem stem" . ($repeat_cnt == 1 ? '' : 's') . ' omitted)'
			: '';
		my $large_desc = "<b>Largest Stemming Groups</b> ($samp_cnt of $set_cnt$repeat_msg)";

		# create a random sample
		# over-generate x3, remove duplicates, and then remove any problem stems or
		# large group examples and down sample from there.
		for (my $i = 0; $i < $config{Sample} * 3; $i++) {
			push @random_sample, @stemming_results[rand @stemming_results];
			}
		@random_sample = uniq(@random_sample);
		@random_sample = set_diff(\@random_sample, \@problem_sample);
		@random_sample = set_diff(\@random_sample, \@large_sample);
		$samp_cnt = scalar(@random_sample);
		if ($samp_cnt > $config{Sample}) {
			@random_sample = @random_sample[0 .. ($config{Sample}-1)];
			}
		$samp_cnt = scalar(@random_sample);
		@random_sample = sort { $a->[0] cmp $b->[0] } @random_sample;
		my $random_desc = "<b>Random Stemming Groups</b> ($samp_cnt)";

		# output the samples in a less alarm-inducing order
		speaker_sample($random_desc, @random_sample);
		speaker_sample($large_desc, @large_sample);
		speaker_sample($problem_desc, @problem_sample);
		}

	# explore: show automatically generated affix candidates
	if ($config{explore}) {
		print_alternations('Common Prefix Alternations', 'commonPrefixes', 'pre',
			$language_data{regular_prefixes_hash});
		print_alternations('Common Suffix Alternations', 'commonSuffixes', 'suf',
			$language_data{regular_suffixes_hash});
		}

	# some stats
	print_section_head('Case-Insensitive Type Group Counts', 'typeCountFreqTable');
	print_table_head('count', 'freq');
	foreach my $cnt (sort {$a <=> $b} keys %{$statistics{count_freqtable}}) {
		my $cnt_display = $cnt;
		if ($cnt >= $min_freqtable_link) {
			$cnt_display = "<a name='count$cnt." . $type_ref_cnt{$cnt} ."'><a href='#count$cnt.1'>$cnt</a>";
			}
		print_table_row([$cnt_display, comma($statistics{count_freqtable}{$cnt})]);
		}
	print_table_foot();

	my $joiner = ' &nbsp; &bull; &nbsp; ';
	print_section_head('Stemmed Tokens Generated per Input Token',
		'tokenCountFreqTable');
	print_table_head('count', 'freq', 'example input tokens');
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
			print_table_row([$i, comma($freq), show_invisibles(join($joiner, map {color_scripts($_)}
				sort @examples))]);
			}
		}
	print_table_foot();

	print_section_head('Final Type Lengths', 'typeLengthFreqTable');
	print_table_head('length', 'type freq', 'token count', 'examples');
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
			print_table_row([$len, comma($freq), comma($statistics{token_length}{$len}),
				show_invisibles(join($joiner,
					map { /^(\\u[0-9A-F]{4})+$/i ?
							too_long(color_scripts(defrag($_), $LATIN)) :
							color_scripts($_) }
					sort @examples))]);
			}
		}
	print_table_foot();

	print_section_head('Token Samples by Category', 'tokenCategories');
	my %pre_config  = ( desc => 'Pre-analysis',  orig_final => 'original', old_new => 'new',
		types => 0, tokens => 0, token_list => {} );
	my %post_config = ( desc => 'Post-analysis', orig_final => 'final',    old_new => 'new',
		types => 0, tokens => 0, token_list => {} );
	gather_cat_info(\%pre_config);
	gather_cat_info(\%post_config);
	print_category_stats(\%pre_config, \%post_config, $max_solo_cat_sample);

	return;
	}

###############
# for a given config, gather relevant info on type and token counts, and category samples
#
sub gather_cat_info {
	my ($cfg) = @_;
	foreach my $token (keys %{$statistics{token_exists}{$cfg->{orig_final}}}) {
		if (my $cnt = $statistics{token_exists}{$cfg->{orig_final}}{$token}{$cfg->{old_new}}) {
			$cfg->{types}++;
			$cfg->{tokens} += $cnt;
			push @{$cfg->{token_list}{token_category($token)}}, $token;
			}
		}
	return;
	}

###############
# print a section heading, along with internal anchor
#
sub print_section_head {
	my ($header, $aname, $subhead) = @_;
	my $head = $subhead ? "h$subhead" : 'h3';
	$aname = $aname ? "<a name='$aname'>" : '';
	print "\n$aname<$head>$header <a href=#TOC class=TOC>[TOC]</a></$head>\n";
	return;
	}

###############
# print the header for a table
#
sub print_table_head {
	print_table_head_class('vtop', @_);
	return;
	}

sub print_table_head_class {
	my ($class, @items) = @_;

	print "<table class='$class'>";
	if (@items) {
		print '<tr><th>', join('</th><th>', @items), '</th></tr>';
		}
	print "\n";
	return;
	}

###############
# print a row of a table
#
sub print_table_row {
	my ($aref, $class) = @_;
	my $row_pre = '<tr><td>';

	if ($class) {
		$row_pre = "<tr class='$class'><td>";
		}

	if (scalar(@$aref)) {
		print $row_pre, join('</td><td>', map {defined $_ ? $_ : ''} @$aref), '</td></tr>', "\n";
		}
	return;
	}

###############
# finish off the table
#
sub print_table_foot {
	print "</table>\n";
	return;
	}

###############
# print a table key, as a table
#
sub print_table_key {
	my ($title, $header, $footer, @keys_and_values) = @_;

	my $div_open = '<div class=hang>';
	my $div_close = '</div>';

	print $bold_open, $title, $bold_close, $cr if $title;
	if ($header) {
		print $header, $cr;
		}
	while (@keys_and_values) {
		print $div_open, $indent, $bold_open, (shift @keys_and_values), ':', $bold_close,
			' ', (shift @keys_and_values), $div_close;
		}
	if ($footer) {
		print $footer, $cr;
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

	print_section_head($gain_loss, 'changed_collisions_' . $incr_decr, 4);
	print_collision_table($old_v_new_results{$incr_decr}, $incr_decr, $arr, 1);

	return;
	}

###############
# Print the Changed Collision Net Gains and Net Losses Speaker Sample
#
sub print_sampled_collisions {
	my ($gain_loss, $incr_decr, $arr) = @_;

	my @random_sample =
		grep { $old_v_new_results{magnitude}{$_} < $hi_impact_cutoff }
		@{$old_v_new_results{$incr_decr}};
	if (@random_sample > $config{Sample}) {
		shuffle(\@random_sample);
		@random_sample = @random_sample[0 .. ($config{Sample}-1)]
		}
	@random_sample = sort @random_sample;
	print "<b>Random Stemming Groups That $gain_loss Members</b> (",
		scalar(@random_sample), ")$cr$cr";
	if (@random_sample) {
		print_collision_table(\@random_sample, $incr_decr, $arr, 0);
		}

	my @large_sample =
		sort { $old_v_new_results{magnitude}{$b} <=> $old_v_new_results{magnitude}{$a} }
		grep { $old_v_new_results{magnitude}{$_} >= $hi_impact_cutoff }
		@{$old_v_new_results{$incr_decr}};
	my $all_large_cnt = scalar(@large_sample);
	if (@large_sample > $config{Sample}) {
		@large_sample = @large_sample[0 .. ($config{Sample}-1)]
		}
	print "<b>Stemming Groups That $gain_loss the Most Members</b> (",
		scalar(@large_sample), " of $all_large_cnt)$cr$cr";
	if (@large_sample) {
		print_collision_table(\@large_sample, $incr_decr, $arr, 0);
		}

	return;
	}

###############
# print just the table highlighting collisions and splits
#
sub print_collision_table {
	my ($coll_ref, $incr_decr, $arr, $show_hic) = @_;

	my $div_open = '<div class=hang>';
	my $div_close = '</div>';

	my $hic = 1;
	print "<a href='#hic_$incr_decr\_1'><b>High Impact Changes</b></a><br><br>\n" if $show_hic;

	print_table_head();
	foreach my $final (@{$coll_ref}) {
		my $impact = $old_v_new_results{magnitude}{$final};
		my $hic_open = '';
		my $hic_close = '';
		if ($impact >= $hi_impact_cutoff && $show_hic) {
			$hic_open = "<a name='hic_$incr_decr\_$hic'><a href='#hic_$incr_decr\_" . ++$hic . "'>";
			$hic_close = '</a>';
			}
		my $oldmap = $mapping{$final}{old};
		my $newmap = $mapping{$final}{new};
		($oldmap, $newmap) = highlight_diffs($oldmap, $newmap);
		print_table_row(["<nobr>$hic_open" . show_invisibles(too_long($final)) .
			" $arr $impact$hic_close</nobr>",
			$div_open . 'o: ' . show_invisibles(color_by_count($oldmap)) . $div_close .
			$div_open . 'n: ' . show_invisibles(color_by_count($newmap)) . $div_close
			]);
		}
	print_table_foot();
	print "<a name='hic_$incr_decr\_$hic'>\n" if $show_hic;
	print $cr;
	}

###############
# highlight diffs in lists
#
sub highlight_diffs {
	my ($m1, $m2) = @_;

	my @tok1 = split(/(?=\[)/, $m1);
	my %tok1 = map { $_ => 1 } @tok1;

	my @tok2 = split(/(?=\[)/, $m2);
	my %tok2 = map { $_ => 1 } @tok2;

	$m1 = join('', map { $tok2{$_} ? $_ : "<span class=diff>$_</span>" } @tok1);
	$m2 = join('', map { $tok1{$_} ? $_ : "<span class=diff>$_</span>" } @tok2);

	return ($m1, $m2);
	}

###############
# Make very long tokens display better in tables
#
# add word-break tags in long strings of unicode-encoded tokens
#
sub too_long {
	my ($token) = @_;
	$token =~ s/(\\u[0-9A-F]{4})/$1<wbr>/g;
	return $token;
	}

###############
# add bolding and color (blue by default) to samples "[### token]" where
# the number is a certain number of digits (4 by default)
#
# - will apply incorrectly if "token" contains a close bracket ]
#
sub color_by_count {
	my ($str, $digits, $class) = @_;
	$digits ||= 4;
	$class ||= 'bigNum';
	$str =~ s!(\[[0-9]{$digits}[^\]]+\])!<b class='$class'>$1</b>!g;
	return $str;
	}

###############
# print alternations table for affix with give title
# provide anchor
#
sub print_alternations {
	my ($title, $aname, $affix, $known_pairs) = @_;

	my $tot_href = \%{$common_affixes{tot}{$affix}};
	my $oneby_href = \%{$common_affixes{onebyone}{$affix}};
	my $group_href = \%{$common_affixes{gp}{$affix}};

	print_section_head($title, $aname);

	my @headings = ('1x1 count', 'group count', 'alt 1', 'alt 2');
	if ($known_pairs) {
		push @headings, 'known';
		}
	print_table_head(@headings);

	my $cnt = 0;
	foreach my $item (sort { $tot_href->{$b} <=> $tot_href->{$a} || $a cmp $b } keys %{$tot_href}) {
		last if ($tot_href->{$item} < $min_alternation_freq);
		my ($a, $b, $z) = split(/\|/, $item);
		my @row_data = (comma($oneby_href->{$item}) || '', comma($group_href->{$item}) || '', $a, $b);
		my $known = '';
		my $red = 'red';
		if ($known_pairs) {
			$known = $known_pairs->{join('|', sort ($a, $b))} ? '*' : '';
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

	# memoize!
	if ($token_cat_cache{$token}) {
		return $token_cat_cache{$token};
		}

	# short-circuit most common easy case
	if ($token =~ /^[a-zA-ZÀ-ÖØ-öø-ž]+$/) {
		$token_cat_cache{$token} = 'Latin';
		return 'Latin';
		}

	# short-circuit all-one script cases (except Latin.. if we didn't get it above,
	# we want to investigate more carefully)
	my $first_script = charscript(ord(substr($token, 0, 1)));
	if ($token =~ /^\p{$first_script}+$/i &&
		$first_script ne 'Latin' && $first_script ne 'Common' &&
		$first_script ne 'Inherited' && $first_script ne 'Unknown'
		) {
		$first_script =~ s/_(.)/ \u$1/g;
		$token_cat_cache{$token} = $first_script;
		return $first_script;
		}

	my $otoken = $token;
	my $category = '';
	my %cat_seen = ();
	my %mod_seen = ();
	my %sep_seen = ();
	my $modifier = ''; # separators at the front, modifiers at the back

	# remove invisibles and weird whitespace before categorizing
	$token = find_and_label($token, \%mod_seen,
		'tab',  qr/\t/,
		'cr',   qr/\n/,
		'shy',  qr/\x{00AD}/,
		'zwsp', qr/\x{200B}/,
		'zwnj', qr/\x{200C}/,
		'zwj',  qr/\x{200D}/,
		'wj',   qr/\x{2060}/,
		'invis_sep', qr/\x{2063}/,
		'nnbsp', qr/\x{202F}/,
		'nbsp',  qr/[\x{FEFF}\x{00A0}]/,
		'var',   qr/[\x{FE00}-\x{FE0F}\x{E0100}-\x{E01EF}]/,
		'bidi',  qr/[\x{200E}\x{200F}\x{202A}\x{202B}\x{202C}\x{202D}]/,
		'bidi',  qr/[\x{202E}\x{2066}\x{2067}\x{2068}\x{2069}\x{061C}]/,
		);

	# look for tell-tale hints of IPA-ish-ness before we start stripping stuff out
	# identify, but don't delete.
	if ($token =~ /[$IPA_mods]|[lrn][̩̥]/) { $cat_seen{$IPA_ISH} = 1; }
	# Also look for signs of non-IPA-ish-ness—digits, capital letters, β or γ alone or
	# set-off by hypens or whatever. Also don't delete.
	if ($token =~ /[0-9\p{Lu}]|\b[βγ]\b/) { $cat_seen{$NON_IPA} = 1; }

	# some complicated all-consuming patterns
	#   chemical only if there is a number somewhere and at least two letters
	if ($token =~ /[\d₀-₉]/ && $token =~ /[A-Z].*[A-Z]/i && $token =~ s/^$chem_pat+$//) {
		$cat_seen{'chemical formula'} = 1;
		}

	# Check for some all-consuming custom categories before removing separators and
	# modifiers. Note that ＃ used in labels is not a normal hash mark (#)... but it
	# sorts nicely
	$token = find_and_label($token, \%cat_seen,
		'＃ hex',  qr/^0x[0-9A-F]+$/i, # bleeds measurements
		'coords', qr/^\d\d?'\d\d?(\.\d+)?[A-Z]?$/i,
		'coords', qr/^[A-Z]?\d\d?[º°]\d\d?(\.\d\d?)?('\d\d?[,.]\d\d?)?[A-Z]?$/i,
		'coords', qr/^\d\d?\.\d{3,}[NEWS]$/,

		'measurements', qr/^($num_pat)?($unit_pat_multi)$/,
		'measurements', qr/^($num_pat)($unit_pat)$/,
		'measurements', qr/^($unit_pat)[·‧]($unit_pat)$/i,
		'measurements', qr/^$num_pat[x'‘’]$num_pat($unit_pat)?$/i,
		'measurements', qr/^\d+[°º](\d+(['‘’]\d+)?)?$/i,
		'measurements', qr/^v[0-9.]+$/i,

		'＃ ordinals',    qr/^(№|n\.?[ªº])\d+$/i,
		'＃ decimals',    qr/^[+-]?\d+(,\d{3})*\.\d+$/,
		'＃ percentages', qr/^[+-]?\d+(,\d{3})*(\.\d+)?%$/,
		'＃ numbers with digit groups', qr/^[+-]?\d{1,3}\,(\d\d\d,)*\d\d\d(\.\d+)?$/,
		'＃ numbers with digit groups', qr/^[+-]?\d{1,3}\.(\d\d\d,)*\d\d\d(\,\d+)?$/,
		'＃ numbers with digit groups', qr/^[+-]?\d{1,2}\,(\d\d,)*\d\d\d(\.\d+)?$/,
		'＃ numbers with digit groups', qr/^[+-]?\d{1,2}\.(\d\d,)*\d\d\d(\,\d+)?$/,
		'file types',   qr/^(\S+\.)+$file_type_pat$/i,
		'acronyms',     qr/^([A-Z]\.)+[A-Z]\.?$/,
		'acronym-like', qr/^([A-Z]\.)+[A-Z]\.?$/i,
		'name-like',    qr/^(\p{Lu}\.){1,3}\p{Lu}\p{L}{2,}$/,
		'name-like',    qr/^(Mr|Dr|Ms|Mrs|St)\.(\p{Lu}\.){0,3}\p{Lu}\p{L}{2,}$/,
		'web domains',  qr/^www\.([a-z0-9-]+\.)+[a-z0-9-]{2,3}$/i,
		'web domains',  qr/^([a-z0-9-]+\.)+$tld_pat$/i,
		'web domains',  qr/^([a-z0-9-]+\.)+(co|com|edu|gov|net|org|mil)\..{2,3}$/i,
		'punctuation',  qr/^\p{Punctuation}+$/,
		);

	#   ID-like only if there are both numbers and digits
	if ($token =~ /[A-Z]/ && $token =~ /[0-9]/ && $token =~ s/^[A-Z0-9-]+$//) {
		$cat_seen{'ID-like'} = 1;
		}

	# remove common "extras" before categorizing
	$token = find_and_label($token, \%mod_seen,
		'$',     qr/\$+$/,
		'&',     qr/&+$/,
		'apos',  qr/['‘’]/,
		'dquot', qr/\\?["“”]/,
		'mod',   qr/\p{Block: Modifier_Letters}/,
		'combo', qr/\p{Block: Combining_Diacritical_Marks}/,
		);

	# identify and remove separators
	while ($token =~ s/([$sep_pat])//) {
		$sep_seen{$seps{$1}} = 1;
		}

	# ID some custom categories
	$token = find_and_label($token, \%cat_seen,
		# all-consuming custom categories
		$TONAL,       qr/^[$tone_incl_pat]*[$tone_id_pat][$tone_incl_pat]*$/i,
		'＃ integers', qr/^[+-]?\d+$/,
		'＃ ordinals', qr/^\d*(1st|2nd|3rd|\dth|\d[ªº])$/i,
		'fractions',  qr/^[+-]?\d+[⁄\/]\d+$/i,
		'fractions',  qr/^[+-]?\d*([¼-¾⅐-⅞↉]+|⅟\d+)$/i,
		'Math Latin', qr/[𝐀-𝚥ℎℬℰℱℋℐℒℳℛℓℯℊℴℭℌℑℜℨℂℍℕℙℚℝℤ]/i,
			# some characters are not in the expected block: math italic h; script
			# BEFHILMRlego; frak CHIRZ; double-struck CHNPQRZ

		# additional partial-match custom categories
		'Unicode',       qr/\\u[0-9A-F]{4}/i,
		'URL-encoded',   qr/([0-9A-F]{2}%)+/i,
		'known symbols', qr/[ℏℵµ©℗®™℠]/,
		$IPA_GREEK,      qr/[θβχγ]/,
		$IPA_ISH,        qr/\p{IPA_Extensions}|\p{Phonetic_Ext}|\p{Phonetic_Ext_Sup}|[$IPA_chars]/,

		# unicode blocks that don't get identified
		'Currency',         qr/[\x{20A0}-\x{20C0}]/,
		'Arrows',           qr/[\x{2190}-\x{21FF}\x{27F0}-\x{27FF}\x{2900}-\x{297F}]/,
		'Math Operators',   qr/[\x{2200}-\x{22FF}\x{2A00}-\x{2AFF}]/,
		'Misc Symbols',     qr/[\x{2300}-\x{23FF}\x{2600}-\x{26FF}]/,
		'Geometric Shapes', qr/[\x{25A0}-\x{25FF}]/,
		'Dingbats',         qr/[\x{2700}-\x{27BF}]/,
		'Math Misc',        qr/[\x{27C0}-\x{27EF}\x{2980}-\x{29FF}]/,
		'Braille',          qr/[\x{2800}-\x{28FF}]/,
		'Han',              qr/[\x{4E00}-\x{9FFF}]/,
		'Fullwidth Latin',  qr/[\x{FF01}-\x{FF60}\x{FFE0}-\x{FFE6}]/,
		'Halfwidth CJK',    qr/[\x{FF61}-\x{FFDC}\x{FFE8}-\x{FFEE}]/,
		'Hanifi Rohingya',  qr/[\x{10D00}-\x{10D3F}]/,
		'Masaram Gondi',    qr/[\x{11D00}-\x{11D59}]/,
		'Gunjala Gondi',    qr/[\x{11D60}-\x{11DA9}]/,
		'Hentaigana',       qr/[\x{1B002}-\x{1B11E}\x{1B100}-\x{1B11E}]/,
		'Hiragana',         qr/[\x{1B11F}\x{1B150}-\x{1B152}]/,
		'Katakana',         qr/[\x{1B120}-\x{1B122}\x{1B164}-\x{1B167}]/,
		'Tangut',           qr/[\x{17000}-\x{18AFF}]/,
		'Math Greek',       qr/[\x{1D6A8}-\x{1D7CB}]/,
		'Math Numbers',     qr/[\x{1D7CE}-\x{1D7FF}]/,
		'Game Pieces',      qr/[\x{1F000}-\x{1F0FF}\x{1FA00}-\x{1FA6F}]/,
		'Flags (Regional Indicators)', qr/[\x{1F1E6}-\x{1F1FF}]/,
		'Misc Symbols',     qr/[\x{1F300}-\x{1F5FF}\x{1F900}-\x{1F9FF}\x{1FA70}-\x{1FAFF}]/,
		'Emoticons',        qr/[\x{1F600}-\x{1F64F}]/,
		'Han',              qr/[\x{20000}-\x{2EBEF}\x{2F800}-\x{2FA1F}\x{30000}-\x{3134F}]/,

		# hack some language bits that don't play nice
		'Arabic',     qr/\p{Block: Arabic}|\p{Arabic_Ext_A}|\p{Arabic_Supplement}|\p{Arabic_Presentation Forms-A}|\p{Arabic_Presentation Forms-B}/,
		'Cyrillic',   qr/[\x{0483}-\x{0489}]/,
		'Devanagari', qr/[\p{Devanagari}\x{0951}\x{0952}]/,
		$HIRA_KATA,   qr/[ー゠ｰ\x{3099}-\x{309C}\x{FF9E}\x{FF9F}]/,
		);

	# any digits left are just misc "numbers"
	$token = find_and_label($token, \%mod_seen, 'numbers', qr/\d/);

	# identify all the remaining characters
	foreach my $char (split(/|/, $token)) {
		$charscript_cache{$char} ||= charscript(ord($char));
		my $cat = $charscript_cache{$char};
		if ($cat eq 'Common' || $cat eq 'Inherited' || $cat eq 'Unknown') {
			# Common bad--we probably failed to identify something
			$token_cat_cache{$otoken} = '  unknown';
			return $token_cat_cache{$otoken};
			}
		else {
			$cat_seen{$cat} = 1;
			}
		}

	# clean up categories

	# I <?> Unicode — convert "Unicode" to "Unicode/Encoded Script"
	if ($cat_seen{'Unicode'}) {
		while ($otoken =~ /((\\u[A-F0-9]{4})+)/g) {
			my $ucat = defrag($1, 1);
			$ucat =~ s/^mixed-//;
			foreach my $uc (split(/-/, $ucat)) {
				$cat_seen{'Unicode/'.$uc} = 1;
				}
			}
		delete $cat_seen{'Unicode'};
		}

	# H/K isn't ambiguous if we have H or K
	if ($cat_seen{'Hiragana'} || $cat_seen{'Katakana'}) { delete $cat_seen{$HIRA_KATA}; }

	# If probably not IPA, delete IPA-ish and convert IPA-Greek to just Greek
	if ($cat_seen{$NON_IPA}) {
		delete $cat_seen{$IPA_ISH};
		if ($cat_seen{$IPA_GREEK}) {
			delete $cat_seen{$IPA_GREEK};
			$cat_seen{$GREEK} = 1;
			}
		delete $cat_seen{$NON_IPA};
		}

	# If there is other Greek, ignore "IPA-Greek"
	if ($cat_seen{$GREEK}) { delete $cat_seen{$IPA_GREEK}; }

	# IPA-Greek + Latin = IPA-ish
	if ($cat_seen{$IPA_GREEK} && $cat_seen{$LATIN}) { $cat_seen{$IPA_ISH} = 1; }

	# only one transcription system at a time
	if ($cat_seen{$TONAL}) { delete $cat_seen{$IPA_ISH}; }

	if ($cat_seen{$IPA_ISH} || $cat_seen{$TONAL}) {
		# only allowed if no other categories (ignoring Latin and IPA-like Greek)
		my $cat_count = scalar(keys %cat_seen);
		if ($cat_seen{$LATIN}) { $cat_count--; }
		if ($cat_seen{$IPA_GREEK}) { $cat_count--; }
		if ($cat_count > 1) {
			delete $cat_seen{$IPA_ISH};
			delete $cat_seen{$TONAL};
			}
		}

	if ($cat_seen{$IPA_ISH} || $cat_seen{$TONAL}) {
		# we (still) have a transcription, making some other stuff redundant
		delete $cat_seen{$LATIN};
		delete $cat_seen{$IPA_GREEK};
		delete $mod_seen{'apos'};
		delete $sep_seen{'period'};
		}
	elsif ($cat_seen{$IPA_GREEK}) {
		# no transcription, so "IPA-Greek" is just Greek
		delete $cat_seen{$IPA_GREEK};
		$cat_seen{$GREEK} = 1;
		}

	# build up the modifier list...
	$modifier = join('+', '', sort keys %mod_seen);

	# ... and add separators
	my @seps = keys %sep_seen;
	if (1 == @seps) {
		$modifier = ", $seps[0]-sep" . $modifier;
		}
	elsif (1 < @seps) {
		$modifier = ', mixed-sep' . $modifier;
		}

	# build the category label and return
	my @cats = keys %cat_seen;
	if (0 == @cats) { # no category is 'empty' (possibly + modifiers)
		$category = 'empty';
		}
	elsif (1 == @cats) {
		$category = $cats[0];
		}
	else { # more than one category is 'mixed'
		$category = ' mixed-' . join('-', sort @cats);
		}

	# Make charscript category_names more readable
	$category =~ s/_(.)/ \u$1/g;

	$category .= $modifier;

	# memoize!
	$token_cat_cache{$otoken} = $category;

	return $category;
	}

###############
# Take a string, a hashref, and an array of regex/label pairs. Find
# substrings matching the regex in the string, delete them, and add
# the corresponding label to the hash.
#
sub find_and_label {
	my ($str, $hashref, @regex_label_pairs) = @_;

	while (length($str) && @regex_label_pairs) {
		my ($label, $regex) = splice(@regex_label_pairs, 0, 2);
		if ($str =~ s/$regex//g) {
			$hashref->{$label} = 1;
			}
		}
	return $str;
	}

###############
# Add color highlights for Latin, Greek, Cyrillic and other scripts
# to highlight potential homoglyphs and make mixed script tokens
# easier to read
#
sub color_scripts {
	my ($str) = @_;

	my $skipLatin = 0;

	foreach my $script ( @script_colors ) {
		my ($s_name, $s_pat, $s_class, $s_color) = @$script;
		if ($skipLatin && $s_name =~ /Latin/) { next; }
		if ($str =~ s/($s_pat)/<span class=$s_class title='$s_name'>$1<\/span>/g &&
				$s_name eq 'Unicode') {
			$skipLatin = 1;
			}
		}

	return $str;
	}

###############
# show invisibles
#
sub show_invisibles {
	my ($str) = @_;

	$str =~ s/($invis_pat)/"<span class=invis title='$invis_desc{$1}'>$invis_symbol{$1}<\/span>"/eg;

	return $str;
	}

###############
# print key to invisibles characters, script colors
#
sub print_highlight_key {
	print_section_head('Invisibles and Script Colors');

	print_table_head_class('vcent',
		'symbol', 'invisible chars', '',
		'symbol', 'invisible chars', '',
		'color', 'script', '', 'color', 'script');
	print_table_row([show_invisibles("\t"), 'tab',
		'', show_invisibles("\x{200E}"), 'LTR bidi (200E, 202A, 202D, 2066)',
		'', color_scripts('বাংলা'), 'Bengali',
		'', color_scripts('อักษรไทย'), 'Thai',
		], 'key');
	print_table_row([show_invisibles("\x{00AD}"), 'soft-hyphen (00AD)',
		'', show_invisibles("\x{200F}"), 'RTL bidi (200F, 202B, 202E, 2067, 061C)',
		'', color_scripts('Кириллица'), 'Cyrillic',
		'', color_scripts('\uFFFD'), 'Unicode',
		], 'key');
	print_table_row([show_invisibles("\x{200C}"), 'non-joiner (200C, 2063)',
		'', show_invisibles("\x{2068}"), 'first strong isolate bidi (2068)',
		'', color_scripts('देवनागरी'), 'Devanagari',
		'', color_scripts('あ가កᎹیא'), 'unlabelled',
		], 'key');
	print_table_row([show_invisibles("\x{200D}"), 'joiner (200D)',
		'', show_invisibles("\x{2069}"), 'pop bidi (2069, 202C)',
		'', color_scripts('Ελληνικά'), 'Greek'
		], 'key');
	print_table_row([show_invisibles("\x{FE00}"), 'variation selector<br>(FE00-FE0F, E0100-E01EF)',
		'', show_invisibles("\x{200B}"), 'whitespace (200B, 202F, FEFF, 00A0)',
		'', color_scripts('Latin'), 'Latin',
		], 'key');

	print_table_foot();

	return;
	}

###############
# Print a set of samples for speaker review
#
sub speaker_sample {
	my ($desc, @samples) = @_;
	print "$desc$cr$cr\n";
	print_table_head();
	foreach my $aref (@samples) {
		my ($final, $token_count, $common, $type_cnt) = @$aref;
		my $the_mapping = $mapping{$final}{new};
		$the_mapping = show_invisibles($the_mapping);
		print_table_row(["$final", "$the_mapping"], 'dirAuto');
		}
	print_table_foot();
	print $cr;
	return;
	}

###############
# Shuffle an array in place
#
sub shuffle {
	my $array = shift;
	my $i = @$array;
	while (--$i) {
		my $j = int rand($i+1);
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
# set difference of two arrays, A \ B
# returns array of items in A that are not in B
#
sub set_diff {
	my ($aref, $bref) = @_;
	my %bseen = map { $_ => 1 } @$bref;
	return grep { ! $bseen{$_} } @$aref;
	}

###############
# Add commas to long numbers
#
sub comma {
	my ($num) = @_;
	if (!defined $num) { return 0; }
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
	return '0%';
	}

###############
# Annotate a \u encoded string with its real characters
#
# cat_only: just give me the category/ies!
#
sub defrag {
	my ($str, $cat_only) = @_;
	my $defragged = $str;
	$defragged =~ s/((\\u[A-F0-9]{4})+)/defragger($1)/eig;
	if ($cat_only) {
		my $cat = token_category($defragged);
		$cat =~ s/^\s+|\s+$//g;
		return $cat;
		}
	return "$defragged ($str)";
	}

sub defragger {
	my ($str) = @_;
	my @bytes = map {hex($_)} grep {$_} split(/\\u/, $str);
	for (my $i = 0; $i < @bytes; $i++) {
		if ($bytes[$i] < 0xD800) {
			$bytes[$i] = chr($bytes[$i]);
			}
		elsif ($i + 1 < @bytes && $bytes[$i + 1] >= 0xDC00) {
			my $hi = $bytes[$i];
			my $lo = $bytes[$i + 1];
			$bytes[$i] = '';
			$i++;
			my $uni = 0x10000 + ($hi - 0xD800) * 0x400 + ($lo - 0xDC00);
			$bytes[$i] = chr($uni);
			}
		else {
			$bytes[$i] = sprintf("\\u%X", $bytes[$i]);
			}
		}
	return join('', grep {$_} @bytes);
	}
