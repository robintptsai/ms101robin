# -*- coding: utf-8 -*-

import logging
from email.header import decode_header
from email.utils import parseaddr
from itertools import izip
from random import random
from time import sleep

try:
	import json
except ImportError:
	import simplejson as json
from google.appengine.ext import deferred
import yui

from common import UserHandler, incr_counter, timestamp_to_datetime, datetime_to_timestamp, unquoted_cursor
from model import *


class ArticleCounterTaskPage(yui.RequestHandler):
	def post(self):
		key = self.POST['key']
		for i in xrange(10):
			if Article.calc_hits(key):
				break
			sleep(5)


class AdminPage(yui.RequestHandler):
	def get(self):
		self.redirect(BLOG_ADMIN_RELATIVE_PATH + 'article/new/', 301)


class UnpublishedArticlesPage(BaseHandler):
	def get(self, cursor=None):
		import hook
		hook.init()

		cursor = unquoted_cursor(self.GET['cursor'])
		articles, next_cursor = Article.get_unpublished_articles(cursor)
		self.echo('unpublished_articles.html', {
			'cursor': cursor,
			'articles': articles,
		    'next_cursor': next_cursor,
		    'title': 'Unpublished articles',
		    'page': 'unpublished_article'
		})


class EditArticlePage(BaseHandler):
	def get(self, id):
		article = Article.get_by_id(int(id))
		if article:
			self.echo('edit_article.html', {
			    'article': article,
				'categories': Category.get_all_categories(),
				'tags': Tag.get_all_tags(),
				'title': u'Edit article: %s' % article.title,
				'page': 'edit_article'
			})
		else:
			self.write("The article doesn't exist.")

	def post(self, id):
		article = Article.get_by_id(int(id))
		if not article:
			self.write("Edit failed, the article doesn't exist.")
		request = self.request
		POST = self.POST
		data = dict(POST)
		data['title'] = (POST['title'] or '').strip()
		if not data['title']:
			self.write('Edit failed, the article title cannot be empty.')
			return

		data['time'] = get_time(data['time'], article.time)
		data['mod_time'] = get_time(data['mod_time'], article.mod_time)

		if data['keywords']:
			keywords = data['keywords'].split(',')
			keyword_set = set([keyword.strip().lower() for keyword in keywords])
			keyword_set.discard('')
			data['keywords'] = list(keyword_set)
		else:
			data['keywords'] = []
		tags = request.get_all('tags')
		if not tags or tags == ['']:
			data['tags'] = []
		else:
			tag_set = set([tag.strip() for tag in tags])
			tag_set.discard('')
			data['tags'] = list(tag_set)
		bbcode = POST['bbcode'] == 'on'
		html = POST['html'] == 'on'
		data['format'] = bbcode + 2 * html
		data['published'] = POST['published'] == 'on'

		old_url = article.url
		old_tags = set(article.tags)

		url = data['url']
		if not url:
			if REPLACE_SPECIAL_CHARACTERS_FOR_URL:
				data['url'] = formatted_date_for_url(data['time'] or article.time) + replace_special_characters_for_url(data['title'])
			else:
				data['url'] = formatted_date_for_url(data['time'] or article.time) + data['title']
		elif not Article._PATTERN.match(url):
			self.write("Edit failed, the article URL isn't well-formed.")
			return

		if url != old_url and Article.all().filter('url =', url).count(1):
			self.write('Edit failed, there is already an article with the same URL.')
			return

		data['content'] = data['content'].replace('\r\n', '\n').replace('\r', '\n')

		def update(article_key):
			article = Article.get(article_key)
			if article:
				article.title = data['title']
				article.url = data['url']
				article.content = data['content']
				article.format = data['format']
				article.published = data['published']
				article.keywords = data['keywords']
				article.tags = data['tags']
				article.category = data['category'] or None
				if data['time']:
					article.time = data['time']
				if data['mod_time']:
					article.mod_time = data['mod_time']
				article.put()
				return article
			else:
				return None
		article = db.run_in_transaction(update, article.key())

		if article:
			new_tags = set(article.tags)
			removed_tags = old_tags - new_tags
			added_tags = new_tags - old_tags

			if removed_tags:
				removed_tags = set(Tag.get_by_key_name(removed_tags))
				removed_tags.discard(None)
				for removed_tag in removed_tags:
					removed_tag.count -= 1
					if removed_tag.count < 0:
						removed_tag.count = 0

			if added_tags:
				added_tags = set(Tag.get_by_key_name(added_tags))
				added_tags.discard(None)
				for added_tag in added_tags:
					added_tag.count += 1

			changed_tags = removed_tags | added_tags
			if changed_tags:
				db.put_async(changed_tags)

			clear_article_memcache(id, old_url)
			memcache_client.set_multi_async({'get_article_by_id:%s' % id: article, 'get_article_by_url:%s' % hash(article.url): article}, ARTICLE_CACHE_TIME)
			quoted_url = article.quoted_url()
			full_url = BLOG_HOME_FULL_URL + quoted_url
			if data['mod_time']:
				deferred.defer(ping_hubs, BLOG_FEED_URL)
				deferred.defer(ping_xml_rpc, full_url)
			if POST['twitter'] == 'on':
				deferred.defer(post_article_to_twitter, article.title, full_url)
			self.write('Edit successful, see the <a href="%s%s">updated article</a>.' % (BLOG_HOME_RELATIVE_PATH, quoted_url))
		else:
			self.write('Edit failed, the article has been deleted or datastore is busy now.')


class AddArticlePage(BaseHandler):
	def get(self):
		self.echo('new_article.html', {
		    'categories': Category.get_all_categories(),
		    'tags': Tag.get_all_tags(),
		    'title': 'Write a new article',
		    'page': 'new_article'
		})

	def post(self):
		POST = self.POST
		title = strip(POST['title'])
		if not title:
			self.write('Save failed, the article title cannot be empty.')
			return
		time = parse_time(POST['time']) or datetime.utcnow()
		mod_time = parse_time(POST['mod_time']) or time
		url = strip(POST['url'])
		if not url:
			if REPLACE_SPECIAL_CHARACTERS_FOR_URL:
				url = formatted_date_for_url(time) + replace_special_characters_for_url(title)
			else:
				url = formatted_date_for_url(time) + title
		elif not Article._PATTERN.match(url):
			self.write("Save failed, the article URL isn't well-formed.")
			return
		if Article.all().filter('url =', url).count(1):
			self.write('Save failed, there is already an article with the same URL.')
			return

		if POST['keywords']:
			keywords = POST['keywords'].split(',')
			keyword_set = set([keyword.strip().lower() for keyword in keywords])
			keyword_set.discard('')
			keywords = list(keyword_set)
		else:
			keywords = []
		tags = self.request.get_all('tags')
		if not tags or tags == ['']:
			tags = []
		else:
			tag_set = set([tag.strip() for tag in tags])
			tag_set.discard('')
			tags = list(tag_set)
		published = POST['published'] == 'on'
		bbcode = POST['bbcode'] == 'on'
		html = POST['html'] == 'on'
		format = bbcode + 2 * html
		content = POST['content'].replace('\r\n', '\n').replace('\r', '\n')

		try:
			article = Article(
				title=title,
				url=url,
				content=content,
				format=format,
				published=published,
				keywords=keywords,
				tags=tags,
				category=POST['category'] or None,
				time=time,
				mod_time=mod_time
			)
			article.put()

			if tags:
				tags = Tag.get_by_key_name(tags)
				tag_set = set(tags)
				tag_set.discard(None)
				tags = list(tag_set)
				if tags:
					for tag in tags:
						tag.count += 1
					db.put_async(tags)

			quoted_url = article.quoted_url()
			if published:
				clear_article_memcache()
				deferred.defer(ping_hubs, BLOG_FEED_URL)
				full_url = BLOG_HOME_FULL_URL + quoted_url
				deferred.defer(ping_xml_rpc, full_url)
				if POST['twitter'] == 'on':
					deferred.defer(post_article_to_twitter, article.title, full_url)
			self.write('Save successful, see the <a href="%s%s">saved article</a>.' % (BLOG_HOME_RELATIVE_PATH, quoted_url))
		except:
			self.write('Save failed, the datastore has some error or is busy now.')


class DeleteArticlePage(BaseHandler):
	def get(self, id):
		article = Article.get_by_id(int(id))
		if article:
			self.echo('del_article.html', {
				'page': 'del_article',
				'id': id,
			    'title': u'Delete article: %s' % article.title
			})
		else:
			self.write("The article doesn't exist.")

	def post(self, id):
		try:
			if Article.remove(int(id)):
				self.write('删除成功')
			else:
				self.write('文章不存在，无需删除')
		except:
			self.write('删除失败，请重试')


class AddCategoryPage(BaseHandler):
	def get(self):
		self.echo('new_category.html', {
			'title': 'Add new category',
			'page': 'new_category'
		})

	def post(self):
		path_with_name = Category.fill_pathes(self.POST['path'])
		if not path_with_name:
			self.write('Add failed, the category name cannot be empty.')
			return

		try:
			keys = ['get_all_categories']
			for each_path, name in path_with_name:
				if Category.all().filter('path =', each_path).count(1):
					continue
				category = Category.get_by_key_name(name)
				if category and category.path != each_path:
					self.write('Add failed, there is already a path "%s" includes the category name "%s".' % (category.path, name))
					return
				Category.get_or_insert(key_name=name, path=each_path)
				keys.extend(['get_sub_categories:' + name, 'get_category_with_subs:%s' % hash(each_path)])
			memcache.delete_multi(keys)
			tenjin.helpers.fragment_cache.store.delete('siderbar')
			yui.flush_all_server_cache()
			self.write('Add successful.')
		except:
			self.write('Add failed, the datastore has some error or is busy now.')


class RemoveCategoryPage(BaseHandler):
	def get(self):
		self.echo('del_category.html', {
			'categories': Category.get_all_categories(),
			'title': 'Delete category',
			'page': 'del_category'
		})

	def post(self):
		path_with_name = Category.fill_pathes(self.POST['path'])
		if not path_with_name:
			self.write('Delete failed, the category name cannot be empty.')
			return
		path, name = path_with_name[-1]
		category = Category.all().filter('path =', path).get()
		if not category:
			self.write("Delete failed, the category doesn't exist.")
			return
		if category.has_sub_categories():
			self.write('Delete failed, the category has sub categories, please deal with them first.')
			return

		deferred.defer(delete_category, path)
		self.write("The delete task has been added. Please don't change this category or its articles until you receive a mail that notices the task has been finished.")


class MoveArticlesBetweenCategoriesPage(BaseHandler):
	def get(self):
		self.echo('move_category.html', {
			'categories': Category.get_all_categories(),
			'title': "Batch change articles' category",
			'page': 'move_category'
		})

	def post(self):
		from_pathes = Category.fill_pathes(self.POST['from_path'])
		if from_pathes:
			from_path, from_name = from_pathes[-1]
			from_category = Category.all().filter('path =', from_path).get()
			if not from_category:
				self.write("Change failed, the source category doesn't exist.")
				return
		else:
			self.write('Change failed, the source category name cannot be empty.')
			return

		to_pathes = Category.fill_pathes(self.POST['to_path'])
		if to_pathes:
			to_path, to_name = to_pathes[-1]
			if not Category.all().filter('path =', to_path).count(1):
				self.write("Change failed, the object category doesn't exist.")
				return
		else:
			self.write('Change failed, the object category name cannot be empty.')
			return

		if from_name == to_name:
			self.write('Change failed, the name of the source category and the object category is the same.')
			return

		deferred.defer(move_articles_between_categories, from_path, to_path)
		self.write("The changed task has been added. Please don't change these 2 categories or their articles until you receive a mail that notices the task has been finished.")


class AddTagPage(BaseHandler):
	def get(self):
		self.echo('new_tag.html', {
			'title': 'Add new tag',
			'page': 'new_tag'
		})

	def post(self):
		name = strip(self.POST['name'])
		if not name:
			self.write('Add failed, the tag name cannot be empty.')
			return

		if Tag.get_or_insert(key_name=name):
			clear_tags_memcache()
			self.write('Add successful.')
		else:
			self.write('Add failed, the datastore has some error or is busy now.')


class RemoveTagPage(BaseHandler):
	def get(self):
		self.echo('del_tag.html', {
			'tags': Tag.get_all_tags(),
			'title': 'Delete tag',
			'page': 'del_tag'
		})

	def post(self):
		name = strip(self.POST['name'])
		if not name:
			self.write('Delete failed, the tag name cannot be empty.')
			return

		deferred.defer(delete_tag, name)
		self.write("The delete task has been added. Please don't change this tag or its articles until you receive a mail that notices the task has been finished.")


class MoveArticlesBetweenTagsPage(BaseHandler):
	def get(self):
		self.echo('move_tag.html', {
			'tags': Tag.get_all_tags(),
			'title': "Batch change articles' tag",
			'page': 'move_tag'
		})

	def post(self):
		from_name = strip(self.POST['from_name'])
		if not from_name:
			self.write('Change failed, the source tag name cannot be empty.')
			return

		to_name = strip(self.POST['to_name'])
		if not to_name:
			self.write('Change failed, the object tag name cannot be empty.')
			return

		if from_name == to_name:
			self.write('Change failed, the name of the source tag and the object tag is the same.')
			return

		to_tag = Tag.get_by_key_name(to_name)
		if not to_tag:
			self.write("Change failed, the object tag doesn't exist.")
			return

		deferred.defer(move_articles_between_tags, from_name, to_name)
		self.write("The changed task has been added. Please don't change these 2 tags or their articles until you receive a mail that notices the task has been finished.")


class DeleteCommentPage(BaseHandler):
	def get(self, article_id, comment_id):
		self.echo('del_comment.html', {
			'title': 'Delete comment',
			'page': 'del_comment'
		})

	def post(self, article_id, comment_id):
		def delete(article_id, comment_id):
			article = Article.get_by_id(article_id)
			if article:
				comment = Comment.get_by_id(comment_id, article)
				if comment:
					comment.delete()
					article.replies -= 1
					if article.replies < 0:
						article.replies = 0
					article.put()
		try:
			db.run_in_transaction(delete, int(article_id), int(comment_id))
			clear_latest_comments_memcache(article_id)
			if self.request.is_xhr:
				self.set_content_type('json')
				self.write(json.dumps({'status': 204}))
			else:
				self.write('Delete successful.')
		except:
			if self.request.is_xhr:
				self.set_content_type('json')
				self.write(json.dumps({
					'status': 500,
					'content': 'Delete failed.'
				}))
			else:
				self.write('Delete failed.')


class EditCommentPage(BaseHandler):
	def get(self, article_id, comment_id):
		comment = Comment.get_comment_by_id(int(comment_id), int(article_id))
		if comment:
			self.echo('edit_comment.html', {
			    'comment': comment,
				'title': 'Edit comment',
				'page': 'edit_comment'
			})
		else:
			self.write("The comment doesn't exist.")

	def post(self, article_id, comment_id):
		comment = Comment.get_comment_by_id(int(comment_id), int(article_id))
		if comment:
			POST = self.POST
			comment.content = POST['content'].strip().replace('\r\n', '\n').replace('\r', '\n')
			bbcode = POST['bbcode'] == 'on'
			html = POST['html'] == 'on'
			comment.format = bbcode + 2 * html
			email = (POST['email'] or '').strip()
			if email and email != comment.email:
				User.get_user_by_email(email)
				comment.email = email
			time = get_time(POST['time'], comment.time)
			if time:
				comment.time = time
			uas = POST['ua'].split(',') if POST['ua'] else []
			comment.ua = [ua.strip() for ua in uas if ua.strip()]
			comment.put()
			clear_latest_comments_memcache(article_id)
			deferred.defer(ping_hubs, BLOG_COMMENT_FEED_URL)
			self.write('Edit successful.')
		else:
			self.write("Edit failed, the comment doesn't exist.")


class SearchUserPage(BaseHandler):
	def get(self):
		GET = self.GET
		filter = GET['filter']
		value = GET['value']
		context = {
			'title': 'Search user',
			'page': 'search_user',
		    'filer': filter,
		    'value': value
		}
		name = GET['name']
		if filter == 'email':
			user = User.get_by_key_name(value)
			context['users'] = [user] if user else []
		elif filter == 'name':
			users = User.all().filter('name =', value).fetch(100)
			context['users'] = users
		else:
			context['users'] = []
		self.echo('search_user.html', context)


class EditUserPage(BaseHandler):
	def get(self):
		email = self.GET['email']
		if email:
			user = User.get_by_key_name(email)
			if user:
				self.echo('edit_user.html', {
					'user': user,
					'title': u'Edit user: %s' % user.name,
					'page': 'edit_user'
				})
			else:
				self.error(404)
				self.echo('error.html', {
					'page': '404',
					'title': "Can't find out this user",
					'h2': "Can't find out this user",
					'msg': 'This user may be deleted.'
				})
		else:
			self.error(404)
			self.echo('error.html', {
				'page': '404',
				'title': "Can't find out this user",
				'h2': "Can't find out this user",
				'msg': "Didn't offer the user's email."
			})

	def post(self):
		POST = self.POST
		email = POST['email']
		if email:
			user = User.get_by_key_name(email)
			if user:
				if POST['name']:
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
				flag = 0
				if POST['mute'] == 'on':
					flag |= USER_FLAGS['mute']
				if POST['verified'] == 'on':
					flag |= USER_FLAGS['verified']
				if POST['banned'] != 'on':
					flag |= USER_FLAGS['active']
				user.flag = flag
				try:
					user.put()
					memcache.set('get_user_by_email:' + email, user, USER_CACHE_TIME)
					if POST['del-comment'] == 'on':
						deferred.defer(delete_comments_of_user, email)
					self.write('User data save successful.')
				except:
					self.write('User data save failed.')
			else:
				self.write("The user doesn't exist.")
		else:
			self.write("Can't find out the user because of not offering his email.")


class EditUserByCommentPage(BaseHandler):
	def get(self, article_id, comment_id):
		comment = Comment.get_comment_by_id(int(comment_id), int(article_id))
		if comment:
			user = User.get_by_key_name(comment.email)
			if user:
				self.echo('edit_user.html', {
					'user': user,
					'title': u'Edit user: %s' % user.name,
					'page': 'edit_user'
				})
			else:
				self.error(404)
				self.echo('error.html', {
					'page': '404',
					'title': "Can't find out this user",
					'h2': "Can't find out this user",
					'msg': 'This user may be deleted.'
				})
		else:
			self.error(404)
			self.echo('error.html', {
				'page': '404',
				'title': 'The comment has been delete',
				'h2': 'The comment has been delete',
				'msg': "Can't find out the user corresponding to this comment."
			})


class GenerateSitemapPage(yui.RequestHandler):
	def get(self):
		id = self.GET['id']
		id = int(id) if id else 0
		num, next_cursor = Sitemap.fill(id, unquoted_cursor(self.GET['cursor']))
		if num == Sitemap._LIMIT: # need fetch more articles
			taskqueue.add(queue_name='generate-sitemap', method='GET',
			    url=BLOG_ADMIN_RELATIVE_PATH + 'generate_sitemap?id=%d&cursor=%s' % (id + 1, next_cursor))
			self.write('The sitemap generating task has been added.')
		else:
			self.write('The sitemap has been generated.')


class GenerateMissingEntitiesPage(yui.RequestHandler):
	def get(self):
		deferred.defer(generate_missing_entities)
		self.write('The fixing task has been added.')


class GenerateFeedPage(BaseHandler):
	def get(self):
		limit = 100
		query = Article.all().filter('published =', True)
		articles, cursor = get_fetch_result_with_valid_cursor(query_with_cursor(query, self.GET['cursor']), limit)
		if articles:
			last_updated = iso_time_format(articles[0].mod_time)
			content = self.render('feed.xml', {'articles': articles, 'last_updated': last_updated})
			Feed(content=content.decode('utf-8'), cursor=cursor).put()
			deferred.defer(ping_hubs, BLOG_FEED_URL)
			if len(articles) < limit:
				self.write("The feed has been generated, and there aren't newer articles. You can switch back to the normal feed URL, delete all feed entities after confirmed the Google Reader has record your feed.")
			else:
				self.write('The feed has been generated.')
		else:
			self.write("There aren't newer articles. You can switch back to the normal feed URL, delete all feed entities after confirmed the Google Reader has record your feed.")


class AddArticleByEmail(yui.RequestHandler):
	def post(self):
		mail_message = mail.InboundEmailMessage(self.request.body)
		reply_to = parseaddr(mail_message.sender)[1]
		title = decode_header(mail_message.subject)[0]
		title = title[0].decode(title[1] or 'utf-8').strip()
		if reply_to not in EMAIL_WRITERS:
			logging.warning(u'Unauthorized user<%s> tried to add article by email, you can changed the inbound email address in app.yaml to avoid spam emails.' % reply_to)
			mail.send_mail(ADMIN_EMAIL, reply_to, u'Re: ' + title, 'Add article failed, you are not in the mail list.')
			return
		if not title:
			mail.send_mail(ADMIN_EMAIL, reply_to, u'Re: ' + title, 'Publish failed, the article title cannot be empty.')
			return

		format = 0
		content = ''
		msg = mail_message.original
		charsets = msg.get_charsets()
		for part, charset in izip(msg.walk(), charsets):
			content_type = part.get_content_type()
			if content_type == 'text/plain' and format == 0 and not content:
				payload = part.get_payload(decode=True)
				if payload:
					content = payload.decode(charset or 'utf-8', 'ignore').strip()
			elif content_type == 'text/html':
				payload = part.get_payload(decode=True)
				if payload:
					content = payload.decode(charset or 'utf-8', 'ignore').strip()
					if content:
						format = 2
						break

		if not content:
			mail.send_mail(ADMIN_EMAIL, reply_to, u'Re: ' + title, 'Publish failed, the article content cannot be empty.')
		if REPLACE_SPECIAL_CHARACTERS_FOR_URL:
			url = formatted_date_for_url() + replace_special_characters_for_url(title)
		else:
			url = formatted_date_for_url() + title
		if Article.all().filter('url =', url).count(1):
			mail.send_mail(ADMIN_EMAIL, reply_to, u'Re: ' + title, 'Publish failed, there is already an article with the same URL.')
			return

		try:
			article = Article(
				title=title,
				url=url,
				content=content,
				format=format,
				published=True
			)
			article.put()
			url = '%s%s' % (BLOG_HOME_FULL_URL, article.quoted_url())
			mail.send_mail(ADMIN_EMAIL, reply_to, u'Re: ' + title, 'Publish successful.\n' + url, html=u'Publish successful, see the <a href="%s">publish article</a>.' % url)
			clear_article_memcache()
			deferred.defer(ping_hubs, BLOG_FEED_URL)
			deferred.defer(ping_xml_rpc, BLOG_HOME_FULL_URL + article.quoted_url())
		except:
			mail.send_mail(ADMIN_EMAIL, reply_to, u'Re: ' + title, 'Publish failed, the datastore has some error or is busy now.')


class MaintainPage(BaseHandler):
	def get(self):
		self.echo('maintain.html', {
		    'title': 'Maintenance',
		    'page': 'maintain'
		})


class FlushCachePage(yui.RequestHandler):
	def get(self):
		yui.flush_all_server_cache()
		memcache.flush_all()
		self.write('Caches has been flushed.')


class UpdateTagsCountPage(yui.RequestHandler):
	def get(self):
		update_tags_count()
		self.write('Tag count has been updated.')


class UpdateArticlesRepliesPage(yui.RequestHandler):
	def get(self):
		deferred.defer(update_articles_replies)
		self.write('The task to update the comment count has been added.')


class CalendarTokenPage(BaseHandler):
	def get(self):
		import gdata.auth
		import gdata.calendar
		import gdata.calendar.service
		import gdata_for_gae

		context = {
		    'title': 'SMS notice',
		    'page': 'calendar_token',
		    'msg': '',
		    'token': ''
		}
		if ADMIN_PASSWORD:
			context['use_pw'] = True
			calendar_client = gdata_for_gae.programmatic_login(ADMIN_EMAIL, ADMIN_PASSWORD)
			if calendar_client:
				context['msg'] = 'Using account id and password to login and has passed the authentication.'
			else:
				context['msg'] = 'Using account id and password to login, but the password is incorrect.'
		else:
			context['use_pw'] = False
			scope = 'http://www.google.com/calendar/feeds/'
			feed = self.GET['feed']
			if feed:
				auth_token = gdata.auth.extract_auth_sub_token_from_url(self.request.uri)
				if auth_token:
					try:
						calendar_client = gdata.calendar.service.CalendarService()
						gdata_for_gae.run_on_appengine(calendar_client, user=ADMIN_EMAIL, url=feed)
						calendar_client.UpgradeToSessionToken(auth_token)
						context['msg'] = 'Token save successful.'
						context['token'] = gdata_for_gae.load_auth_token(ADMIN_EMAIL)
					except:
						context['msg'] = 'Token authentication failed.'
				else:
					self.redirect(str(gdata.auth.generate_auth_sub_url(self.request.uri, (scope,))))
					return
			else:
				calendar_client = gdata.calendar.service.CalendarService()
				gdata_for_gae.run_on_appengine(calendar_client, user=ADMIN_EMAIL)
				if not isinstance(calendar_client.token_store.find_token(scope), gdata.auth.AuthSubToken):
					context['msg'] = 'No available token exists.'
				else:
					context['msg'] = 'Available token exists.'
					context['token'] = gdata_for_gae.load_auth_token(ADMIN_EMAIL)
		self.echo('calendar_token.html', context)

	def post(self):
		import gdata_for_gae
		gdata_for_gae.del_auth_token(ADMIN_EMAIL)
		self.write('The token has been deleted successful.')


class SubscribePage(BaseHandler):
	def get(self):
		self.echo('subscribe.html', {
		    'title': 'PubSubHubbub subscription and unsubscription',
		    'page': 'subscribe'
		})

	def post(self):
		feed = self.POST['feed']
		if not feed:
			self.write('Please fill out the feed address.')
			return
		mode = self.POST['mode']
		if mode == 'ping':
			try:
				ping_hubs(feed)
				self.write('Published successful.')
			except:
				self.write('Published failed, you can continue to retry.')
		elif mode in ('subscribe', 'unsubscribe'):
			verify_token = `random()`
			memcache.set('hub_verify_token', verify_token)
			if 200 <= send_subscription_request('https://pubsubhubbub.appspot.com/subscribe', mode, verify_token, feed) <= 299:
				self.write('Submit successful.')
			else:
				self.write('Submit failed continue to retry.')
		else:
			self.write('Request is incorrect, the request mode is not supported.')


class RemoveOldSubscribersPage(yui.RequestHandler):
	def get(self):
		Subscriber.update_new_subscribers()
		Subscriber.remove_old_subscribers()
		self.write('Finished updating.')


class WarmupPage(yui.RequestHandler):
	def get(self):
		Category.get_all_categories()
		Tag.get_all_tags()
		Article.get_articles_for_homepage()
		Comment.latest_comments(LATEST_COMMENTS_FOR_SIDEBAR)
		Subscriber.update_new_subscribers()
		Subscriber.get_subscribers()
		get_recent_tweets()
		yui.clear_expired_server_cache()
		update_requests_counter()


class TwitterStatusPage(BaseHandler):
	def get(self):
		self.echo('twitter_status.html', {
			'title': 'Twitter Status',
			'page': 'twitter_status',
			'twitter': Twitter.get_twitter() if TWITTER_CONSUMER_KEY and TWITTER_CONSUMER_SECRET else None
		})

	def post(self):
		if TWITTER_CONSUMER_KEY and TWITTER_CONSUMER_SECRET:
			content = self.POST['content']
			if content:
				content = content.strip()
			if content:
				if Twitter.get_twitter():
					if post_tweet(content):
						self.write('Tweet successful.')
					else:
						self.write('Tweet failed, something is wrong with Google App Engine or Twitter. Please try again later.')
				else:
					self.write("Tweet failed, your blog hasn't associated with your Twitter account.")
			else:
				self.write('Tweet failed, you need to write something.')
		else:
			self.write("Tweet failed, your blog hasn't associated with your Twitter account.")


class TwitterOauthPage(BaseHandler):
	def get(self):
		if TWITTER_CONSUMER_KEY and TWITTER_CONSUMER_SECRET:
			success = True
			TWITTER_REQUEST_TOKEN_URL = 'https://api.twitter.com/oauth/request_token'
			params = get_oauth_params({}, TWITTER_REQUEST_TOKEN_URL)
			try:
				res = urlfetch.fetch(url=TWITTER_REQUEST_TOKEN_URL, headers={'Authorization': 'OAuth ' + dict2qs(params)}, method='POST')
				if res.status_code != 200:
					success = False
					logging.error('Fetch request token error.\nstatus_code: %s\nheaders: %s\nparams: %s' % (res.status_code, res.headers, params))
			except:
				success = False

			if success:
				content = qs2dict(res.content)
				if content['oauth_callback_confirmed'] != 'true':
					success = False
					logging.error('Fetch request token error.\nstatus_code: %s\nheaders: %s\nparams: %s' % (res.status_code, res.headers, params))
		else:
			success = False

		if success:
			memcache.set(content['oauth_token'], content['oauth_token_secret'], 600, namespace='TwitterRequestToken')
			self.redirect('https://api.twitter.com/oauth/authorize?oauth_token=%s' % content['oauth_token'])
		else:
			self.echo('twitter_oauth.html', {
				'title': 'Failed to fetch request token',
				'page': 'twitter_oauth'
			})


class TwitterCallbackPage(BaseHandler):
	def get(self):
		if TWITTER_CONSUMER_KEY and TWITTER_CONSUMER_SECRET:
			msg = ''
			oauth_token = self.GET['oauth_token']
			if oauth_token:
				oauth_token_secret = memcache.get(oauth_token, 'TwitterRequestToken')
				if oauth_token_secret:
					TWITTER_ACCESS_TOKEN_URL = 'https://api.twitter.com/oauth/access_token'
					params = get_oauth_params({
						'oauth_token': oauth_token,
						'oauth_verifier': self.GET['oauth_verifier']
					}, TWITTER_ACCESS_TOKEN_URL, oauth_token_secret)

					try:
						res = urlfetch.fetch(url=TWITTER_ACCESS_TOKEN_URL, headers={'Authorization': 'OAuth ' + dict2qs(params)}, method='POST')
						if res.status_code != 200:
							logging.error('Exchanging access token error.\nstatus_code: %s\nheaders: %s\nparams: %s' % (res.status_code, res.headers, params))
							msg = 'Exchanging access token failed, something is wrong with Google App Engine or Twitter. Please try again later.'
					except:
						msg = 'Exchanging access token failed, something is wrong with Google App Engine or Twitter. Please try again later.'

					content = qs2dict(res.content)
					Twitter.set_twitter(name=content['screen_name'], token=content['oauth_token'], secret=content['oauth_token_secret'])
				else:
					msg = 'Exchanging access token failed, the oauth_token is invalid or expired. Please try again.'
			else:
				logging.error('Missing or wrong oauth_token: ' + oauth_token)
				msg = 'Exchanging access token failed, the oauth_token is missing. Please try again.'
		else:
			msg = 'You haven\'t set the Twitter consumer key and secret. To enable this function, please see <a href="status">Twitter Status</a> to configure it.'

		if msg:
			self.echo('twitter_callback.html', {
				'title': 'Twitter associating failed',
				'page': 'twitter_callback',
			    'msg': msg
			})
		else:
			self.redirect('./status')


class XmlRpcPage(BaseHandler):
	def get(self):
		self.echo('xml_rpc.html', {
			'title': 'XML-RPC服务',
			'page': 'xml_rpc',
			'xml_rpc': XmlRpc.get_xml_rpc()
		})

	def post(self):
		result = XmlRpc.set_xml_rpc(self.POST['username'], self.POST['password'])
		if result == 1:
			self.write('保存成功，XML-RPC已启用。')
		elif result == 0:
			self.write('保存成功，XML-RPC已禁用。')
		else:
			self.write('保存失败，请重新尝试。')


class ExportPage(yui.RequestHandler):
	def get(self):
		filename = get_local_now().strftime('backup-%Y%m%d%H%M%S.gz')
		self.response.set_download_filename(filename)
		self.write(export_entities())


class ImportPage(BaseHandler):
	def get(self):
		self.echo('import_export.html', {
			'title': '备份',
			'page': 'import'
		})

	def post(self):
		self.write(IMPORT_ENTITIES_RETURN_MESSAGES[import_entities(self.POST['file'].file)])


class ScheduledBackupPage(yui.RequestHandler):
	def get(self):
		memcache_client.set_multi({
			'dynamic_requests': 0,
			'update_counter': 0
		})
		gzip_content = export_recent_entities()
		if gzip_content:
			filename = get_local_now().strftime('backup-%Y%m%d%H%M%S.gz')
			mail.AdminEmailMessage(sender=ADMIN_EMAIL, subject='Daily backup', body=' ', attachments=[(filename, gzip_content)]).send()
