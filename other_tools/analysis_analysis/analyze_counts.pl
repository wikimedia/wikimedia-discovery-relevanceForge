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

our ($opt_a, $opt_d, $opt_h, $opt_i, $opt_p, $opt_t, $opt_1, $opt_2);
getopts('a:d:h:i:p:t:12');

my %default_config = (
	'host' => 'localhost',
	'port' => '9200',
	'index' => 'my_wiki_content',
	'analyzer' => 'text',
	'tag' => 'baseline',
	);

# -h host, -p port, -i index, -a analyzer
my $host = $opt_h || $default_config{'host'};
my $port = $opt_p || $default_config{'port'};
my $index = $opt_i || $default_config{'index'};
my $analyzer = $opt_a || $default_config{'analyzer'};
my $tag = $opt_t || $default_config{'tag'};
my $dir = $opt_d;

# -1: prep 1-token-per-line output for external stemmer
my $ext_stem_out = $opt_1;
# -2: read 1-token-per-line input from external stemmer
my $ext_stem_in = $opt_2;

# either external stemmer input and two input files or just one input file
# can't have external stemmer input and output at the same time
# (that would just copy the input to the output very inefficiently)

if ( $ext_stem_in && $ext_stem_out ) {
	usage("Can't have external stemmer input and output at the same time.");
	exit;
	}

if ( $ext_stem_in && scalar(@ARGV) != 2 ) {
	usage('External stemmer input requires token counts file and stemmed tokens file.');
	exit;
	}

if ( ! $ext_stem_in && scalar(@ARGV) != 1 ) {
	usage('Input text file required.');
	exit;
	}

if ( ! -e $ARGV[0] ) {
	usage("File $ARGV[0] not found.");
	exit;
	}

if ( $ARGV[1] && ! -e $ARGV[1] ) {
	usage("File $ARGV[1] not found.");
	exit;
	}

# input and output files
my $input_text_file = '';   # input file with plain text, like WP articles
my $counts_file = '';       # output file with mapping between original and final tokens

my $tok_counts_file = '';   # input/output file with original tokens and counts
my $tok_stem_file = '';     # input/output file with one normalized token per line

my $pipe_esc = chr(3);      # used to escape pipe characters in counts file

my $line_cnt = 0;
my %final_count = ();
my %reverse = ();

if ($ext_stem_out) {
	# 1-token-per-line output for external stemmer
	$input_text_file = shift @ARGV;

	# add file type labels and tag to input name
	$tok_counts_file = $input_text_file;
	$tok_counts_file =~ s/\.txt$//;
	$tok_stem_file = $tok_counts_file;
	$tok_counts_file .= ".tok-count.$tag.txt";
	$tok_stem_file .= ".tok-unstemmed.$tag.txt";
	}
elsif ($ext_stem_in) {
	# 1-token-per-line input from external stemmer
	$tok_counts_file = shift @ARGV;
	$tok_stem_file = shift @ARGV;

	# strip .tok_count.<old_tag> from input name, add file type label and tag
	$counts_file = $tok_stem_file;
	$counts_file =~ s/\.txt$//;
	$counts_file .= ".counts.$tag.txt";
	}
else {
	# regular counting
	$input_text_file = shift @ARGV;

	# add file type label and tag to input name
	$counts_file = $input_text_file;
	$counts_file =~ s/\.txt$//;
	$counts_file .= ".counts.$tag.txt";
	}

if ($dir) {
	$counts_file =~ s!.*/!$dir/!;
	$tok_counts_file =~ s!.*/!$dir/!;
	$tok_stem_file =~ s!.*/!$dir/!;
	}

*STDERR->autoflush();

binmode(STDOUT, ':encoding(UTF-8)');

if ($ext_stem_in) {
	# load externally stemmed data
	open(TOKCOUNTSFILE, '<:encoding(UTF-8)', $tok_counts_file);
	open(TOKSTEMFILE, '<:encoding(UTF-8)', $tok_stem_file);

	while (my $token = <TOKSTEMFILE>) {
		chomp $token;
		my @counts = split(/\t/, <TOKCOUNTSFILE>);
		chomp $counts[-1];

		$line_cnt++;
		if ($line_cnt % 1000 == 0) {
			print STDERR '.';
			if ($line_cnt % 50_000 == 0) {
				print STDERR " $line_cnt\n";
				}
			}

		next if $token eq '';

		while (@counts) {
			my $otoken = shift @counts;
			my $cnt = shift @counts;
			$final_count{$otoken}{$token} += $cnt;
			$reverse{$token}{$otoken} += $cnt;
			}
		}

	close TOKCOUNTSFILE;
	close TOKSTEMFILE;
	}
else {
	# load text file
	open(INPUTTEXTFILE, '<:encoding(UTF-8)', $input_text_file);

	my $prev_line = '';
	my $new_line = '';

	while (my $line = $new_line || <INPUTTEXTFILE>) {
		chomp $line;
		$line_cnt++;
		my $line_len = length($line);

		my $start_line_cnt = $line_cnt;
		$new_line = <INPUTTEXTFILE>;
		chomp $new_line if defined $new_line;
		my $new_line_len = length($new_line);

		# ~30x speed up to process 100 lines at a time.
		# Additional 25%+ speed up by allowing as many lines as we can, up
		# to the 30K char limit (beyond that, stuff starts getting lost)
		while (defined $new_line) {
			if ($line_len + 1 + $new_line_len < 30_000) {
				$line .= ' ' . $new_line;
				$line_len += length($new_line) + 1;
				$line_cnt++;

				if ($line_cnt % 1000 == 0) {
					print STDERR '.';
					if ($line_cnt % 50_000 == 0) {
						print STDERR " $line_cnt\n";
						}
					}

				$new_line = <INPUTTEXTFILE>;
				chomp $new_line if defined $new_line;
				$new_line_len = length($new_line);
				}
			else {
				last;
				}
			}

		my $esc_line = $line;
		$esc_line = urlize($esc_line);

		my $json = `curl -H 'Content-Type: application/json' -s $host:$port/$index/_analyze?pretty -d '{"analyzer": "$analyzer", "text" : "$esc_line" }'`;
		$json = decode_utf8($json);

		if ($json =~ /"error" :\s*{\s*"root_cause" :/s) {
			print STDERR "\n_analyze error (somewhere on lines $start_line_cnt-$line_cnt, len = ", $line_len, "/", length($esc_line), "):\n$json\n";
			exit;
			}

		# Elastic interprets high surrogate/low surrogate pairs as two characters.
		# Add ^A as padding after high-value Unicode characters so offsets are correct.
		my $pad = chr(1);
		$line =~ s/(\p{InSurrogates})/$1$pad/g;

		my %tokens = ();
		my $token;
		my $start;
		my $end;

		foreach my $jline (split(/\n\s*/, $json)) {
			if ($jline =~ /^"token" : "(.*)",$/) {
				$token = count_esc($1);
				}
			elsif ($jline =~ /^"start_offset" : (\d+),$/) {
				$start = $1;
				}
			elsif ($jline =~ /^"end_offset" : (\d+),$/) {
				$end = $1;
				my $otoken = count_esc(substr($line, $start, $end - $start));
				$otoken =~ s/$pad//g; # remove any ^A padding from actual tokens
				$tokens{"$start|$end|$otoken"}{$token}++;
				}
			}

		foreach my $info (keys %tokens) {
			my ($s, $e, $otoken) = split /\|/, $info, 3;
			my $mapto = join('|', sort keys %{$tokens{$info}});
			foreach my $token (keys %{$tokens{$info}}) {
				$final_count{$otoken}{$mapto} += $tokens{$info}{$token};
				$reverse{$token}{$otoken} += $tokens{$info}{$token};
				}
			}
		}

	close INPUTTEXTFILE;
	}

unless ($line_cnt % 50_000 == 0) {
	print STDERR " $line_cnt";
	}
print STDERR "\n";

if ($ext_stem_out) {
	# 1-token-per-line output for external stemmer
	open(TOKCOUNTSFILE, '>:encoding(UTF-8)', $tok_counts_file);
	open(TOKSTEMFILE, '>:encoding(UTF-8)', $tok_stem_file);
	foreach my $token (sort keys %reverse) {
		print TOKSTEMFILE "$token\n";
		print TOKCOUNTSFILE join("\t",  map {"$_\t$reverse{$token}{$_}"} sort keys %{$reverse{$token}}), "\n";
		}
	close TOKCOUNTSFILE;
	close TOKSTEMFILE;
	exit;
	}
else {
	# regular output
	open(COUNTSFILE, '>:encoding(UTF-8)', $counts_file);

	print COUNTSFILE "original tokens mapped to final tokens\n";
	foreach my $otoken (sort keys %final_count) {
		print COUNTSFILE count_unesc($otoken), "\n";
		foreach my $mapto (sort keys %{$final_count{$otoken}}) {
			print COUNTSFILE "\t$final_count{$otoken}{$mapto}\t$mapto\n";
			}
		}

	print COUNTSFILE "\n";

	print COUNTSFILE "final tokens mapped to original tokens\n";
	foreach my $token (sort keys %reverse) {
		print COUNTSFILE count_unesc($token), "\n";
		foreach my $otoken (sort keys %{$reverse{$token}}) {
			print COUNTSFILE "\t$reverse{$token}{$otoken}\t$otoken\n";
			}
		}

	close COUNTSFILE;
	}

exit;

###############
# add pipe escape char following pipes
#
sub count_esc {
	my ($str) = @_;
	$str =~ s/\|/\|$pipe_esc/g;
	return $str;
	}

###############
# remove pipe escape char following pipes
#
sub count_unesc {
	my ($str) = @_;
	$str =~ s/\|$pipe_esc/\|/g;
	return "$str";
	}

sub urlize {
	my ($rv) = @_;
	$rv =~ s/\x{0}/ /g;
	$rv =~ s/(["\\])/\\$1/g;
	$rv =~ s/'/'"'"'/g;
	$rv =~ s/\t/\\t/g;
	return $rv;
}

# user-defined character class for high-value Unicode characters
sub InSurrogates {
        return <<END;
10000	FFFCFF
END
    }

###############
# Show usage
#
sub usage {
	my ($msg) = @_;
	if ($msg) {
		print "Error: $msg\n\n";
		}
print <<USAGE;
usage: $0  [-t <tag>] [-d <dir>]
    [-h <host>] [-p <port>] [-i <index>] [-a <analyzer>]
    [-1] <input_file>.txt | -2 <input_counts>.txt <input_stemmed>.txt

    -t <tag>   tag added to the names of output files (default: $default_config{'tag'})
                 e.g., <input_file>.counts.<tag>.txt
    -d <dir>   directory output files should be written to
                 (default: same as <input_file>.txt or <input_stemmed>.txt)

    -h <host>  specify host for analysis (default: $default_config{'host'})
    -p <port>  specify port for analysis (default: $default_config{'port'})
    -i <index> specify index for analysis (default: $default_config{'index'})
    -a <analyzer>
               specify analyzer for analysis (default: $default_config{'analyzer'})

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

USAGE
	return;
	}
