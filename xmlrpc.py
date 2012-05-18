# -*- coding: utf-8 -*-

from SimpleXMLRPCServer import SimpleXMLRPCDispatcher
from xmlrpclib import DateTime, Fault
from model import *


def authorized(pos=1):
	'''
	@type pos: int
	@param pos: the username parameter position
	'''
	def wrap(method):
		def authorized_method(*args):
			xml_rpc = XmlRpc.get_xml_rpc()
			if not (xml_rpc and xml_rpc.username and xml_rpc.password):
				raise Fault(403, 'XML-RPC not enable.')
			if not (args[pos] == xml_rpc.username and args[pos + 1] == xml_rpc.password):
				raise Fault(403, 'Authentication failed.')
			return method(*(args[:pos] + args[pos + 2:])) # remove username and password
		return authorized_method
	return wrap

def article_to_struct(article):
	time = article.time
	local_time = convert_to_local_time(time)
	quoted_url = article.quoted_url()
	full_url = BLOG_HOME_FULL_URL + quoted_url
	category = article.category
	category = [category] if category else []

	return {
		'postid': str(article.key().id()),
		'title': article.title,
		'dateCreated': DateTime(time),
		'date_created_gmt': DateTime(local_time),
		'link': full_url,
		'permaLink': full_url,
		'description': unicode(article.html_content()),
		'categories': category,
		'userid': '1',
		'mt_keywords': ','.join(article.tags),
		'mt_excerpt': '',
		'mt_text_more': '',
		'mt_allow_comments': 1,
		'mt_allow_pings': 0,
		'custom_fields': [],
		'post_status': 'publish' if article.published else 'draft',
		'sticky': 0,
		'wp_author_display_name': BLOG_AUTHOR,
 		'wp_author_id': '1',
 		'wp_password': '',
 		'wp_slug': quoted_url,
	}

def get_article_by_id(post_id):
	try:
		article_id = int(post_id)
	except:
		raise Fault(404, "Edit failed, the article doesn't exist.")
	if article_id <= 0:
		raise Fault(404, "Edit failed, the article doesn't exist.")
	article = Article.get_by_id(article_id)
	if not article:
		raise Fault(404, "Edit failed, the article doesn't exist.")
	return article

class BloggerApi:
	prefix = 'blogger.'

	@staticmethod
	@authorized()
	def getUsersBlogs(appkey):
		return [{'url': BLOG_HOME_FULL_URL, 'blogid': '1', 'isAdmin': True, 'blogName': BLOG_TITLE, 'xmlrpc': BLOG_HOME_FULL_URL + 'rpc'}]

	@staticmethod
	@authorized()
	def getUserInfo(appkey):
		return {'userid': '1', 'firstname': BLOG_AUTHOR, 'lastname': '', 'nickname': BLOG_AUTHOR, 'email': ADMIN_EMAIL, 'url':''}
	
	@staticmethod
	@authorized(2)
	def deletePost(appkey, postid, publish):
		try:
			if Article.remove(int(postid)):
				return True
			raise Fault(404, "Article doesn't exist.")
		except:
			raise Fault(500, 'Article deleting failed.')


class MetaWeblogApi:
	prefix = 'metaWeblog.'

	@staticmethod
	@authorized()
	def newPost(blogid, struct, publish):
		if 'title' not in struct:
			raise Fault(400, 'Save failed, the article title cannot be empty.')
		title = strip(struct['title'])
		if not title:
			raise Fault(400, 'Save failed, the article title cannot be empty.')

		if 'description' not in struct:
			raise Fault(400, 'Save failed, the article content cannot be empty.')
		content = struct['description']
		if not content:
			raise Fault(400, 'Save failed, the article content cannot be empty.')

		try:
			if 'dateCreated' in struct:
				time = parse_iso8601_time(struct['dateCreated'].value)
			else:
				time = datetime.utcnow()
		except:
			time = datetime.utcnow()

		if REPLACE_SPECIAL_CHARACTERS_FOR_URL:
			url = formatted_date_for_url(time) + replace_special_characters_for_url(title)
		else:
			url = formatted_date_for_url(time) + title
		if Article.all().filter('url =', url).count(1):
			raise Fault(400, 'Save failed, there is already an article with the same URL.')

		tags = []
		try:
			if 'mt_keywords' in struct:
				tags = struct['mt_keywords'].strip().split()
				tags = list(set(tags))
		except:
			pass

		category = None
		try:
			if 'categories' in struct:
				categories = struct['categories']
				if categories:
					category = categories[0].strip() or None
		except:
			pass

		try:
			article = Article(
				title=title,
				url=url,
				content=content,
				format=CONTENT_FORMAT_FLAG['html'],
				published=publish,
				tags=tags,
				category=category,
				time=time,
				mod_time=time
			)
			article.put()

			try:
				if tags:
					tags = Tag.get_by_key_name(tags)
					tag_set = set(tags)
					tag_set.discard(None)
					tags = list(tag_set)
					if tags:
						for tag in tags:
							tag.count += 1
						db.put(tags)
			except:
				pass

			if publish:
				clear_article_memcache()
				deferred.defer(ping_hubs, BLOG_FEED_URL)
				deferred.defer(ping_xml_rpc, BLOG_HOME_FULL_URL + article.quoted_url())

			return str(article.key().id())
		except:
			raise Fault(500, 'Save failed, the datastore has some error or is busy now.')

	@staticmethod
	@authorized()
	def editPost(postid, struct, publish):
		article = get_article_by_id(postid)

		if 'title' not in struct:
			raise Fault(400, 'Edit failed, the article title cannot be empty.')
		title = strip(struct['title'])
		if not title:
			raise Fault(400, 'Edit failed, the article title cannot be empty.')
		article.title = title

		if 'description' not in struct:
			raise Fault(400, 'Edit failed, the article content cannot be empty.')
		content = struct['description']
		if not content:
			raise Fault(400, 'Edit failed, the article content cannot be empty.')
		article.content = content

		article.format = CONTENT_FORMAT_FLAG['html']

		article.published = publish

		try:
			if 'dateCreated' in struct:
				time = parse_iso8601_time(struct['dateCreated'].value)
				article_time = article.time
				if time != article_time:
					if time > article_time:
						if time - article_time > ONE_SECOND:
							article.time = time
					else:
						if article_time - time > ONE_SECOND:
							article.time = time
		except:
			pass

		article.mod_time = datetime.utcnow()

		tags = []
		old_tags = set(article.tags)
		try:
			if 'mt_keywords' in struct:
				tags = struct['mt_keywords'].strip().split()
		except:
			pass

		category = None
		try:
			if 'categories' in struct:
				categories = struct['categories']
				if categories:
					category = categories[0].strip() or None
		except:
			pass

		try:
			article.put()

			new_tags = set(tags)
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
				db.put(changed_tags)

			clear_article_memcache()
			if publish:
				deferred.defer(ping_hubs, BLOG_FEED_URL)
				deferred.defer(ping_xml_rpc, BLOG_HOME_FULL_URL + article.quoted_url())
			return str(article.key().id())
		except:
			raise Fault(500, 'Edit failed, the datastore has some error or is busy now.')

	@staticmethod
	@authorized()
	def getPost(postid):
		return article_to_struct(get_article_by_id(postid))

	@staticmethod
	@authorized()
	def getRecentPosts(blogid, numberOfPosts):
		if numberOfPosts > 0:
			recent_articles = Article.get_recent_articles(fetch_limit=numberOfPosts)
		else:
			recent_articles = Article.get_recent_articles()
		return [article_to_struct(article) for article in recent_articles[0]]

	@staticmethod
	@authorized()
	def getCategories(blogid):
		categories = Category.get_all_categories()
		return [{'description': category.key().name(), 'htmlUrl': '', 'rssUrl': ''} for category in categories]


class WordPressApi:
	prefix = 'wp.'

	@staticmethod
	@authorized(0)
	def getUsersBlogs():
		return [{'url': BLOG_HOME_FULL_URL, 'blogid': '1', 'isAdmin': True, 'blogName': BLOG_TITLE, 'xmlrpc': BLOG_HOME_FULL_URL + 'rpc'}]

	@staticmethod
	@authorized()
	def getTags(blog_id):
		tags = Tag.get_all_tags()
		return [{'tag_id': 0, 'name': tag.key().name(), 'count': tag.count, 'slug': '', 'html_url': '', 'rss_url': ''} for tag in tags]

	@staticmethod
	@authorized()
	def getCommentCount(blog_id, post_id):
		article = get_article_by_id(post_id)
		return [{'approved': 1, 'awaiting_moderation': 0, 'spam': 0, 'total_comments': article.replies}]

	@staticmethod
	@authorized()
	def getPostStatusList(blog_id):
		return ['draft', 'publish']

	@staticmethod
	@authorized()
	def getCategories(blogid):
		categories = Category.get_all_categories()
		return [{'categoryId': 0, 'parentId': 0, 'description': category.key().name(), 'categoryName': category.key().name(), 'htmlUrl': '', 'rssUrl': ''} for category in categories]


class XMLRPCDispatcher(SimpleXMLRPCDispatcher):
	def __init__(self, apis):
		SimpleXMLRPCDispatcher.__init__(self, True, 'utf-8')
		funcs = {}
		for api in apis:
			prefix = api.prefix
			for attr_name in dir(api):
				attr = getattr(api, attr_name)
				if callable(attr):
					funcs[prefix + attr_name] = attr
		self.funcs = funcs
		self.register_introspection_functions()

dispatcher = XMLRPCDispatcher((BloggerApi, MetaWeblogApi, WordPressApi))


class RpcHandler(yui.RequestHandler):
	def post(self):
		self.set_content_type('text/xml')
		logging.info('-'*10)
		logging.info(self.request.body)
		response = dispatcher._marshaled_dispatch(self.request.body)
		logging.info(response)
		logging.info('='*10)
		self.write(response)


class RsdPage(BaseHandler):
	@yui.server_cache(0, False)
	@yui.client_cache(0, 'public')
	def get(self):
		self.set_content_type('text/xml')
		self.echo('RSD.xml')
