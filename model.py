# -*- coding: utf-8 -*-

from calendar import timegm
from hashlib import md5
import re

from google.appengine.api import users, memcache, mail
from google.appengine.ext import db, deferred

from setting import *
from common import *


class EntityNotFound(object):
	def __nonzero__(self):
		return False

ENTITY_NOT_FOUND = EntityNotFound()

EVENTUAL_CONSISTENCY_CONFIG = db.create_config(read_policy=db.EVENTUAL_CONSISTENCY)
QUICK_LIMITED_EVENTUAL_CONSISTENCY_CONFIG = db.create_config(deadline=0.5, read_policy=db.EVENTUAL_CONSISTENCY)

USER_FLAGS = {
	'active': 1, # not be banned
	'verified': 2,
    'mute': 4 # whether or not receive email notification
}

class User(db.Model):
	# key name: email
	name = db.StringProperty(required=True)
	site = db.StringProperty(indexed=False)
	flag = db.IntegerProperty(default=USER_FLAGS['active'] | USER_FLAGS['verified'], indexed=False)

	def to_dict(self):
		return {
			'key': self.key().name(),
			'name': self.name,
			'site': self.site,
			'flag': self.flag
		}

	@classmethod
	def from_dict(cls, entity):
		return cls(
			key_name=entity['key'],
			name=entity['name'],
			site=entity['site'],
			flag=entity['flag']
		)

	@staticmethod
	def get_current_user():
		current_user = users.get_current_user()
		return User.get_user_by_email(current_user.email()) if current_user else None

	@staticmethod
	@memcached('get_user_by_email', USER_CACHE_TIME, lambda email: email)
	def get_user_by_email(email):
		try:
			user = User.get_by_key_name(email)
			return user if user else User.get_or_insert(key_name=email, name=email.split('@', 1)[0])
		except:
			def save_user(email):
				User.get_or_insert(key_name=email, name=email.split('@', 1)[0])
			deferred.defer(save_user, email)
			return User(key_name=email, name=email.split('@', 1)[0])

	@staticmethod
	def get_users_by_emails(emails):
		unique_emails = set(emails)
		comment_authors_dict = memcache.get_multi(unique_emails, 'get_user_by_email:')

		missed_emails = [email for email in unique_emails if email not in comment_authors_dict]
		if missed_emails:
			missed_user_keys = [db.Key.from_path('User', email) for email in missed_emails]
			missed_comment_authors = db.get(missed_user_keys, config=EVENTUAL_CONSISTENCY_CONFIG)
			missed_comment_authors_dict = dict(izip(missed_emails, missed_comment_authors))
			memcache_client.set_multi_async(missed_comment_authors_dict, USER_CACHE_TIME, 'get_user_by_email:')
			comment_authors_dict.update(missed_comment_authors_dict)
		return [comment_authors_dict[email] for email in emails]

	def get_gravatar(self, https=False):
		if https:
			return 'https://secure.gravatar.com/avatar/' + md5(self.key().name()).hexdigest()
		return 'http://www.gravatar.com/avatar/' + md5(self.key().name()).hexdigest()

	def status(self):
		flag = self.flag
		if not (flag & USER_FLAGS['active']):
			return 'banned'
		elif flag & USER_FLAGS['verified']:
				return 'verified'
		return 'unverified'


class Category(db.Model):
	# key name: category name
	path = db.StringProperty(required=True) # category path, separat and terminate by CATEGORY_PATH_DELIMETER

	_LIMIT = 1000 # the category amount is unlikely greater than 1000

	def to_dict(self):
		return {
			'key': self.key().name(),
			'path': self.path
		}

	@classmethod
	def from_dict(cls, entity):
		return cls(
			key_name=entity['key'],
			path=entity['path']
		)

	def level(self): # category level, 1 represent root category, 2 is the first level sub category, and so on
		return len(self.path.split(CATEGORY_PATH_DELIMETER)) - 1

	@memcached('get_sub_categories', CATEGORY_CACHE_TIME, lambda self, limit=_LIMIT: self.key().name())
	def get_sub_categories(self, limit=_LIMIT):
		path = self.path
		return Category.all().filter('path >', path).filter('path <', path + u'\ufffd').order('path').fetch(limit)

	def has_sub_categories(self):
		path = self.path
		return Category.all().filter('path >', path).filter('path <', path + u'\ufffd').count(1)

	@staticmethod
	@memcached('get_category_with_subs', CATEGORY_CACHE_TIME, lambda path, limit=_LIMIT: hash(path))
	def get_category_with_subs(path, limit=_LIMIT):
		return Category.all().filter('path >=', path).filter('path <', path + u'\ufffd').order('path').fetch(limit)

	@staticmethod
	@memcached('get_all_categories', CATEGORY_CACHE_TIME)
	def get_all_categories(limit=_LIMIT):
		return Category.all().order('path').fetch(limit)

	@memcached('get_articles_in_category', ARTICLES_CACHE_TIME,
			   lambda self, cursor=None, fetch_limit=ARTICLES_PER_PAGE:
				('%s_%s' % (self.key().name(), cursor)) if cursor else self.key().name())
	def get_articles(self, cursor=None, fetch_limit=ARTICLES_PER_PAGE):
		path = self.path
		query = Article.all().filter('published =', True).filter('category >=', path).filter('category <', path + u'\ufffd')
		return get_fetch_result_with_valid_cursor(query_with_cursor(query, cursor), fetch_limit, config=EVENTUAL_CONSISTENCY_CONFIG)

	@staticmethod
	def fill_pathes(path):
		if not path:
			return []
		names = path.split(CATEGORY_PATH_DELIMETER)
		each_path = ''
		all_pathes = []
		for name in names:
			name = name.strip()
			if not name:
				continue
			each_path += name + CATEGORY_PATH_DELIMETER
			all_pathes.append((each_path, name))
		return all_pathes

	@staticmethod
	def path_to_name(path):
		if path:
			return path.rstrip(CATEGORY_PATH_DELIMETER).rsplit(CATEGORY_PATH_DELIMETER, 1)[-1]
		return ''


def move_articles_between_categories(from_path, to_path):
	articles = Article.all().filter('category =', from_path).fetch(100)
	if not articles:
		memcache_client.delete_multi_async(['get_articles_in_category:' + Category.path_to_name(from_path), 'get_articles_in_category:' + Category.path_to_name(to_path)])
		mail.send_mail_to_admins(ADMIN_EMAIL, "Batch change articles' category successful.", u'Source category: %s\nobject category: %s' % (from_path, to_path))
		return
	for article in articles:
		article.category = to_path
	db.put(articles)
	deferred.defer(move_articles_between_categories, from_path, to_path)

def delete_category(path):
	articles = Article.all().filter('category =', path).fetch(100)
	if not articles:
		name = Category.path_to_name(path)
		db.delete(db.Key.from_path('Category', name))
		memcache_client.delete_multi_async(['get_all_categories', 'get_sub_categories:' + name, 'get_category_with_subs:%s' % hash(path), 'get_articles_in_category:' + name])
		tenjin.helpers.fragment_cache.store.delete('siderbar')
		yui.flush_all_server_cache()
		mail.send_mail_to_admins(ADMIN_EMAIL, 'Delete category successful.', u'Category path: ' + path)
		return
	for article in articles:
		article.category = None
	db.put(articles)
	deferred.defer(delete_category, path)


class Tag(db.Model):
	# key name: tag name
	count = db.IntegerProperty(default=0) # articles in this tag

	_LIMIT = 1000 # the tag amount is unlikely greater than 1000

	def to_dict(self):
		return {
			'key': self.key().name(),
			'count': self.count
		}

	@classmethod
	def from_dict(cls, entity):
		return cls(
			key_name=entity['key'],
			count=entity['count']
		)

	@memcached('get_articles_in_tag', ARTICLES_CACHE_TIME,
			   lambda self, cursor=None, fetch_limit=ARTICLES_PER_PAGE:
				('%s_%s' % (self.key().name(), cursor)) if cursor else self.key().name())
	def get_articles(self, cursor=None, fetch_limit=ARTICLES_PER_PAGE):
		query = Article.all().filter('tags =', self.key().name()).filter('published =', True)
		return get_fetch_result_with_valid_cursor(query_with_cursor(query, cursor), fetch_limit, config=EVENTUAL_CONSISTENCY_CONFIG)

	@staticmethod
	@memcached('get_all_tags', TAGS_CACHE_TIME)
	def get_all_tags(limit=_LIMIT):
		return Tag.all().fetch(limit)

	def update_count(self):
		self.count = Article.all().filter('tags =', self.key().name()).filter('published =', True).count(None)
		self.put()
		return self.count


def move_articles_between_tags(from_name, to_name):
	articles = Article.all().filter('tags =', from_name).fetch(100)
	if not articles:
		from_tag = Tag.get_by_key_name(from_name)
		if from_tag:
			from_tag.count = 0
			from_tag.put()

		to_tag = Tag.get_by_key_name(to_name)
		if to_tag:
			to_tag.update_count()

		memcache_client.delete_multi_async(['get_all_tags', 'get_articles_in_tag:' + from_name, 'get_articles_in_tag:' + to_name])
		mail.send_mail_to_admins(ADMIN_EMAIL, "Batch change articles' tag successful.", u'Source tag: %s\nobject tag: %s' % (from_name, to_name))
		return
	for article in articles:
		tags = article.tags
		while from_name in tags:
			tags.remove(from_name)
		if to_name not in tags:
			tags.append(to_name)
		article.tags = tags
	db.put(articles)
	deferred.defer(move_articles_between_tags, from_name, to_name)

def delete_tag(name):
	articles = Article.all().filter('tags =', name).fetch(100)
	if not articles:
		db.delete(db.Key.from_path('Tag', name))
		memcache_client.delete_multi_async(['get_all_tags', 'get_articles_in_tag:' + name])
		tenjin.helpers.fragment_cache.store.delete('siderbar')
		yui.flush_all_server_cache()
		mail.send_mail_to_admins(ADMIN_EMAIL, 'Delete tag successful.', u'Tag name: ' + name)
		return
	for article in articles:
		tags = article.tags
		while name in tags:
			tags.remove(name)
		article.tags = tags
	db.put(articles)
	deferred.defer(delete_tag, name)

def update_tags_count():
	tags = Tag.get_all_tags()
	if tags:
		for tag in tags:
			tag.count = Article.all().filter('tags =', tag.key().name()).filter('published =', True).count(None)
		db.put(tags) # since tags is normally not too many, no need to separate into several tasks

CONTENT_FORMAT_FLAG = {
	'plain': 0,
    'bbcode': 1,
    'html': 2
}

def _cache_articles(articles):
	size = len(articles)
	if size:
		last = size - 1
		mapping = {}
		for i in xrange(size):
			article = articles[i]
			id = article.key().id()
			published = article.published
			mapping['get_article_by_url:%s' % hash(article.url)] = article
			mapping['get_article_by_id:%s' % id] = article
			if i > 0:
				mapping['get_next_article:%s_%s' % (id, published)] = articles[i - 1]
			if i < last:
				mapping['get_previous_article:%s_%s' % (id, published)] = articles[i + 1]
		memcache_client.set_multi_async(mapping, ARTICLE_CACHE_TIME)


class Article(db.Model):
	# key id
	title = db.StringProperty(required=True)
	url = db.StringProperty(required=True) # relative URL
	content = db.TextProperty()
	format = db.IntegerProperty(default=CONTENT_FORMAT_FLAG['plain'], indexed=False) # parse format
	published = db.BooleanProperty(default=True) # whether publish to all
	time = db.DateTimeProperty(auto_now_add=True) # publish time
	mod_time = db.DateTimeProperty(auto_now_add=True) # last modified time
	keywords = db.StringListProperty() # search keywords, saved as lower case
	tags = db.StringListProperty()
	category = db.StringProperty() # category path
	hits = db.IntegerProperty(default=0) # views
	replies = db.IntegerProperty(default=0) # comments
	# password = db.StringProperty(indexed=False)
	# view_level = db.IntegerProperty(default=0, indexed=False)
	# closed = db.BooleanProperty(default=False, indexed=False) #  whether close comments

	_PATTERN = re.compile(r'\d{4}/\d{2}/\d{2}/.+')

	def to_dict(self):
		time = self.time
		time = '%d.%d' % (timegm(time.timetuple()), time.microsecond)
		mod_time = self.mod_time
		mod_time = '%d.%d' % (timegm(mod_time.timetuple()), mod_time.microsecond)
		entity = {
			'key': self.key().id(),
			'title': self.title,
			'url': self.url,
			'content': self.content,
			'format': self.format,
			'published': self.published,
			'time': time,
			'mod_time': mod_time,
			'category': self.category,
			'hits': self.hits,
			'replies': self.replies
		}
		if self.keywords:
			entity['keywords'] = self.keywords
		if self.tags:
			entity['tags'] = self.tags
		return entity

	@classmethod
	def from_dict(cls, entity):
		timestamp, microsecond = entity['time'].split('.')
		time = datetime.fromtimestamp(int(timestamp))
		time.replace(microsecond=int(microsecond))

		timestamp, microsecond = entity['mod_time'].split('.')
		mod_time = datetime.fromtimestamp(int(timestamp))
		mod_time.replace(microsecond=int(microsecond))
		return cls(
			key=db.Key.from_path('Article', entity['key']),
			title=entity['title'],
			url=entity['url'],
			content=entity['content'],
			format=entity['format'],
			published=entity['published'],
			time=time,
			mod_time=mod_time,
			keywords=entity.get('keywords', []),
			tags=entity.get('tags', []),
			category=entity['category'],
			hits=entity['hits'],
			replies=entity['replies']
		)

	@staticmethod
	@memcached('get_articles_for_homepage', ARTICLES_CACHE_TIME,
				lambda cursor=None, fetch_limit=ARTICLES_PER_PAGE: hash(cursor) if cursor else None)
	def get_articles_for_homepage(cursor=None, fetch_limit=ARTICLES_PER_PAGE):
		query = Article.all().filter('published =', True).order('-time')
		articles, cursor = get_fetch_result_with_valid_cursor(query_with_cursor(query, cursor), fetch_limit, config=EVENTUAL_CONSISTENCY_CONFIG)
		_cache_articles(articles)
		return articles, cursor

	@staticmethod
	def get_unpublished_articles(cursor=None, fetch_limit=ARTICLES_PER_PAGE):
		query = Article.all().filter('published =', False).order('-mod_time')
		articles, cursor = get_fetch_result_with_valid_cursor(query_with_cursor(query, cursor), fetch_limit)
		_cache_articles(articles)
		return articles, cursor

	@staticmethod
	@memcached('get_articles_for_feed', FEED_CACHE_TIME)
	def get_articles_for_feed(fetch_limit=ARTICLES_FOR_FEED):
		return Article.all().filter('published =', True).order('-mod_time').fetch(fetch_limit)

	@staticmethod
	def get_recent_articles(cursor=None, fetch_limit=ARTICLES_PER_PAGE):
		query = Article.all().order('-time')
		articles, cursor = get_fetch_result_with_valid_cursor(query_with_cursor(query, cursor), fetch_limit)
		return articles, cursor

	@staticmethod
	@memcached('get_article_by_url', ARTICLE_CACHE_TIME, lambda url: hash(url))
	def get_article_by_url(url):
		if len(url) <= 500:
			article = Article.all().filter('url =', url).get(config=EVENTUAL_CONSISTENCY_CONFIG)
			if article:
				memcache_client.set_multi_async({'get_article_by_id:%s' % article.key().id(): article}, ARTICLE_CACHE_TIME)
				return article
		return ENTITY_NOT_FOUND

	@staticmethod
	@memcached('get_article_by_id', ARTICLE_CACHE_TIME, lambda id: id)
	def get_article_by_id(id):
		if id > 0:
			article = Article.get_by_id(id)
			if article:
				memcache_client.set_multi_async({'get_article_by_url:%s' % hash(article.url): article}, ARTICLE_CACHE_TIME)
				return article
		return ENTITY_NOT_FOUND

	@staticmethod
	def get_articles_by_ids(article_ids):
		unique_article_ids = set(article_ids)
		unique_article_ids_str = [str(id) for id in unique_article_ids]
		articles_dict = memcache.get_multi(unique_article_ids_str, 'get_article_by_id:')

		missed_article_ids = [article_id for article_id in unique_article_ids if article_id not in articles_dict]
		if missed_article_ids:
			missed_articles = Article.get_by_id(missed_article_ids, config=EVENTUAL_CONSISTENCY_CONFIG)
			missed_articles_dict = dict(izip(unique_article_ids_str, missed_articles))
			memcache_client.set_multi_async(missed_articles_dict, ARTICLE_CACHE_TIME, 'get_article_by_id:')
			articles_dict.update(missed_articles_dict)

			missed_article_urls = [article.url for article in missed_articles]
			missed_articles_dict = dict(izip(missed_article_urls, missed_articles))
			memcache_client.set_multi_async(missed_articles_dict, ARTICLE_CACHE_TIME, 'get_article_by_url:')
		return [articles_dict[str(id)] for id in article_ids]

	def category_name(self):
		return Category.path_to_name(self.category)

	def html_summary(self):
		format = self.format
		content = self.content
		if SUMMARY_DELIMETER.search(content):
			summary = SUMMARY_DELIMETER.split(content, 1)[0]
		elif SUMMARY_DELIMETER2.search(content):
			summary = SUMMARY_DELIMETER2.split(content, 1)[0]
		else:
			summary = content
		if format & CONTENT_FORMAT_FLAG['bbcode']:
			return convert_bbcode_to_html(summary, escape=not(format & CONTENT_FORMAT_FLAG['html']))
		if format & CONTENT_FORMAT_FLAG['html']:
			return summary
		else:
			return parse_plain_text(summary)

	def html_content(self):
		format = self.format
		content = self.content
		if SUMMARY_DELIMETER.search(content):
			content = SUMMARY_DELIMETER.sub('', content, 1)
		elif SUMMARY_DELIMETER2.search(content):
			content = SUMMARY_DELIMETER2.split(content, 1)[1]

		if format & CONTENT_FORMAT_FLAG['bbcode']:
			return convert_bbcode_to_html(content, escape=not(format & CONTENT_FORMAT_FLAG['html']))
		if format & CONTENT_FORMAT_FLAG['html']:
			return content
		else:
			return parse_plain_text(content)

	def previous_article(self, published):
		previous_article = None
		try:
			previous_article = Article.all().filter('published =', published).filter('time <', self.time).order('-time').get(config=QUICK_LIMITED_EVENTUAL_CONSISTENCY_CONFIG)
			if previous_article:
				memcache_client.set_multi_async({
					'get_previous_article:%s_%s' % (self.key().id(), published): previous_article,
					'get_next_article:%s_%s' % (previous_article.key().id(), published): self,
					'get_article_by_url:%s' % hash(previous_article.url): previous_article,
					'get_article_by_id:%s' % previous_article.key().id(): previous_article
				}, ARTICLE_CACHE_TIME)
				return previous_article
			memcache_client.set_multi_async({'get_previous_article:%s_%s' % (self.key().id(), published): ENTITY_NOT_FOUND}, ARTICLE_CACHE_TIME)
			return ENTITY_NOT_FOUND
		except:
			return previous_article

	def next_article(self, published):
		next_article = None
		try:
			next_article = Article.all().filter('published =', published).filter('time >', self.time).order('time').get(config=QUICK_LIMITED_EVENTUAL_CONSISTENCY_CONFIG)
			if next_article:
				memcache_client.set_multi_async({
					'get_next_article:%s_%s' % (self.key().id(), published): next_article,
					'get_previous_article:%s_%s' % (next_article.key().id(), published): self,
					'get_article_by_url:%s' % hash(next_article.url): next_article,
					'get_article_by_id:%s' % next_article.key().id(): next_article
				}, ARTICLE_CACHE_TIME)
				return next_article
			memcache_client.set_multi_async({'get_next_article:%s_%s' % (self.key().id(), published): ENTITY_NOT_FOUND}, ARTICLE_CACHE_TIME)
			return ENTITY_NOT_FOUND
		except:
			return next_article

	def nearby_articles(self, published=True):
		key = '%s_%s' % (self.key().id(), published)
		previous_key = 'get_previous_article:' + key
		next_key = 'get_next_article:' + key
		nearby_articles = memcache.get_multi((next_key, previous_key))

		previous_article = nearby_articles.get(previous_key, None)
		if previous_article is None:
			previous_article = self.previous_article(published)

		next_article = nearby_articles.get(next_key, None)
		if next_article is None:
			next_article = self.next_article(published)
		return previous_article, next_article

	@staticmethod
	@memcached('relative_articles', ARTICLES_CACHE_TIME, lambda id, limit: id)
	def relative_articles(id, limit):
		if id <= 0:
			return []
		article = Article.get_article_by_id(id)
		if not article:
			return []
		article_key = article.key()
		keywords = article.keywords
		relative_article_keys = set()
		left = limit
		total = 0
		if keywords:
			# Keys only queries do not support IN filters.
			for keyword in keywords:
				relative_article_keys |= set(Article.all(keys_only=True).filter('keywords =', keyword).filter('published =', True).fetch(left + 1))
				relative_article_keys.discard(article_key)
				total = len(relative_article_keys)
				if total >= limit:
					return db.get(list(relative_article_keys)[:limit])
			left -= total
		tags = article.tags
		if tags:
			for tag in tags:
				new_article_keys = set(Article.all(keys_only=True).filter('tags =', tag).filter('published =', True).fetch(left + 1)) - relative_article_keys
				new_article_keys.discard(article_key)
				if len(new_article_keys) >= left:
					return db.get(list(relative_article_keys) + list(new_article_keys)[:left])
				relative_article_keys |= new_article_keys
			left = limit - len(relative_article_keys)
		category = article.category
		if category:
			new_article_keys = set(Article.all(keys_only=True).filter('category >=', category).filter('category <', category + u'\ufffd').filter('published =', True).fetch(left + 1)) - relative_article_keys
			new_article_keys.discard(article_key)
			if len(new_article_keys) >= left:
				return db.get(list(relative_article_keys) + list(new_article_keys)[:left])
			relative_article_keys |= new_article_keys
		if relative_article_keys:
			return Article.get_articles_by_ids([key.id() for key in relative_article_keys])
		return []

	@staticmethod
	def calc_hits(key):
		article_id = int(key.split(':')[1])
		if article_id <= 0:
			return True
		def calc():
			try:
				hits = memcache.get(key)
				if hits:
					article = Article.get_by_id(article_id)
					if article:
						article.hits += hits
						article.put()
						memcache_client.set_multi_async({'get_article_by_id:%s' % article.key().id(): article, 'get_article_by_url:%s' % hash(article.url): article}, ARTICLE_CACHE_TIME)
						memcache.decr(key, hits)
				return True
			except:
				return False
		try:
			return db.run_in_transaction(calc)
		except:
			return False

	@staticmethod
	def search(keywords, published, cursor=None, fetch_limit=ARTICLES_PER_PAGE):
		if not cursor:
			query = Article.all().filter('title =', keywords)
			if published is not None:
				query.filter('published =', published)
			article = query.fetch(1) # it's unlikely to have several articles with the same name, but you can change the limit as you need
			if article:
				fetch_limit -= 1
		else:
			article = []
		if keywords:
			keywords = set(keywords.split())
			query = Article.all()
			for keyword in keywords:
				query.filter('keywords =', keyword.lower())
			if published is not None:
				query.filter('published =', published)
			articles, cursor = get_fetch_result_with_valid_cursor(query_with_cursor(query, cursor), fetch_limit)
			return (article + articles, cursor)
		else:
			return article, None

	def quoted_url(self):
		return escape(quoted_string(self.url))

	def quoted_not_escaped_url(self):
		return quoted_string(self.url)

	@staticmethod
	def remove(article_id):
		if article_id > 0:
			article = Article.get_by_id(article_id)
			if article:
				try:
					article_key = article.key()
					comments = Comment.all(keys_only=True).ancestor(article_key).fetch(500)
					while comments:
						db.delete(comments)
						comments = Comment.all(keys_only=True).ancestor(article_key).fetch(500)
					tag_names = article.tags
					article.delete()
					clear_article_memcache(article_id, article.url)
					clear_latest_comments_memcache(article_id)
				except:
					return False

				if tag_names:
					try:
						tags = Tag.get_by_key_name(tag_names)
						new_tags = []
						for tag in tags:
							if tag:
								tag.count -= 1
								if tag.count < 0:
									tag.count = 0
							new_tags.append(tag)
						if new_tags:
							db.put(new_tags)
					except:
						pass
			return True
		return False


class Comment(db.Model):
	# parent: Article
	email = db.StringProperty(required=True) # commenter's email
	content = db.TextProperty()
	format = db.IntegerProperty(default=CONTENT_FORMAT_FLAG['plain'], indexed=False) # parse format
	ua = db.StringListProperty(indexed=False) # user agent information
	time = db.DateTimeProperty(auto_now_add=True) # submit time

	def to_dict(self):
		time = self.time
		time = '%d.%d' % (timegm(time.timetuple()), time.microsecond)
		entity = {
			'key': (self.parent_key().id(), self.key().id()),
			'email': self.email,
			'content': self.content,
			'format': self.format,
			'time': time
		}
		if 'ua' in entity:
			entity['ua'] = self.ua
		return entity

	@classmethod
	def from_dict(cls, entity):
		keys = entity['key']
		timestamp, microsecond = entity['time'].split('.')
		time = datetime.fromtimestamp(int(timestamp))
		time.replace(microsecond=int(microsecond))

		return cls(
			key=db.Key.from_path('Article', keys[0], 'Comment', keys[1]),
			email=entity['email'],
			content=entity['content'],
			format=entity['format'],
			ua=entity.get('ua', []),
			time=time
		)

	@staticmethod
	# get_comments_with_user_by_article_key uses more commonly, no need to cache twice
	def get_comments_by_article_key(article_key, order=True, cursor=None, fetch_limit=COMMENTS_PER_PAGE):
		query = Comment.all().ancestor(article_key).order('time' if order else '-time')
		return get_fetch_result_with_valid_cursor(query_with_cursor(query, cursor), fetch_limit, config=EVENTUAL_CONSISTENCY_CONFIG)

	@staticmethod
	@memcached('get_comments_with_user_by_article_key', COMMENTS_CACHE_TIME,
			   lambda article_key, order=True, cursor=None, fetch_limit=COMMENTS_PER_PAGE:
				('%s_%s_%s' % (article_key.id(), order, cursor)))
	def get_comments_with_user_by_article_key(article_key, order=True, cursor=None, fetch_limit=COMMENTS_PER_PAGE):
		comments_with_cursor = Comment.get_comments_by_article_key(article_key, order, cursor, fetch_limit)
		comments = comments_with_cursor[0]
		comment_authors = get_authors_of_comments(comments) if comments else []
		return comments_with_cursor, comment_authors

	@staticmethod
	def get_comment_by_id(comment_id, article_id):
		return Comment.get_by_id(comment_id, db.Key.from_path('Article', article_id))

	def html_content(self):
		format = self.format
		content = self.content
		if format & CONTENT_FORMAT_FLAG['bbcode']:
			return convert_bbcode_to_html(content, escape=not(format & CONTENT_FORMAT_FLAG['html']))
		if format & CONTENT_FORMAT_FLAG['html']:
			return content
		else:
			return parse_plain_text(content)

	@staticmethod
	@memcached('latest_comments', 0, lambda limit: limit)
	def latest_comments(limit):
		comments = Comment.all().order('-time').fetch(limit)
		if comments:
			return comments, get_articles_of_comments(comments), get_authors_of_comments(comments)
		return [], [], []

def update_articles_replies(cursor=None):
	query = query_with_cursor(Article.all(), cursor)
	articles = query.fetch(100)
	if articles:
		for article in articles:
			article.replies = Comment.all().ancestor(article).count(None)
		db.put(articles)
	if len(articles) < 100:
		mail.send_mail_to_admins(ADMIN_EMAIL, "Articles' replies count has been updated.", 'You can go to check it now.')
	else:
		deferred.defer(update_articles_replies, query.cursor())

def update_article_replies(article_key):
	def update():
		article = Article.get(article_key)
		if article:
			article.replies = Comment.all().ancestor(article_key).count(None)
			article.put()
	db.run_in_transaction(update)

def delete_comments_of_user(email, article_keys=None, cursor=None):
	query = Comment.all(keys_only=True).filter('email =', email)
	comment_keys = query_with_cursor(query, cursor).fetch(100)
	if not article_keys:
		article_keys = set()
	if comment_keys:
		db.delete(comment_keys)
		article_keys |= set([comment_key.parent() for comment_key in comment_keys])
	if len(comment_keys) == 100:
		deferred.defer(delete_comments_of_user, email, article_keys, query.cursor())
	else:
		clear_latest_comments_memcache()
		for article_key in article_keys:
			deferred.defer(update_article_replies, article_key)

def get_authors_of_comments(comments):
	return User.get_users_by_emails([comment.email for comment in comments])

def get_articles_of_comments(comments):
	return Article.get_articles_by_ids([comment.parent_key().id() for comment in comments])


class Sitemap(db.Model):
	# key id
	content = db.TextProperty()
	count = db.IntegerProperty(default=0, indexed=False)

	_LIMIT = 1000

	@staticmethod
	def fill(id, cursor=None):
		fetch_limit = Sitemap._LIMIT
		if not id: # incremental
			last_sitemap_id = Sitemap.all().count(None)
			if last_sitemap_id:
				articles = Article.all().filter('published =', True).filter('time >', datetime.utcnow() - timedelta(days=1)).fetch(fetch_limit) # should less than fetch_limit
				length = len(articles)
				if length:
					last_sitemap = Sitemap.get_by_id(last_sitemap_id)
					left = fetch_limit - last_sitemap.count - length
					if left >= 0:
						last_sitemap.content += engine.render('sitemap.xml', {'articles': articles})
						last_sitemap.count += length
						last_sitemap.put()
					else:
						last_sitemap.content += engine.render('sitemap.xml', {'articles': articles[:left]})
						last_sitemap.count = fetch_limit
						new_sitemap = Sitemap(key=db.Key.from_path('Sitemap', last_sitemap_id + 1), content=engine.render('sitemap.xml', {'articles': articles[left:]}), count=-left)
						db.put([last_sitemap, new_sitemap])
					memcache.delete('get_sitemap')
				return 0, None # done
			else:
				return fetch_limit, None # need generate all
		else:
			if id == 1: # remove all sitemaps before generating all
				sitemap_keys = Sitemap.all(keys_only=True).fetch(fetch_limit)
				if sitemap_keys:
					db.delete(sitemap_keys)
			query = Article.all().filter('published =', True)
			articles = query_with_cursor(query, cursor).fetch(fetch_limit)
			if articles:
				content = engine.render('sitemap.xml', {'articles': articles})
				Sitemap(key=db.Key.from_path('Sitemap', id), content=content, count=len(articles)).put()
				return len(articles), query.cursor()
			memcache.delete('get_sitemap')
			return 0, None

	@staticmethod
	@memcached('get_sitemap', SITEMAP_CACHE_TIME)
	def get_sitemap():
		sitemaps = Sitemap.all().fetch(Sitemap._LIMIT)
		xml = ['<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
		for sitemap in sitemaps:
			xml.append(sitemap.content)
		xml.append('</urlset>')
		return ''.join(xml)


class Feed(db.Model):
	content = db.TextProperty()
	cursor = db.StringProperty(indexed=False)
	time = db.DateTimeProperty(auto_now_add=True)


class Subscriber(db.Model):
	# key name: ua
	count = db.IntegerProperty(default=1, indexed=False) # subscribers
	time = db.DateTimeProperty(auto_now=True) # last fetch time

	_LIMIT = 100000

	@staticmethod
	def set_subscriber(user_agent, count):
		if len(user_agent) > 500:
			user_agent = user_agent[:500]
		key = 'get_subscriber:' + user_agent
		try:
			if memcache.get(key) != count:
				rpc = memcache_client.get_multi_async(['new_subscribers'])
				memcache_client.set_multi_async({key: count}, SUBSCRIBER_CACHE_TIME)
				new_subscribers = rpc.get_result()
				if new_subscribers and 'new_subscribers' in new_subscribers:
					new_subscribers = new_subscribers['new_subscribers']
				new_subscribers[user_agent] = count
				memcache_client.set_multi_async({'new_subscribers': new_subscribers}, SUBSCRIBER_CACHE_TIME)
		except:
			pass

	@staticmethod
	@memcached('get_subscribers', SUBSCRIBERS_CACHE_TIME)
	def get_subscribers():
		subscribers = Subscriber.all().fetch(Subscriber._LIMIT)
		if subscribers:
			return reduce(lambda x, y: x + y.count, subscribers, 0)
		return 0

	@staticmethod
	def update_new_subscribers():
		new_subscribers = memcache.get('new_subscribers')
		if new_subscribers:
			subscribers = [Subscriber(key_name=user_agent.decode('iso-8859-1', 'ignore'), count=count) for user_agent, count in new_subscribers.iteritems()]
			while subscribers:
				db.put_async(subscribers[:500])
				subscribers = subscribers[500:]
			memcache.delete('new_subscribers')

	@staticmethod
	def remove_old_subscribers():
		old_subscribers = Subscriber.all(keys_only=True).filter('time <', datetime.utcnow() - timedelta(days=1)).fetch(1000)
		if old_subscribers:
			db.delete_async(old_subscribers)
			memcache_client.delete_multi_async(['get_subscribers'])


class Twitter(db.Model):
	name = db.StringProperty(indexed=False)
	token = db.StringProperty(indexed=False)
	secret = db.StringProperty(indexed=False)

	def to_dict(self):
		return {
			'name': self.name,
			'token': self.token,
			'secret': self.secret
		}

	@staticmethod
	@memcached('get_twitter')
	def get_twitter():
		return Twitter.get_by_id(1) or ENTITY_NOT_FOUND

	@staticmethod
	def set_twitter(**kw):
		try:
			twitter = Twitter(key=db.Key.from_path('Twitter', 1), **kw)
			twitter.put()
			memcache.set('get_twitter', twitter)
			return True
		except:
			return False


class XmlRpc(db.Model):
	username = db.StringProperty(indexed=False)
	password = db.StringProperty(indexed=False)

	@staticmethod
	@memcached('get_xml_rpc')
	def get_xml_rpc():
		return XmlRpc.get_by_id(1) or ENTITY_NOT_FOUND

	@staticmethod
	def set_xml_rpc(username, password):
		try:
			key = db.Key.from_path('XmlRpc', 1)
			if username and password:
				xml_rpc = XmlRpc(key=key, username=username, password=password)
				xml_rpc.put()
				memcache.set('get_xml_rpc', xml_rpc)
				return 1
			else:
				db.delete(key)
				memcache.set('get_xml_rpc', ENTITY_NOT_FOUND)
				return 0
		except:
			return -1


def export_entities(limit=100000):
	import gzip
	try:
		from io import BytesIO
	except ImportError:
		from cStringIO import StringIO as BytesIO

	articles = Article.all().fetch(limit)
	users = User.all().fetch(limit)
	categories = Category.all().fetch(limit)
	tags = Tag.all().fetch(limit)
	comments = Comment.all().fetch(limit)
	twitter = Twitter.get_twitter()

	entities = {
		'articles': [article.to_dict() for article in articles],
		'users': [user.to_dict() for user in users],
		'categories': [category.to_dict() for category in categories],
		'tags': [tag.to_dict() for tag in tags],
		'comments': [comment.to_dict() for comment in comments],
	    'twitter': twitter.to_dict() if twitter else None
	}

	del articles
	del users
	del categories
	del tags
	del comments
	del twitter

	json_content = json.dumps(entities)
	del entities

	fileobj = BytesIO()
	gzip_file = gzip.GzipFile('backup.json', mode='wb', fileobj=fileobj)
	gzip_file.write(json_content)
	gzip_file.close()
	gzip_content = fileobj.getvalue()
	fileobj.close()

	return gzip_content

def export_recent_entities(limit=100000):
	import gzip
	try:
		from io import BytesIO
	except ImportError:
		from cStringIO import StringIO as BytesIO

	last_update = datetime.utcnow() - timedelta(days=1)
	article_keys = set(Article.all(keys_only=True).filter('time >', last_update).fetch(limit) + Article.all(keys_only=True).filter('mod_time >', last_update).fetch(limit))
	articles = db.get(article_keys)
	comments = Comment.all().filter('time >', last_update).fetch(limit)

	if not (articles or comments):
		return None

	entities = {
		'articles': [article.to_dict() for article in articles],
		'comments': [comment.to_dict() for comment in comments]
	}

	del articles
	del comments

	json_content = json.dumps(entities)
	del entities

	fileobj = BytesIO()
	gzip_file = gzip.GzipFile('backup.json', mode='wb', fileobj=fileobj)
	gzip_file.write(json_content)
	gzip_file.close()
	gzip_content = fileobj.getvalue()
	fileobj.close()

	return gzip_content

IMPORT_ENTITIES_RETURN_MESSAGES = {
	0: u'Import sucessfully.',
	1: u'Import failed, can\'t extract the file.',
	2: u'Import failed, wrong file content.',
	3: u'Import failed, datastore error.',
}

def import_entities(fileobj):
	import gzip

	try:
		gzip_file = gzip.GzipFile('backup.json', mode='rb', fileobj=fileobj)
		json_content = gzip_file.read()
		gzip_file.close()
	except:
		logging.exception('Extract fail:')
		return 1

	try:
		entites = json.loads(json_content)
		del json_content

		new_entites = []

		for key, model in (('articles', Article), ('users', User), ('categories', Category), ('tags', Tag), ('comments', Comment)):
			if key in entites:
				new_entites += [model.from_dict(entity) for entity in entites[key]]
				del entites[key]
	except:
		logging.exception('File format error:')
		return 2

	try:
		rpcs = []
		while new_entites:
			rpcs.append(db.put_async(new_entites[:500]))
			new_entites = new_entites[500:]
		twitter = entites.get('twitter', None)
		if twitter:
			Twitter.set_twitter(**twitter)
		for rpc in rpcs:
			rpc.get_result()
	except:
		logging.exception('Datastore error:')
		return 3
	return 0

def generate_missing_entities(step='article', categories=None, tags=None, users=None, cursor=None):
	if step == 'article':
		if not categories:
			categories = set()
		if not tags:
			tags = set()
		query = Article.all()
		articles = query_with_cursor(query, cursor).fetch(100)

		categories |= set([article.category for article in articles])
		new_tags = []
		for article in articles:
			if article.tags:
				new_tags += article.tags
		tags |= set(new_tags)

		if len(articles) == 100:
			deferred.defer(generate_missing_entities, step, categories, tags, users, query.cursor())
		else:
			if categories:
				category_pathes = []
				category_names = []
				for category in categories:
					if category and len(category) >= 2 and category[-1] == CATEGORY_PATH_DELIMETER:
						category_pathes.append(category)
						category_names.append(Category.path_to_name(category))
				if category_pathes:
					categories = Category.get_by_key_name(category_names)
					new_categories = [Category(key_name=category_name, path=category_path) for category_name, category_path, category in izip(category_names, category_pathes, categories) if not category]
					db.put(new_categories)
					clear_categories_memcache()
			if tags:
				tag_names = list(tags)
				tags = Tag.get_by_key_name(tag_names)
				new_tags = [Tag(key_name=tag_name) for tag_name, tag in izip(tag_names, tags) if not tag]
				db.put(new_tags)
				clear_tags_memcache()
			deferred.defer(generate_missing_entities, 'comment')
	elif step == 'comment':
		if not users:
			users = set()
		query = Comment.all()
		comments = query_with_cursor(query, cursor).fetch(200)
		users |= set([comment.email for comment in comments])

		if len(comments) == 200:
			deferred.defer(generate_missing_entities, step, users=users, cursor=query.cursor())
		elif users:
			emails = list(users)
			users = User.get_by_key_name(emails)
			new_users = [User(key_name=email, name=email.split('@', 1)[0]) for email, user in izip(emails, users) if not user]
			rpcs = []
			while new_users:
				rpcs.append(db.put_async(new_users[:500]))
				new_users = new_users[500:]
			for rpc in rpcs:
				rpc.get_result()
