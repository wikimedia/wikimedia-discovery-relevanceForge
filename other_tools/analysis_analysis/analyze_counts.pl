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

my ($file) = @ARGV;
my $linecnt = 0;
my %final_count = ();
my %reverse = ();

*STDERR->autoflush();

binmode(STDOUT, ':encoding(UTF-8)');
open(FILE, '<:encoding(UTF-8)', $file);

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

	my $json = `curl -s localhost:9200/wiki_content/_analyze?pretty -d '{"analyzer": "text", "text" : "$escline" }'`;
	$json = decode_utf8($json);

	if ($json =~ /"error" :\s*{\s*"root_cause" :/s) {
		print STDERR "\n_analyze error (somewhere on lines $start_linecnt-$linecnt):\n$json\n";
		exit;
		}

	my %tokens = ();
	my $hs_offset = 0;  # offset to compensate for errors caused by high-surrogate characters
	my $token;
	my $start;
	my $end;
	my $offset;
	foreach my $jline (split(/\n\s*/, $json)) {
		if ($jline =~ /^"token" : "(.*)",$/) {
			$token = $1;
			}
		elsif ($jline =~ /^"start_offset" : (\d+),$/) {
			$start = $1 - $hs_offset;
			# handle rare UTF-16 & UTF-32 Chinese characters
			$offset = ( $token =~ s/\\u(D8[0-9A-F]{2})/ pack 'U*', hex($1) /eg );
			$hs_offset += $offset;
			$token =~ s/\\u([0-9A-F]{4})/ pack 'U*', hex($1) /eg;
			}
		elsif ($jline =~ /^"end_offset" : (\d+),$/) {
			$end = $1 - $hs_offset;
			next if $offset;
			my $otoken = substr($line, $start, $end-$start);
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

print "original tokens mapped to final tokens\n";
foreach my $otoken (sort keys %final_count) {
	print "$otoken\n";
	foreach my $mapto (sort keys %{$final_count{$otoken}}) {
		print "\t$final_count{$otoken}{$mapto}\t$mapto\n";
		}
	}

print "\n";

print "final tokens mapped to original tokens\n";
foreach my $token (sort keys %reverse) {
	print "$token\n";
	foreach my $otoken (sort keys %{$reverse{$token}}) {
		print "\t$reverse{$token}{$otoken}\t$otoken\n";
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

