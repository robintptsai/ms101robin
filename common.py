# -*- coding: utf-8 -*-

from datetime import datetime, timedelta, tzinfo
import hmac
from hashlib import sha1
from itertools import izip
import logging
import os.path
from random import getrandbits
import re
from time import time, mktime
from traceback import format_exc
from urllib import quote, unquote, urlencode
from urlparse import urlunsplit

from google.appengine.api import mail, memcache, taskqueue, urlfetch, users
from google.appengine.ext import db, deferred
from postmarkup import _re_html, render_bbcode, quoted_string, quoted_url
try:
	import json
except ImportError:
	import simplejson as json
import tenjin
from tenjin.helpers import *
import yui

from setting import *


memcache_client = memcache.Client()

if LOCAL_TIME_ZONE:
	import pytz

	LOCAL_TIMEZONE = pytz.timezone(LOCAL_TIME_ZONE)
	UTC = pytz.utc

	def convert_to_local_time(dt):
		if dt.tzinfo:
			return LOCAL_TIMEZONE.normalize(dt)
		else:
			return LOCAL_TIMEZONE.normalize(UTC.localize(dt))

	def parse_time(time_string):
		try:
			dt = LOCAL_TIMEZONE.localize(datetime.strptime(time_string, '%Y-%m-%d %H:%M:%S')).astimezone(UTC).replace(tzinfo=None)
			return dt if dt.year >= 1900 else None # the datetime strftime() method requires year >= 1900
		except:
			return None
else:
	ZERO_TIME_DELTA = timedelta(0)

	class LocalTimezone(tzinfo):
		def utcoffset(self, dt):
			return LOCAL_TIME_DELTA

		def dst(self, dt):
			return ZERO_TIME_DELTA

	LOCAL_TIMEZONE = LocalTimezone()

	class UTC(tzinfo):
		def utcoffset(self, dt):
			return ZERO_TIME_DELTA

		def dst(self, dt):
			return ZERO_TIME_DELTA

	UTC = UTC()

	def convert_to_local_time(dt):
		if dt.tzinfo:
			return dt.astimezone(LOCAL_TIMEZONE)
		else:
			return dt.replace(tzinfo=UTC).astimezone(LOCAL_TIMEZONE)

	def parse_time(time_string):
		try:
			dt = datetime.strptime(time_string, '%Y-%m-%d %H:%M:%S').replace(tzinfo=LOCAL_TIMEZONE).astimezone(UTC).replace(tzinfo=None)
			return dt if dt.year >= 1900 else None # the datetime strftime() method requires year >= 1900
		except:
			return None

def get_local_now():
	return datetime.now(LOCAL_TIMEZONE)

def formatted_date(dt):
	return convert_to_local_time(dt).strftime(DATE_FORMAT)

def formatted_date_for_url(dt=None):
	if not dt:
		return get_local_now().strftime('%Y/%m/%d/')
	return convert_to_local_time(dt).strftime('%Y/%m/%d/')

def formatted_time(dt, display_second=True):
	return convert_to_local_time(dt).strftime(SECONDE_FORMAT if display_second else MINUTE_FORMAT)

def formatted_time_for_edit(dt):
	return convert_to_local_time(dt).strftime('%Y-%m-%d %H:%M:%S')

ONE_SECOND = timedelta(seconds=1)

def get_time(time, compare_time):
	if not time or not time.strip():
		return datetime.utcnow()
	else:
		time = parse_time(time)
		if time:
			if time == compare_time:
				return None
			elif time > compare_time:
				return time if (time - compare_time > ONE_SECOND) else None
			else:
				return time if (compare_time - time > ONE_SECOND) else None
		else:
			return None

ISO_TIME_FORMAT = '%Y-%m-%dT%H:%M:%SZ'
ISO8601_TIME_FORMAT = '%Y%m%dT%H:%M:%SZ'

def sitemap_time_format(dt):
	if dt.tzinfo:
		dt = dt.astimezone(UTC)
	return dt.strftime('%Y-%m-%dT%H:%M:%S+00:00')

def iso_time_format(dt):
	if dt.tzinfo:
		return convert_to_local_time(dt).strftime(ISO_TIME_FORMAT)
	else:
		return dt.strftime(ISO_TIME_FORMAT)

def iso_time_now():
	return datetime.utcnow().strftime(ISO_TIME_FORMAT)

def parse_iso8601_time(time_string):
	return datetime.strptime(time_string, ISO8601_TIME_FORMAT)

def datetime_to_timestamp(dt):
	return mktime(dt.timetuple()) + dt.microsecond * 0.000001

def timestamp_to_datetime(timestamp):
	return datetime.fromtimestamp(timestamp)

def time_from_now(time):
	if isinstance(time, int):
		time = timestamp_to_datetime(time)
	time_diff = datetime.utcnow() - time
	days = time_diff.days
	if days:
		if days > 730:
			return '%s years ago' % (days / 365)
		if days > 365:
			return '1 year ago'
		if days > 60:
			return '%s months ago' % (days / 30)
		if days > 30:
			return '1 month ago'
		if days > 14:
			return '%s weeks ago' % (days / 7)
		if days > 7:
			return '1 week ago'
		if days > 1:
			return '%s days ago' % days
		return '1 day ago'
	seconds = time_diff.seconds
	if seconds > 7200:
		return '%s hours ago' % (seconds / 3600)
	if seconds > 3600:
		return '1 hour ago'
	if seconds > 120:
		return '%s minutes ago' % (seconds / 60)
	if seconds > 60:
		return '1 minute ago'
	if seconds > 1:
		return '%s seconds ago' %seconds
	return '%s second ago' % seconds

def path_to_unicode(path, coding='utf-8'):
	return path.decode(coding, 'ignore')

def unquoted_unicode(string, coding='utf-8'):
	return unquote(string).decode(coding)

def unquoted_cursor(cursor):
	if cursor:
		return unquote(cursor)
	return None

def strip(s):
	return s.strip() if s else s

def strip_html(content, length):
	result = _re_html.sub(' ', content)
	return result[:length].strip()

URL_PATTERN = re.compile(r'(.+?://)(.+)')
def split_url(url):
	match = URL_PATTERN.match(url)
	if match:
		return match.groups()
	return 'http://', url

REPLY_PATTERN = re.compile(r'<a href="#comment-id-(\d+)">')
def send_reply_notification(content, html_body, title, article_id):
	import model
	comment_ids = set(int(id) for id in REPLY_PATTERN.findall(content))
	if comment_ids:
		comments = db.get([db.Key.from_path('Article', article_id, 'Comment', comment_id) for comment_id in comment_ids])
		reply_to_list = list(set([comment.email for comment in comments if comment and comment.email != ADMIN_EMAIL]))[:MAX_SEND_TO]
		if reply_to_list:
			reply_to_users = model.User.get_by_key_name(reply_to_list)
			reply_to_list = [user.key().name() for user in reply_to_users if not(user.flag & model.USER_FLAGS['mute'])]
			if reply_to_list:
				try:
					mail.EmailMessage(sender=APP_SENDER, bcc=reply_to_list, subject=title, html=html_body).send()
				except:
					pass

SUBSCRIBER_PATTERN = re.compile(r'(\d+) subscriber', re.I)
def get_subscribers_from_ua(user_agent):
	match = SUBSCRIBER_PATTERN.search(user_agent)
	if match:
		return int(match.group(1))
	return 0

def ping_hubs(feed):
	data = urlencode({'hub.url': feed, 'hub.mode': 'publish'})
	rpcs = []
	for hub in HUBS:
		rpc = urlfetch.create_rpc(10)
		urlfetch.make_fetch_call(rpc, hub, data, urlfetch.POST)
		rpcs.append(rpc)
	for rpc in rpcs:
		try:
			rpc.wait()
		except:
			pass

def ping_xml_rpc(article_url):
	xml = engine.render('XML-RPC.xml', {'article_url': article_url})
	rpcs = []
	for endpoint in XML_RPC_ENDPOINTS:
		rpc = urlfetch.create_rpc(10)
		urlfetch.make_fetch_call(rpc, endpoint, xml, urlfetch.POST)
		rpcs.append(rpc)
	for rpc in rpcs:
		try:
			rpc.wait()
		except:
			pass

def send_subscription_request(hub, mode, verify_token, feed):
	data = urlencode({
		'hub.callback': BLOG_HOME_FULL_URL + 'hub/callback',
		'hub.mode': mode,
		'hub.topic': feed,
		'hub.verify': 'async',
		'hub.verify_token': verify_token
    })
	try:
		response = urlfetch.fetch(hub, data, urlfetch.POST, deadline=10)
		return response.status_code
	except:
		return 404

def clear_article_memcache(id=None, url=None):
	keys = ['get_articles_for_feed', 'get_articles_for_homepage']
	if id:
		keys.append('get_article_by_id:%s' % id)
		tenjin.helpers.fragment_cache.store.delete('article:%s' % id)
	if url:
		keys.append('get_article_by_url:%s' % hash(url))
	memcache_client.delete_multi_async(keys)
	yui.flush_all_server_cache()

def clear_user_memcache(email):
	memcache.delete('get_user_by_email:' + email)

def clear_tags_memcache():
	memcache.delete('get_all_tags')
	tenjin.helpers.fragment_cache.store.delete('siderbar')
	yui.flush_all_server_cache()

def clear_categories_memcache():
	memcache.delete('get_all_categories')
	tenjin.helpers.fragment_cache.store.delete('siderbar')
	yui.flush_all_server_cache()

def clear_latest_comments_memcache(id=None):
	keys = ['latest_comments:%s' % LATEST_COMMENTS_FOR_SIDEBAR, 'latest_comments:%s' % LATEST_COMMENTS_FOR_FEED]
	if id:
		keys.extend(['get_comments_with_user_by_article_key:%s_True_None' % id, 'get_comments_with_user_by_article_key:%s_False_None' % id])
	memcache_client.delete_multi_async(keys)
	tenjin.helpers.fragment_cache.store.delete('siderbar')
	yui.flush_all_server_cache()

def query_with_cursor(query, cursor):
	try:
		if cursor:
			query.with_cursor(cursor)
	except:
		pass
	return query

if REPLACE_SPECIAL_CHARACTERS_FOR_URL:
	def replace_special_characters_for_url(string):
		return URL_SPECIAL_CHARACTERS.sub(URL_REPLACE_CHARACTER, string)

def qt(s):
	return quote(s, '~')

def qs2dict(s):
	dic = {}
	for param in s.split('&'):
		(key, value) = param.split('=')
		dic[key] = value
	return dic

def dict2qs(dic):
	return ', '.join(['%s="%s"' % (key, value) for key, value in dic.iteritems()])

TWITTER_CALLBACK_URL = MAJOR_HOST_URL + BLOG_ADMIN_RELATIVE_PATH + 'twitter/callback'

def get_oauth_params(params, base_url, token_secret='', callback_url=TWITTER_CALLBACK_URL, method='POST'):
	default_params = {
		'oauth_consumer_key': TWITTER_CONSUMER_KEY,
		'oauth_signature_method': 'HMAC-SHA1',
		'oauth_timestamp': str(int(time())),
		'oauth_nonce': hex(getrandbits(64))[2:],
		'oauth_version': '1.0'
	}
	params.update(default_params)

	if callback_url:
		params['oauth_callback'] = qt(callback_url)

	keys = sorted(list(params.keys()))
	encoded = qt('&'.join(['%s=%s' % (key, params[key]) for key in keys]))

	base_string = '%s&%s&%s' % (method, qt(base_url), encoded)
	key = TWITTER_CONSUMER_SECRET + '&' + token_secret

	params['oauth_signature'] = qt(hmac.new(key, base_string, sha1).digest().encode('base64')[:-1])

	return params

def post_tweet(msg):
	import model

	twitter = model.Twitter.get_twitter()
	if twitter:
		msg = msg.encode('UTF-8')
		POST_URL = 'https://api.twitter.com/1/statuses/update.json'

		params = get_oauth_params({
			'oauth_token': twitter.token,
			'status': qt(msg)
		}, POST_URL, twitter.secret, '')

		del params['status']

		try:
			res = urlfetch.fetch(url=POST_URL, payload=urlencode({'status': msg}), headers={'Authorization': 'OAuth ' + dict2qs(params)}, method='POST')
			if res.status_code == 200:
				return True
			logging.error('Access Twitter error.\nstatus_code: %s\nheaders: %s\nparams: %s' % (res.status_code, res.headers, params))
		except:
			pass
	return False

def post_article_to_twitter(title, url):
	left = 139 - min(len(url), 20) # t.co will shorten it to less than 20
	if left > 0:
		if len(title) > left:
			title = title[:left]
		post_tweet('%s %s' % (title, url))

def get_recent_tweets(count=RECENT_TWEETS):
	if TWITTER_CONSUMER_KEY and TWITTER_CONSUMER_SECRET:
		import model
		twitter = model.Twitter.get_twitter()
		if twitter:
			try:
				res = urlfetch.fetch(url='https://api.twitter.com/1/statuses/user_timeline.json?screen_name=%s&count=%s&include_rts=1' % (twitter.name, RECENT_TWEETS))
				if res.status_code == 200:
					contents = json.loads(res.content)
					if contents:
						from email.utils import parsedate
						from calendar import timegm
						tweets = [{
							'text': content['text'],
						    'timestamp': timegm(parsedate(content['created_at']))
						} for content in contents]
						result = (twitter.name, tweets)
						memcache.set('recent_tweets', result)
						return result
			except:
				pass

def check_latest_version():
	latest_version = DOODLE_VERSION
	try:
		res = urlfetch.fetch('http://bitbucket.org/keakon/doodle/downloads')
		if res.status_code == 200:
			match = re.search(r'Doodle_(\d+(\.\d)+)_en\.zip', res.content)
			if match:
				latest_version = match.group(1)
	except:
		pass
	memcache.set('latest_version', latest_version, 86400)

def memcached(key, cache_time=0, key_suffix_calc_func=None):
	'''
	Memcache the function result

	@type key: str
	@param key: the memcache key

	@type cache_time: int
	@param cache_time: cache expiration time in seconds

	@type key_suffix_calc_func: function
	@param key_suffix_calc_func: calculate the suffix of the key, if the function or its result is None, no suffix will append to the key

	@warning: make sure the parameter must be the same with the cached function, including name, order and default value.
	'''
	def wrap(func):
		def cached_func(*args, **kw):
			key_with_suffix = key

			if key_suffix_calc_func:
				key_suffix = key_suffix_calc_func(*args, **kw)
				if key_suffix is not None:
					key_with_suffix = '%s:%s' % (key, key_suffix)

			value = memcache.get(key_with_suffix)
			if value is None:
				value = func(*args, **kw)
				memcache_client.set_multi_async({key_with_suffix: value}, cache_time)
			return value
		return cached_func
	return wrap

def get_fetch_result_with_valid_cursor(query, fetch_limit, config=None):
	entities = query.fetch(fetch_limit, config=config)
	cursor = query.cursor()
	if len(entities) < fetch_limit or query.with_cursor(cursor).count(1) == 0:
		return entities, None
	else:
		return entities, cursor

def incr_counter(key, url, delta=1):
	'''
	Count by memcache

	@type key: str
	@param key: the memcache key

	@type url: str
	@param url: the URL of the count taskqueue

	@type delta: int
	@param delta: the increment value
	'''
	memcache.incr(key, delta, initial_value=0)
	lock_key = 'lock:' + key
	if not memcache.get(lock_key):
		memcache.set(lock_key, 1, COUNTER_TASK_DELAY - 1)
		try:
			taskqueue.add(queue_name='counter', url=url, params={'key': key}, countdown=COUNTER_TASK_DELAY)
		except:
			pass

def log_request(app):
	def wrap(environ, start_response):
		memcache_client.incr_async('dynamic_requests', initial_value=0)
		return app(environ, start_response)
	return wrap

def update_requests_counter():
	dynamic_requests = memcache.get('dynamic_requests') or 0
	update_counter = memcache.incr('update_counter', initial_value=0)
	logging.info('#%d: %d dynamic requests today.' % (update_counter, dynamic_requests))

def convert_bbcode_to_html(bbcode_content, escape=True, exclude_tags=()):
	'''
	Convert BBCode to HTML

	@type bbcode_content: str or unicode
	@param bbcode_content: the BBCode content

	@type escape: bool
	@param escape: whether escape '<', '>' and '"' to HTML entity

	@type exclude_tags: str or unicode
	@param exclude_tags: the BBCode tags which shouldn't be parsed
	'''
	return render_bbcode(bbcode_content, auto_urls=False, clean=False, exclude_tags=exclude_tags, escape=escape)

def parse_plain_text(content):
	return escape(content).replace('\n', '<br/>').replace('  ', '&#160;&#160;').replace('\t', '&#160;&#160;&#160;&#160;')


engine = tenjin.Engine(path=[os.path.join('template', theme) for theme in THEMES] + ['template'], cache=tenjin.MemoryCacheStorage(), preprocess=True)

class BaseHandler(yui.HtmlRequestHandler):

	if ONLINE_VISITORS_EXPIRY_TIME > 0:
		def before(self, *args, **kw):
			super(BaseHandler, self).before(*args, **kw)
			now = int(time())
			online_visitors = memcache.get('online_visitors') or {}
			request = self.request
			current_user = request.user
			online_visitors[current_user.email() if current_user else request.client_ip] = now + ONLINE_VISITORS_EXPIRY_TIME
			memcache_client.set_multi_async({'online_visitors': online_visitors})
			request.online_visitors = online_visitors

	def render(self, template, context=None, globals=None, layout=False):
		if context is None:
			context = {'request': self.request}
		else:
			context['request'] = self.request
		return engine.render(template, context, globals, layout)

	def echo(self, template, context=None, globals=None, layout=False):
		self.write(self.render(template, context, globals, layout))

	def check_mobile(self):
		view_mode = self.GET['viewmode']
		if view_mode:
			use_mobile_theme = view_mode == 'mobile'
			self.header.add_cookie('viewmode', str(int(use_mobile_theme)))
		else:
			view_mode = self.request.cookies.get('viewmode', '')
			if view_mode:
				use_mobile_theme = view_mode == '1'
			else:
				use_mobile_theme = self.request.is_mobile
		if use_mobile_theme:
			self.set_content_type('wap2')
		return use_mobile_theme

	def is_spider(self):
		user_agent = self.request.user_agent.lower()
		if 'bot' in user_agent or 'spider' in user_agent:
			return True
		return False


class UserHandler(BaseHandler):

	def before(self, *args, **kw):
		import model
		super(UserHandler, self).before(*args, **kw)
		self.request.current_user = model.User.get_current_user()

	def handle_exception(self, exception):
		logging.exception('Get an uncaught exception when processing request.')
		self.error(500)
		self.display_exception(exception)

	def display_exception(self, exception):
		self.echo('error.html', {
			'page': '500',
			'title': 'An unhandled error occurred',
			'h2': 'The server is temporary error now.',
			'msg': format_exc() if self.request.is_admin else "I don't know what has happened. You can try to refresh this page, if still has error, you can report to the administrator."
		})
