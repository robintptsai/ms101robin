$(function() {
	var $document = $(document);
	var $window = $(window);
	var $content = $('#content');
	var $loading = $('<div/>'); // be used to temporarily store the loaded articles
	var loading = false;
	var $next_url = $('#content>.post-nav>.previous>a');
	var next_url = '';
	var $no_more = $('<span class="no-more"><a href="javascript:;"><em>我看够了</em> 停止自动加载</a></span>');

	$no_more.find('a').click(function() {
		$window.unbind('scroll', load_more);
		$no_more.remove();
	});

	function set_next_url() {
		if ($next_url.length) {
			next_url = $next_url.attr('href');
		} else {
			$window.unbind('scroll', load_more);
			next_url = '';
		}
	}

	function load() {
		$loading.load(next_url + ' #content', function() {
			$next_url = $loading.find('.post-nav>.previous>a');
			set_next_url();
			$next_url.parent().after($no_more);
			$('#content>.post-nav').detach(); // delete the next page link of current page
			$loading.children().detach().children().hide().appendTo($content).slideDown(1000);
			loading = false;
		});
		_gaq.push(['_trackEvent', 'Page', 'Load', next_url]);
	}

	function load_more() {
		// load articles when scroll to the bottom of the page
		if (!loading && ($document.height() - $window.scrollTop() - $window.height() < 50)) {
			loading = true;
			load();
		}
	}

	$window.bind('scroll', load_more);
	set_next_url();
});