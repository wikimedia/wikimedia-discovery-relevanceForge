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

our ($opt_a, $opt_d, $opt_h, $opt_i, $opt_p, $opt_t);
getopts('a:d:h:i:p:t:');

# -h host, -p port, -i index, -a analyzer
my $host = $opt_h || 'localhost';
my $port = $opt_p || '9200';
my $index = $opt_i || 'wiki_content';
my $analyzer = $opt_a || 'text';

my $tag = $opt_t || 'baseline';
my $dir = $opt_d;

my ($file) = @ARGV;
my $linecnt = 0;
my %final_count = ();
my %reverse = ();

my $outfile = $file;
$outfile =~ s/\.txt$//;
$outfile .= ".counts.$tag.txt";

if ($dir) {
	$outfile =~ s!.*/!$dir/!;
	}

*STDERR->autoflush();

binmode(STDOUT, ':encoding(UTF-8)');
open(FILE, '<:encoding(UTF-8)', $file);
open(OUTFILE, '>:encoding(UTF-8)', $outfile);

while (my $line = <FILE>) {
	chomp $line;
	$linecnt++;

	my $start_linecnt = $linecnt;

	# ~30x speed up to process 100 lines at a time.
	my $linelen = length($line);
	foreach my $i (1..99) {
		my $newline = <FILE>;
		if ($newline) {
			chomp $newline;
			$line .= ' ' . $newline;
			$linecnt++;

			if ($linecnt % 1000 == 0) {
				print STDERR '.';
				if ($linecnt % 50_000 == 0) {
					print STDERR " $linecnt\n";
					}
				}

			# More than ~50K in one go causes errors, so stop at 30K
			$linelen += length($newline) + 1;
			if ($linelen > 30_000) {
				last;
				}

			}
		else {
			last;
			}
		}

	my $escline = $line;
	$escline = urlize($escline);

	my $json = `curl -s $host:$port/$index/_analyze?pretty -d '{"analyzer": "$analyzer", "text" : "$escline" }'`;
	$json = decode_utf8($json);

	if ($json =~ /"error" :\s*{\s*"root_cause" :/s) {
		print STDERR "\n_analyze error (somewhere on lines $start_linecnt-$linecnt):\n$json\n";
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
			$token = $1;
			}
		elsif ($jline =~ /^"start_offset" : (\d+),$/) {
			$start = $1;
			}
		elsif ($jline =~ /^"end_offset" : (\d+),$/) {
			$end = $1;
			my $otoken = substr($line, $start, $end-$start);
			$otoken =~ s/$pad//g; # remove any ^A padding from actual tokens
			$tokens{"$start|$end|$otoken"}{$token}++;
			}
		}

	foreach my $info (sort keys %tokens) {
		my ($s, $e, $otoken) = split /\|/, $info, 3;
		my $mapto = join('|', sort keys %{$tokens{$info}});
		$final_count{$otoken}{$mapto}++;
		foreach my $token (sort keys %{$tokens{$info}}) {
			$reverse{$token}{$otoken}++;
			}
		}
	}

close FILE;

unless ($linecnt % 50_000 == 0) {
	print STDERR " $linecnt";
	}
print STDERR "\n";

print OUTFILE "original tokens mapped to final tokens\n";
foreach my $otoken (sort keys %final_count) {
	print OUTFILE "$otoken\n";
	foreach my $mapto (sort keys %{$final_count{$otoken}}) {
		print OUTFILE "\t$final_count{$otoken}{$mapto}\t$mapto\n";
		}
	}

print OUTFILE "\n";

print OUTFILE "final tokens mapped to original tokens\n";
foreach my $token (sort keys %reverse) {
	print OUTFILE "$token\n";
	foreach my $otoken (sort keys %{$reverse{$token}}) {
		print OUTFILE "\t$reverse{$token}{$otoken}\t$otoken\n";
		}
	}

exit;

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
