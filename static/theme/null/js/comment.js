$(function() {
	var $window = $(window);
	var complete = false;
	var loading = true;
	var $commentlist = $('#commentlist>ol');
	var $comment = $('#comment'); // the textarea of the editor
	var $temp = $('<ol/>'); // be used to temporarily store the generated comments
	var $comment_float_list = $('<ol class="commentlist comment-float-list"/>').appendTo(document.body).hide(); // be used to temporarily store the float quoted comment
	var $commentform = $('#commentform');
	var allow_comment = $commentform.length; // if the form is not exist, then it's not allowed to comment
	var next_cursor = '';
	var comment_order = true;
	var $comment_order_asc = $('#comment-order-asc');
	var $comment_order_desc = $('#comment-order-desc');
	var is_admin = typeof(comment_delete_url) != 'undefined'; // only the page of admin's defines comment_delete_url
	var $del_comment_button = $('<span id="del-comment-button">Confirm deletion</span>');
	var comment_fetch_url = home_path + 'comment/json/'+ article_id + '/';
	var $more_hint = $('#more-hint');
	var $wap = $('a[href="/wap/"]'); // "/wap/" should be the BLOG_WAP_RELATIVE_PATH in setting.py

	if ($wap.length) {
		$wap[0].href = '/wap' + location.pathname;
	}

	function generate_comment(comment) {
		var html = [];
		html.push('<li><p class="comment-author"><img src="');
		html.push(comment.img);
		html.push('?s=48&amp;d=monsterid" class="avatar" height="48" width="48"/><cite><a id="comment-id-');
		html.push(comment.id);
		if (comment.url) { // display user's site
			html.push('" href="');
			html.push(comment.url);
		}
		html.push('">');
		html.push(comment.user_name);
		html.push('</a></cite>');
		var uas = comment.ua;
		if (uas) { // display user agent infomation
			html.push('<span class="ua">');
			for (var i = 0, ua; i < uas.length; ++ i) {
				ua = comment.ua[i];
				html.push('<img src="/img/ua/');
				html.push(ua.replace(/ /g, '-'));
				html.push('.png" alt="');
				html.push(ua);
				html.push('" title="');
				html.push(ua);
				html.push('"/>');
			}
			html.push('</span>');
		}
		html.push('<br/><small><strong>');
		html.push(comment.time);
		html.push('</strong>');
		if (is_admin) { // display administration links for admin
			html.push(' <span class="edit-user"><a href="');
			html.push(user_edit_url);
			html.push(comment.id);
			html.push('/">[Profile]</a></span> <span class="edit-comment"><a href="');
			html.push(comment_edit_url);
			html.push(comment.id);
			html.push('/">[Edit]</a></span> <span class="del-comment">[Delete]</span>');
		}
		html.push('</small></p><div class="commententry" id="commententry-');
		html.push(comment.id);
		html.push('"><div>');
		html.push(comment.content);
		html.push('</div></div><a class="comment-reply-link" href="#respond">reply</a></li>');
		return html.join("");
	}

	function bind_events_for_comment($html, id, user_name) {
		$html.find('a.comment-reply-link').click(function() { // when click the reply button
			reply(id, user_name);
		});
		$html.find('a[href^="#comment-id-"]').hover(function(ev) { // the A element whose URL begin with #comment-id-
			var comment_author_id = $(this).attr('href').substr(12); // the comment id starts from the 13th
			var ref_comment_link = $commentlist.find('#comment-id-' + comment_author_id); // the quoted comment
			if (ref_comment_link.length) {
				$comment_float_list.css({
					'top': ev.pageY,
					'left': ev.pageX + 50
				}).append(ref_comment_link.parent().parent().parent().clone().find('p.reply').remove().end()).fadeTo(1000, 0.9);
				// display a float comment
				// ref_comment_link.parent().parent().parent() is the LI element which contains the quoted comment
				// if your theme changes the DOM structure, you can find its parents until meet a LI element
				// eg: ref_comment_link.parentsUntil('li').last().parent()
			}
		}, function() {
			$comment_float_list.hide().empty(); // hide the float comment
		});
		$html.find('pre>code').each(function(i, e) {hljs.highlightBlock(e, '    ')}); // highlight the code element of comments
		if (is_admin) { // display confire delete button for admin
			$html.find('span.del-comment').data('id', id).hover(function(){
				$(this).append($del_comment_button);
			}, function(){
				$del_comment_button.detach();
			});
		}
	}

	//get relative articles
	function get_comment() {
		var url = comment_fetch_url;
		if (next_cursor) {
			url += next_cursor;
		}
		if (!comment_order) {
			url += '?order=desc'
		}

		$.ajax({
			'url': url,
			'dataType': 'json',
			'error': function(jqXHR, textStatus){
				if (textStatus == 'timeout') {
					get_comment();
				}
			},
			'success': function(json){
				next_cursor = json.next_cursor;
				if (next_cursor) {
					$more_hint.show();
				} else {
					complete = true;
					$more_hint.hide();
				}
				var comments = json.comments;
				var length = comments.length;
				if (length) {
					for (var index = 0; index < length; ++index) {
						var comment = comments[index];
						var $html = $(generate_comment(comment)).appendTo($temp);
						bind_events_for_comment($html, comment.id, comment.user_name);
					}
					$temp.children().unwrap().hide().appendTo($commentlist).slideDown(1000);
				}
				loading = false;
			},
			'timeout': 10000
		});
		_gaq.push(['_trackEvent', 'Comment', 'Load', article_id]);
	}

	get_comment();

	$.getJSON(home_path + 'relative/' + article_id, function(json) {
		var length = json ? json.length : 0;
		if (length) {
			var html = ['<ul>'];
			for (var index = 0; index < length; ++index) {
				var article = json[index];
				html.push('<li><a href="');
				html.push(home_path);
				html.push(article.url);
				html.push('">');
				html.push(article.title);
				html.push('</a></li>');
			}
			html.push('</ul>');
			$('#relative-articles').append(html.join('')).slideDown(1000, function(){
				$(this).find('li').animate({'padding-left': '2em'}, 1000);
			});
		}
	});
	_gaq.push(['_trackEvent', 'RelativeArticles', 'Load', article_id]);

	function reply(comment_id, comment_user) {
		if (!allow_comment) {return;}
		var comment = [$comment.val()];
		comment.push('[url=#comment-id-');
		comment.push(comment_id);
		comment.push(']@');
		comment.push(comment_user);
		comment.push('[/url]: ');
		setTimeout(function(){$comment.focus().val(comment.join(''));}, 100); // insert replied user and comment id in textarea
	}

	$('pre>code').each(function(i, e) {hljs.highlightBlock(e, '    ')}); // highlight the code element of the article

	if ($comment.length) {
		$comment.markItUp(BbcodeSettings);
		var submitting = false;
		var $bbcode = $commentform.find('#bbcode');
		$commentform.submit(function() {
			if (submitting) return false;
			submitting = true;
			var val = $.trim($comment.val());
			if (!val) {
				msgbbox('You should post it after write something.');
				submitting = false;
				return false;
			}
			var data = {'comment': val};
			if ($bbcode.attr('checked')) { // check whether enable BBCode
				data['bbcode'] = 'on';
			}
			$.ajax({
				'url': $commentform.attr('action'),
				'data': data,
				'dataType': 'json',
				'type': 'POST',
				'error': function(){
					submitting = false;
					msgbbox('Sorry, submit failed duo to unknown reason.');
				},
				'success': function(json){
					if (json.status == 200) {
						var comment = json.comment;
						var $html = $(generate_comment(comment));
						bind_events_for_comment($html, comment.id, comment.user_name);
						$html.hide().appendTo($commentlist).slideDown(1000); // append new comment
						$comment.val(''); // empty the textarea
						msgbbox('Thanks for your reply. Your comment will be displayed immediately after the cache expires.');
					} else {
						msgbbox(json.content);
					}
					submitting = false;
				},
				'timeout': 10000
			});
			_gaq.push(['_trackEvent', 'Comment', 'Reply', article_id]);
			return false;
		});
	}

	if (allow_comment) {
		$('#comments').find('a').click(function() {$comment.focus();});
	}

	$comment_order_asc.click(function() {
		$comment_order_asc.addClass('selected');
		$comment_order_desc.removeClass('selected');
		if (comment_order) {
			return;
		}
		loading = true;
		$commentlist.empty();
		comment_order = true;
		complete = false;
		next_cursor = '';
		get_comment();
	});

	$comment_order_desc.click(function() {
		$comment_order_desc.addClass('selected');
		$comment_order_asc.removeClass('selected');
		if (!comment_order) {
			return;
		}
		loading = true;
		$commentlist.empty();
		comment_order = false;
		complete = false;
		next_cursor = '';
		get_comment();
	});


	if (is_admin) {
		$del_comment_button.click(function() { // when click the confirm delete button
			var $parent = $del_comment_button.parent();
			var $comment_li = $parent.parent().parent().parent();
			$.ajax({
				'url': comment_delete_url + $parent.data('id') + '/',
				'dataType': 'json',
				'type': 'POST',
				'error': function(){
					msgbbox('Comment deleting failed duo to unknown reason.');
				},
				'success': function(json){
					if (json.status == 204) {
						$comment_li.slideUp('2000', function(){
							$del_comment_button.detach(); // remove the confirm delete button without delete its click event handler
							$comment_li.remove(); // remove deleted comment
						});
					} else {
						msgbbox(json.content);
					}
				},
				'timeout': 10000
			});
		});
	}

	$more_hint.find('a').click(function () {
		complete = true;
		$more_hint.hide();
	});

	$window.scroll(function(){ // load more comments when all the loaded comments has been displayed
		if (!complete && !loading && ($window.scrollTop() + $window.height() - $commentlist.offset().top - $commentlist.outerHeight() > 300)) {
			loading = true;
			get_comment();
		}
	});
});