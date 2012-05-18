(function(){
	var $scroller;
	var $body = $('body');
	var $html = $('html');
	if ($body.scrollTop()) {
		$scroller = $body;
	} else if ($html.scrollTop()) {
		$scroller = $html;
	} else {
		$body.scrollTop(1);
		if ($body.scrollTop()) { // check whether $body.scrollTop() is available in this browser
			$scroller = $body.scrollTop(0);
		} else {
			$scroller = $html;
		}
	}
	function scrollTo(top) {
		$scroller.animate({scrollTop: top < 0 ? 0 : top}, 1000);
	}
	$body.on('click', 'a[href^=#]', function(ev){ // only hook the click event of the A element whose URL is begin with #
		var hash = this.hash;
		if (hash) {
			var $hash = $(hash);
			if ($hash.length) {
				scrollTo($hash.offset().top);
				ev.preventDefault();
			}
		} else {
			scrollTo(0);
			ev.preventDefault();
		}
	});
})();