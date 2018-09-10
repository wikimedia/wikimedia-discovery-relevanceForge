var currentMousePos = { x: -1, y: -1 };
$( document ).ready( function() {

		var hash = decodeURIComponent(window.location.hash.substr(1)).trim();
		if ( hash ) {
				$("#querybox").val(hash);
				getComparison();
		}

		$("#querybox").keypress(function(e) {
				if ( e.which != 13 ) return;
				getComparison();
		} );
		$("#qweight").keypress(function(e) {
				if ( e.which != 13 ) return;
				getComparison();
		} );
		/*
		$("#qprop").keypress(function(e) {
				if ( e.which != 13 ) return;
				getComparison();
		} );
		*/
		$("#querybox").change(getComparison);
		$(document).mousemove(function(event) {
				currentMousePos.x = event.pageX;
				currentMousePos.y = event.pageY;
		});
});

getComparison = function() {
		let q = $("#querybox").val();
		window.location.hash = '#' + q;
		$("#loading_img").show();
		let url = "search_backend.php?query=" + encodeURIComponent(q);
		if ( $("#qweight").val() != "" ) {
				url += "&cirrusQualW=" + $("#qweight").val();
		}
		/*
		if ( $("#qprop").val() != "" ) {
				url += "&cirrusQualP=" + $("#qprop").val();
		}
		*/
		$.getJSON( url, null, display_comp );
}

display_comp = function( data ) {
		$("#loading_img").hide();
		$("#header").show();
		let left = $('.leftbox');
		let right = $('.rightbox');
		left.empty();
		right.empty();
		
		l = Math.max( data.left.length, data.right.length );
		for ( let i = 0; i < l; i++) {
				let box = document.querySelector("#comp_box").content;

				let leftBox = document.importNode(box, true)
				let rightBox = document.importNode(box, true)

				display_block( leftBox, data.left.length > i ? data.left[i] : null );
				display_block( rightBox, data.right.length > i ? data.right[i] : null );

				left[0].appendChild( leftBox );
				right[0].appendChild( rightBox );
		}
}

display_block = function( node, data ) {
		if ( data != null ) {
				node.querySelector('.titlelink').setAttribute('href', 'https://commons.wikimedia.org/wiki/'+data.title);

				imgNode = node.querySelector('.compboximg');
				imgNode.setAttribute('src', (data.imageinfo.length > 0 && data.imageinfo[0].thumburl) ? data.imageinfo[0].thumburl : 'https://upload.wikimedia.org/wikipedia/commons/5/59/Oxygen480-status-image-missing.svg');
				if ( data.titlesnippet != "" ) {
						node.querySelector('.tooltipfile').innerHTML = data.titlesnippet;
				} else {
						node.querySelector('.tooltipfile').innerHTML = data.titlesnippet;
				}
				node.querySelector('.tooltipsnippet').innerHTML = data.snippet;
				let tooltip = node.querySelector('.hiddentooltip');
				imgNode.onmouseover = function() {
						if ( tooltip.className == 'tooltip' ) {
								return;
						}
						tooltip.className = 'tooltip';
						tooltip.style.top = currentMousePos.y + 10;
						tooltip.style.left = currentMousePos.x + 10;
				}
				imgNode.onmouseout = function() {
						tooltip.className = 'hiddentooltip';
				}
		}
}
