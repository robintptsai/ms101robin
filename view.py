# -*- coding: utf-8 -*-

import logging
from re import compile as reg_compile

try:
	import json
except ImportError:
	import simplejson as json
from google.appengine.api import mail, memcache
import yui

from common import UserHandler, incr_counter, unquoted_cursor
from model import *
from setting import *


class HomePage(UserHandler):
	@yui.server_cache(ARTICLES_CACHE_TIME, True, True, True)
	def get(self):
		cursor = unquoted_cursor(self.GET['cursor'])
		articles, next_cursor = Article.get_articles_for_homepage(cursor)
		self.echo('home.html', {
			'articles': articles,
			'next_cursor': next_cursor,
			'title': BLOG_TITLE,
			'cursor': cursor,
			'page': 'home'
		})


class ArticlePage(UserHandler):
	def get(self, url):
		article = Article.get_article_by_url(path_to_unicode(url))
		if article and (article.published or self.request.is_admin):
			if self.is_spider():
				self.response.set_last_modified(article.mod_time)
			self.echo('article.html', {
				'article': article,
				'title': article.title,
				'page': 'article'
			})
			incr_counter('article_counter:%s' % article.key().id(), BLOG_ADMIN_RELATIVE_PATH + 'article_counter/')
		else:
			self.error(404)
			self.echo('error.html', {
				'page': '404',
				'title': "Can't find out this article",
				'h2': 'Oh, my god!',
				'msg': 'Something seems to be lost...'
			})


class RelativeArticlesJson(UserHandler):
	@yui.server_cache(ARTICLES_CACHE_TIME, False)
	@yui.client_cache(ARTICLES_CACHE_TIME, 'public')
	def get(self, id):
		self.set_content_type('json')
		relative_articles = Article.relative_articles(int(id), RELATIVE_ARTICLES)
		if not relative_articles:
			return

		relative_articles.sort(cmp=lambda x, y: cmp(x.hits + x.replies * 10, y.hits + y.replies * 10), reverse=True)
		article_list = []
		for article in relative_articles:
			article_list.append({
				'title': escape(article.title),
				'url': article.quoted_url()
			})
		self.write(json.dumps(article_list))

	def display_exception(self, exception):
		self.write(json.dumps({
			'status': 500,
			'content': 'The server has some error, you can try to refresh or report to administrator.'
		}))


class CommentPage(UserHandler):
	#@yui.server_cache(COMMENTS_CACHE_TIME)
	def get(self, id, cursor=None):
		article_id = int(id)
		article = Article.get_article_by_id(article_id) if article_id else None
		if article:
			(comments, next_cursor), users = Comment.get_comments_with_user_by_article_key(
				article.key(), cursor=unquoted_cursor(cursor))
			self.echo('comment.html', {
				'comments': comments,
				'next_cursor': next_cursor,
				'comment_users': users,
				'id': id,
			    'article': article,
				'title': '%s - comments' % article.title,
				'page': 'comments'
			})
		else:
			self.error(404)
			self.echo('error.html', {
				'page': '404',
				'title': "Can't find out this comment",
				'h2': "Can't find out this comment.",
				'msg': 'Please check whether you entered a wrong URL.'
			})

	@yui.authorized()
	def post(self, id, cursor=None):
		if self.GET['viewmode'] == 'mobile':
			error_page = message_page = 'message_mobile.html'
		else:
			error_page = 'error.html'
			message_page = 'message.html'
		is_ajax = self.request.is_xhr
		if is_ajax:
			self.set_content_type('json')
		user = self.request.current_user
		is_admin = self.request.is_admin
		if not (is_admin or user.flag & USER_FLAGS['active']):
			if is_ajax:
				self.write(json.dumps({
					'status': 403,
					'content': 'Sorry, you have been banned by the administrator and cannot reply. You can contact with the administrator for explanation.'
				}))
			else:
				self.echo(error_page, {
					'page': 'error',
					'title': 'Comment post failed',
					'h2': 'Sorry, you have been banned by the administrator and cannot reply.',
					'msg': 'You can contact with the administrator for explanation.'
				})
			return
		comment = self.POST.get('comment')
		if comment:
			comment = comment.strip().replace('\r\n', '\n').replace('\r', '\n')
		if not comment:
			if is_ajax:
				self.write(json.dumps({
					'status': 400,
					'content': 'You should post it after write something.'
				}))
			else:
				self.echo(error_page, {
					'page': 'error',
					'title': 'Comment post failed',
					'h2': 'You should post it after write something.',
					'msg': 'Please go back to reply something.'
				})
			return

		ua = []
		browser, platform, os, os_version, vendor = self.request.ua_details
		if platform:
			if platform in ('iPhone', 'iPod Touch', 'iPad', 'Android'):
				ua.append(platform)
			elif self.request.is_mobile:
				ua.append('mobile')
		else:
			if self.request.is_mobile:
				ua.append('mobile')
			elif os and os in ('Windows', 'Mac OS', 'Linux', 'FreeBSD'):
				ua.append(os)
		if browser:
			if browser == 'Internet Explorer':
				ua.append('IE')
			elif browser in ('Firefox', 'Chrome', 'Safari', 'Opera'):
				ua.append(browser)
			elif browser == 'Mobile Safari':
				ua.append('Safari')
			elif browser in ('Opera Mini', 'Opera Mobile'):
				ua.append('Opera')

		id = int(id)
		article = Article.get_article_by_id(id) if id else None
		if article:
			def post_comment(article_key, email, content, format, ua):
				comment = Comment(parent=article_key, email=email, content=content, format=format, ua=ua)
				comment.put()
				article = Article.get(article_key)
				article.replies += 1
				article.put()
				return comment, article
			email = user.key().name()
			format = CONTENT_FORMAT_FLAG['bbcode'] if self.POST['bbcode'] == 'on' else CONTENT_FORMAT_FLAG['plain']
			comment, article = db.run_in_transaction(post_comment, article.key(), email, comment, format, ua)
			if comment:
				if is_ajax:
					self.write(json.dumps({
						'status': 200,
						'comment': {
							'user_name': user.name,
							'url': user.site,
							'img': user.get_gravatar(self.request.scheme == 'https'),
							'ua': comment.ua,
							'time': formatted_time(comment.time),
							'id': comment.key().id(),
							'content': comment.html_content()
						}
					}))
				else:
					self.echo(message_page, {
						'page': 'message',
						'title': 'Comment post successful',
						'h2': 'Comment post successful.',
						'msg': 'Your comment will be displayed immediately after the cache expires.'
					})
				try:
					memcache_client.set_multi_async({
						'get_article_by_url:%s' % hash(article.url): article,
					    'get_article_by_id:%d' % id: article
					}, ARTICLE_CACHE_TIME)
					clear_latest_comments_memcache(id)
					deferred.defer(ping_hubs, BLOG_COMMENT_FEED_URL)
					url = ''
					if NOTIFY_WHEN_REPLY and not is_admin and (not SEND_INTERVAL or memcache.add('has_sent_email_when_reply', 1, SEND_INTERVAL)):
						url = u'%s%s' % (BLOG_HOME_FULL_URL, article.quoted_url())
						html_content = comment.html_content()[:4096] # maximum size of an AdminEmailMessage is 16 kilobytes
						html_body = u'%s replied at <a href="%s">%s</a>:<br/>%s' % (escape(user.name), url, article.title, html_content)
						title = u'Re: ' + article.title
						mail.AdminEmailMessage(sender=APP_SENDER, subject=title, html=html_body).send()
						import gdata_for_gae
						deferred.defer(gdata_for_gae.send_sms, user.name, article.title)
					if MAX_SEND_TO and format != CONTENT_FORMAT_FLAG['plain'] and  (is_admin or user.flag & SEND_LEVEL):
						if not url:
							url = u'%s%s' % (BLOG_HOME_FULL_URL, article.quoted_url())
							html_content = comment.html_content()[:4096] # maximum size of parameters of a task queue is 10 kilobytes
							html_body = u'%s replied at <a href="%s">%s</a>:<br/>%s<hr/>You received this mail because someone replied your comment. You can reply him or her at the ordinary article, please don\'t directly reply this email.<br/>If you don\'t like being disturbed, you can modify your <a href="%sprofile/">profile</a>.' % (escape(user.name), url, article.title, html_content, BLOG_HOME_FULL_URL)
							title = u'Re: ' + article.title
						else:
							html_body = u'%s<hr/>You received this mail because someone replied your comment. You can reply him or her at the ordinary article, please don\'t directly reply this email.<br/>If don\'t like to be disturbing, you can modify your <a href="%sprofile/">profile</a>.' % (html_body, BLOG_HOME_FULL_URL)
						deferred.defer(send_reply_notification, html_content, html_body, title, id)
				except:
					logging.error(format_exc())
			else:
				if is_ajax:
					self.write(json.dumps({
						'status': 500,
						'content': "Comment post failed, the replied article doesn't exist or the datastore is busy now.",
					}))
				else:
					self.echo(error_page, {
						'page': 'error',
						'title': 'Comment post failed',
						'h2': 'Oh, my god!',
						'msg': "Comment post failed, the replied article doesn't exist or the datastore is busy now."
					})
		else:
			if is_ajax:
				self.write(json.dumps({
					'status': 404,
					'content': "Comment post failed, the replied article doesn't exist."
				}))
			else:
				self.echo(error_page, {
					'page': 'error',
					'title': 'Comment post failed',
					'h2': 'Oh, my god!',
					'msg': "Comment post failed, the replied article doesn't exist."
				})


class CommentJson(UserHandler):
	#@yui.server_cache(COMMENTS_CACHE_TIME, False)
	def get(self, id, cursor=None):
		self.set_cache(0)
		self.set_content_type('json')

		id = int(id)
		if not id:
			self.write(json.dumps({
				 'next_cursor': None,
				 'comments': []
			}))
			return

		isHttps = self.request.scheme == 'https'
		(comments, next_cursor), users = Comment.get_comments_with_user_by_article_key(
				db.Key.from_path('Article', id), self.GET['order'] != 'desc', cursor=unquoted_cursor(cursor))
		comments_list = []
		for comment, user in izip(comments, users):
			if user:
				user_name = user.name
				user_site = escape(user.site) if user.site else ''
			else:
				user_name = u'Anonymous'
				user_site = ''
			comments_list.append({
				'user_name': user_name,
				'url': user_site,
				'img': user.get_gravatar(isHttps),
				'ua': comment.ua,
				'time': formatted_time(comment.time),
				'id': comment.key().id(),
				'content': comment.html_content()
			})
		self.write(json.dumps({
			 'next_cursor': next_cursor,
			 'comments': comments_list
		}))

	def display_exception(self, exception):
		self.write(json.dumps({
			'status': 500,
			'content': 'The server has some error, you can try to refresh or report to administrator.'
		}))


class PreviewPage(UserHandler):
	@yui.authorized()
	def post(self):
		data = self.POST['data']
		self.write(convert_bbcode_to_html(data).encode('utf-8'))


class TagPage(UserHandler):
	def get(self, name):
		name = path_to_unicode(name)
		memcache_key = 'get_tag_by_name:' + name
		tag = memcache.get(memcache_key)
		if tag is None:
			tag = Tag.get_by_key_name(name) or ENTITY_NOT_FOUND
		memcache_client.set_multi_async({memcache_key: tag}, TAGS_CACHE_TIME)
		if tag:
			cursor = unquoted_cursor(self.GET['cursor'])
			articles, next_cursor = tag.get_articles(cursor)
			self.echo('tag.html', {
				'title': u'Tag: %s' % name,
				'tag_name': name,
				'articles': articles,
				'next_cursor': next_cursor,
				'cursor': cursor,
				'page': 'tag'
			})
		else:
			self.error(404)
			self.echo('error.html', {
				'page': '404',
				'title': "Can't find out this tag",
				'h2': 'Oh, my god!',
				'msg': 'Something seems to be lost...'
			})


class CategoryPage(UserHandler):
	def get(self, name):
		name = path_to_unicode(name)
		memcache_key = 'get_category_by_name:' + name
		category = memcache.get(memcache_key)
		if category is None:
			category = Category.get_by_key_name(name) or ENTITY_NOT_FOUND
		memcache_client.set_multi_async({memcache_key: category}, CATEGORY_CACHE_TIME)
		if category:
			cursor = unquoted_cursor(self.GET['cursor'])
			articles, next_cursor = category.get_articles(cursor)
			self.echo('category.html', {
				'title': u'Category: %s' % name,
				'category_name': name,
				'articles': articles,
				'next_cursor': next_cursor,
				'cursor': cursor,
				'page': 'category'
			})
		else:
			self.error(404)
			self.echo('error.html', {
				'page': '404',
				'title': "Can't find out this category",
				'h2': 'Oh, my god!',
				'msg': 'Something seems to be lost...'
			})


class SearchPage(UserHandler):
	def get(self):
		request = self.request
		GET = request.GET
		keywords = GET['keywords']
		if keywords:
			keywords = keywords.strip()
		if keywords:
			cursor = unquoted_cursor(GET['cursor'])
			articles, next_cursor = Article.search(keywords, None if request.is_admin else True, cursor)
			self.echo('search.html', {
				'title': 'Search result',
				'articles': articles,
				'next_cursor': next_cursor,
				'keywords': keywords,
				'cursor': cursor,
				'page': 'search'
			})
		else:
			self.echo('message.html', {
				'page': 'message',
				'title': 'Please enter some search keywords',
				'h2': 'What do you search for?',
				'msg': 'Please enter some search keywords.'
			})


class ProfilePage(UserHandler):
	@yui.authorized()
	def get(self):
		self.echo('profile.html', {
			'title': 'Profile',
			'page': 'profile'
		})

	@yui.authorized()
	def post(self):
		POST = self.POST
		user = self.request.current_user
		is_ajax = self.request.is_xhr

		try:
			user.name = POST['name']
			site = (POST['site'] or '').strip()
			if site:
				if site[:4] == 'www.':
					site = 'http://' + site
				if '%' in site:
					user.site = site
				else:
					user.site = quoted_url(site)
			else:
				user.site = None
			if POST['mute'] == 'on':
				if not (user.flag & USER_FLAGS['mute']):
					user.flag |= USER_FLAGS['mute']
			elif user.flag & USER_FLAGS['mute']:
				user.flag &= ~USER_FLAGS['mute']
			user.put()
			memcache_client.set_multi_async({'get_user_by_email:' + user.key().name(): user}, USER_CACHE_TIME)
			if is_ajax:
				self.write('Your profile has been saved!')
			else:
				self.echo('message.html', {
					'page': 'message',
					'title': 'Your profile has been saved',
					'h2': 'No error happens.',
					'msg': 'Your profile has been saved!'
				})
		except (db.TransactionFailedError, db.InternalError, db.Timeout):
			if is_ajax:
				self.write("Can't save your profile because the server is too busy now.")
			else:
				self.error(500)
				self.echo('error.html', {
					'page': '500',
					'title': 'Your profile saved failed',
					'h2': 'Oh, my god!',
					'msg': 'Your profile saved failed duo to server error.'
				})
		except:
			if is_ajax:
				self.write('Your profile is incorrect.')
			else:
				self.error(400)
				self.echo('error.html', {
					'page': '400',
					'title': 'Your profile saved failed',
					'h2': 'Your profile is incorrect.',
					'msg': 'Please go back to correct it.'
				})


class RedirectToHomePage(yui.RequestHandler):
	@yui.client_cache(ARTICLES_CACHE_TIME, 'public')
	def get(self):
		self.redirect(BLOG_HOME_RELATIVE_PATH, 301)


class RedirectToArticlePage(yui.RequestHandler):
	@yui.client_cache(ARTICLE_CACHE_TIME, 'public')
	def get(self, tid=''):
		if not tid:
			try:
				id = int(self.GET['tid'])
			except:
				self.redirect(BLOG_HOME_RELATIVE_PATH, 301)
				return
		else:
			id = int(tid)

		if id:
			article = Article.get_article_by_id(id)
			if article:
				self.redirect(BLOG_HOME_RELATIVE_PATH + article.quoted_not_escaped_url(), 301)
				return
		self.redirect(BLOG_HOME_RELATIVE_PATH, 301)


class RedirectToHomeOrArticlePage(yui.RequestHandler):
	_PATTERN = reg_compile(r'tid-(\d+)(?:-page-\d+)?.html')

	@yui.client_cache(ARTICLE_CACHE_TIME, 'public')
	def get(self):
		match = RedirectToHomeOrArticlePage._PATTERN.match(self.request.query_string)
		if match:
			id = int(match.group(1))
			if id:
				article = Article.get_article_by_id(id)
				if article:
					self.redirect(BLOG_HOME_RELATIVE_PATH + article.quoted_not_escaped_url(), 301)
					return
		self.redirect('/', 301)


class FeedPage(BaseHandler):
	def get(self):
		self.set_content_type('atom')
		user_agent = self.request.user_agent.replace(',gzip(gfe)', '')
		subscribers = get_subscribers_from_ua(user_agent)
		if subscribers:
			if 'Feedfetcher-Google' in user_agent:
				user_agent = user_agent.replace(' %s subscribers;' % subscribers, '') # 避免重复统计
		else:
			user_agent = '%s:%s' % (self.request.client_ip, user_agent)
			subscribers = 1
		Subscriber.set_subscriber(user_agent, subscribers)

		articles = Article.get_articles_for_feed()
		if articles:
			last_modified = articles[0].mod_time
			last_updated = iso_time_format(last_modified)
		else:
			last_modified = datetime.utcnow()
			last_updated = iso_time_now()
		self.response.set_last_modified(last_modified)
		self.echo('feed.xml', {'articles': articles, 'last_updated': last_updated})


class GeneratedFeedPage(BaseHandler):
	def get(self):
		self.set_content_type('atom')
		feed = Feed.all().order('-time').get()
		if feed:
			self.write(feed.content.encode('utf-8'))
			user_agent = self.request.user_agent
			if 'pubsubhubbub' in user_agent or 'Feedfetcher-Google' in user_agent:
				url = u'%s%sgenerate_feed?cursor=%s' % (self.request.host_url, BLOG_ADMIN_RELATIVE_PATH, feed.cursor)
				mail.send_mail_to_admins(ADMIN_EMAIL, u'Feedfetcher-Google已抓取feed',
					u'Click this URL to generate next feed after confirm Google Reader has recorded:\n' + url,
					html=u'Click this URL to <a href="%s">generate next feed</a> after confirm Google Reader has recorded your feed.' % url)


class CommentFeedPage(BaseHandler):
	def get(self):
		self.set_content_type('atom')
		comments, articles, users = Comment.latest_comments(LATEST_COMMENTS_FOR_FEED)
		if comments:
			last_modified = comments[0].time
			last_updated = iso_time_format(last_modified)
		else:
			last_modified = datetime.utcnow()
			last_updated = iso_time_now()
		self.response.set_last_modified(last_modified)
		self.echo('comment_feed.xml', {'comments': comments, 'articles': articles, 'users': users, 'last_updated': last_updated})


class SitemapPage(yui.RequestHandler):
	@yui.client_cache(SITEMAP_CACHE_TIME, 'public')
	def get(self):
		self.set_content_type('text/xml')
		self.write(Sitemap.get_sitemap())


class RedirectToFeedPage(yui.RequestHandler):
	@yui.client_cache(FEED_CACHE_TIME, 'public')
	def get(self):
		self.redirect(BLOG_FEED_URL, 301)


class WapHomePage(BaseHandler):
	@yui.server_cache(ARTICLES_CACHE_TIME, False)
	@yui.client_cache(ARTICLES_CACHE_TIME, 'public')
	def get(self):
		cursor = unquoted_cursor(self.GET['cursor'])
		articles, next_cursor = Article.get_articles_for_homepage(cursor)
		self.echo('home_mobile.html', {
			'articles': articles,
			'next_cursor': next_cursor,
			'title': BLOG_TITLE,
			'cursor': cursor,
			'page': 'home'
		})


class WapArticlePage(UserHandler):
	def get(self, url):
		article = Article.get_article_by_url(path_to_unicode(url))
		if article and (article.published or self.request.is_admin):
			self.echo('article_mobile.html', {
				'article': article,
				'title': article.title,
				'page': 'article'
			})
			incr_counter('article_counter:%s' % article.key().id(), BLOG_ADMIN_RELATIVE_PATH + 'article_counter/')
		else:
			self.error(404)
			self.echo('message_mobile.html', {
				'page': '404',
				'title': "Can't find out this article",
				'h2': "Can't find out this article.",
				'msg': 'Please check whether you entered a wrong URL.'
			})


class WapCommentPage(UserHandler):
	#@yui.server_cache(COMMENTS_CACHE_TIME)
	def get(self, id, cursor=None):
		article_id = int(id)
		article = Article.get_article_by_id(article_id) if article_id else None
		if article:
			(comments, next_cursor), users = Comment.get_comments_with_user_by_article_key(
				article.key(), cursor=unquoted_cursor(cursor))
			self.echo('comment_mobile.html', {
				'comments': comments,
				'next_cursor': next_cursor,
				'comment_users': users,
				'id': id,
			    'article': article,
				'title': u'%s - comments' % article.title,
				'page': 'comments'
			})
		else:
			self.error(404)
			self.echo('message_mobile.html', {
				'page': '404',
				'title': "Can't find out this comment",
				'h2': "Can't find out this comment.",
				'msg': 'Please check whether you entered a wrong URL.'
			})


class RedirectToWapHomePage(yui.RequestHandler):
	@yui.client_cache(86400, 'public')
	def get(self):
		self.redirect(BLOG_HOME_RELATIVE_PATH + 'wap/', 301)


class RobotsPage(BaseHandler):
	@yui.client_cache(3600, 'public')
	def get(self):
		self.set_content_type('text/plain')
		self.echo('robots.txt')


class RobotsMobilePage(BaseHandler):
	@yui.client_cache(3600, 'public')
	def get(self):
		self.set_content_type('text/plain')
		self.echo('robots_mobile.txt')


class NotFoundPage(BaseHandler):
	@yui.client_cache(600, 'public')
	def get(self):
		self.error(404)
		self.echo('error.html', {
			'page': '404',
			'title': "Can't find out this URL",
			'h2': 'Oh, my god!',
			'msg': 'Something seems to be lost...'
		})

	post = get


class NotFoundMobilePage(BaseHandler):
	@yui.client_cache(600, 'public')
	def get(self):
		self.error(404)
		self.echo('message_mobile.html', {
			'page': '404',
			'title': "Can't find out this URL",
			'h2': 'Oh, my god!',
			'msg': 'Something seems to be lost...'
		})

	post = get


class LoginoutPage(yui.RequestHandler):
	def get(self):
		if self.request.user:
			self.redirect(users.create_logout_url(self.request.referer or BLOG_HOME_RELATIVE_PATH))
		else:
			self.redirect(users.create_login_url(self.request.referer or BLOG_HOME_RELATIVE_PATH))


class VerifySubscription(yui.RequestHandler):
	def get(self):
		verify_token = self.GET['hub.verify_token']
		if verify_token and verify_token == memcache.get('hub_verify_token'):
			memcache.delete('hub_verify_token')
			self.write(self.GET['hub.challenge'])
			mail.send_mail_to_admins(ADMIN_EMAIL, 'PubSubHubbub request has been verified.', 'Request parameters are:\n%s' % dict(self.GET))
		else:
			logging.warning('PubSubHubbub request verified failed. Request parameters are:\n%s' % dict(self.GET))

	def post(self):
		pass
