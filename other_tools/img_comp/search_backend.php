<?php

$query = $_GET['query'];
$server1 = 'https://commons-defaults-relforge.wmflabs.org/w/api.php';
$server2 = 'https://commons-img-qual-relforge.wmflabs.org/w/api.php';

function get_results( $url, $query ) {
	$url .= '?action=query' .
		'&generator=search' .
		'&list=search' .
		'&gsrsearch=' . urlencode($query) .
		'&gsrnamespace=6' .
		'&gsrprop=snippet|categorysnippet|titlesnippet' . 
		'&gsrlimit=20' .
		'&srsearch=' . urlencode($query) .
		'&srnamespace=6' .
		'&srprop=snippet|categorysnippet|titlesnippet' . 
		'&srlimit=20' .
		'&prop=imageinfo' .
		'&iiprop=url' .
		'&iiurlwidth=600' .
		'&format=json' .
		'&formatversion=2';
	foreach( $_GET as $k => $v ) {
		if ( preg_match( '/^cirrus/', $k  ) ) {
			$url .= "&$k=$v";
		}
	}
	$ch = curl_init( $url );
	curl_setopt( $ch, CURLOPT_RETURNTRANSFER, true );
	curl_setopt( $ch, CURLOPT_CUSTOMREQUEST,  'GET' );
	$resp = curl_exec( $ch );
	$data = json_decode( $resp, JSON_OBJECT_AS_ARRAY );
	return $data;
}  

function munge( $data ) {
	if ( !isset( $data['query']['pages'] ) ) {
			return [];
	}

	$pages = [];
	foreach( $data['query']['pages'] as $p ) {
			$pages[$p['title']] = $p;
	}
	$results = [];
	foreach( $data['query']['search'] as $r ) {
			$r['imageinfo'] = $pages[$r['title']]['imageinfo'] ?? [];
			$results[] = $r;
	}
	return $results;
}

header('Content-Type: application/json');
print( json_encode( [ 
	'left' => munge(get_results( $server1, $query )) ?: [],
	'right' => munge(get_results( $server2, $query )) ?: [],
] ) );

