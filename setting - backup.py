# -*- coding: utf-8 -*-

from datetime import timedelta
from os import environ
import re
from urllib import quote


DOODLE_VERSION = '1.4' # current Doodle version
CHECK_NEW_VERSION = True # whether check the latest version

THREAD_SAFE = environ.get('APPENGINE_RUNTIME') == 'python27' # whether enable thread safe mode, no need to change
APPID = environ['APPLICATION_ID'] # application ID, no need to change
IS_PRODUCTION_SERVER = not APPID.startswith('dev~') # whether in production server, no need to change
CURRENT_VERSION_ID = environ['CURRENT_VERSION_ID'] # deployed version id, no need to change
BLOG_TITLE = u'' # blog title
BLOG_SUB_TITLE = u''# blog sub title
BLOG_DESCRIPTION = BLOG_SUB_TITLE # blog description for feed
BLOG_AUTHOR = '' # blog author
MAJOR_DOMAIN = environ['HTTP_HOST'] # major domain, if you don't want to generate *.appspot.com domain, you can set it to your Google Apps domain
# eg:
# MAJOR_DOMAIN = environ['HTTP_HOST']
# MAJOR_DOMAIN = 'abcdegf.appspot.com'
# MAJOR_DOMAIN = 'www.abcdegf.com'
ONLY_USE_MAJOR_DOMAIN = False # whether only use major domain, if True, all requests of other domains will be redirect to the major domain
FEED_DOMAIN = '' # the domain of the feed, you can set it to a sub domain if you don't want to use a directory
MAJOR_HOST_URL = 'http://' + MAJOR_DOMAIN
if FEED_DOMAIN:
	BLOG_FEED_URL = 'http://%s/' % FEED_DOMAIN # the blog article feed URL
	BLOG_COMMENT_FEED_URL = 'http://%s/comment' % FEED_DOMAIN # the blog comment feed URL
else:
	BLOG_FEED_URL = MAJOR_HOST_URL + '/feed'
	BLOG_COMMENT_FEED_URL = MAJOR_HOST_URL + '/comment-feed'
QUOTED_BLOG_FEED_URL = quote(BLOG_FEED_URL, '')
BLOG_HOME_RELATIVE_PATH = '/' # the relative path of the blog home page, you can change it to '/blog/' or others
BLOG_HOME_FULL_URL = MAJOR_HOST_URL + BLOG_HOME_RELATIVE_PATH # # the full url of the blog home page
BLOG_WAP_RELATIVE_PATH = BLOG_HOME_RELATIVE_PATH + 'wap/' # the relative path of the blog wap page
BLOG_ADMIN_RELATIVE_PATH = BLOG_HOME_RELATIVE_PATH + 'admin/' # the relative path of the blog admin page
# if you modified above pathes, you should also change yaml files and previewParserPath of \static\markitup\sets\bbcode\set.js

SOCIAL_MEDIAS = [
	{'icon': 'atom', 'url': '/comment-feed', 'title': 'subscribe comments', 'text': 'Comments Feed', 'rel': 'nofollow'}
] # social media links

NAV_LINKS = [
	{'url': '/', 'text': 'Home', 'level': 1},
	{'url': BLOG_WAP_RELATIVE_PATH, 'text': 'Wap', 'level': 1},
] # navigation bar links

LINKS = [
	{'url': 'http://code.google.com/appengine/', 'text': 'Google App Engine', 'rel': 'nofollow'},
] # links for sidebar

GOOGLE_ANALYTICS_ID = '' # Google Analytics web property ID, leave it as empty if you don't use it
GOOGLE_CSE_ID = '' # Google Custom Search ID, left it as empty if you don't use it. You can get it from http://www.google.com/cse/manage/create

DISPLAY_PERFORMANCE_TO_EVERYONE = False # whether display the performance information for everyone. If False, only administrator can see it. Notice: enable it may make the user agent cannot reuse the cache since the ETag might be changed.

ADMIN_EMAIL = '' # admin email address for sending and receiving email
EMAIL_WRITERS = [ADMIN_EMAIL] # the mail list contains who are allowed to post articles by email
APP_SENDER = u'%s <no-reply@%s.appspotmail.com>' % (BLOG_TITLE, APPID) # for sending email to others
MAX_SEND_TO = 5 # Max allowed recipients per comment notification email. You can set it to 0 to disable notification. Note: If you doesn't enable billing, there is a quota that limited to 8 recipients/minute.
SEND_LEVEL = 1 | 2 # what knid of users can send notification email, see USER_FLAGS in model.py for available values
NOTIFY_WHEN_REPLY = True # whether send notification to admin when receive new comment
SEND_INTERVAL = 600 # the shortest sending interval in seconds (similarly hereafter). 0 means don't check the interval. During the interval, the admin will receive notification only once.
ADMIN_PASSWORD = '' # admin password for login Google Calendar to send SMS notification, using AuthSub to login if it's empty. Warning: it's not recommend to set password because you may take a risk of password leaking, so do keep your setting.py file safe and private.
NOTIFY_FEED_URL = 'http://www.google.com/calendar/feeds/default/private/full' # the feed path for Google Calendar, only available when using password to login.

LANGUAGE = 'en' # the main language your blog articles use

THEMES = ['null', 'iphonsta', 'freshpress'] # themes
JQUERY_VERSION = '1.7.1' # jQuery version
ZEPTO_VERSION = '0.8' # Zepto.js version

LOCAL_TIME_ZONE = '' # the time zone name defined in pytz, using LOCAL_TIME_DELTA if it's empty. Note: pytz can handle the daylight saving time, but slower. If you don't need this function, you can delete pytz folder to save the uploading time.
LOCAL_TIME_DELTA = timedelta(hours=8) # time difference between local time zone and UTC
DATE_FORMAT = '%Y-%m-%d' # date format
SECONDE_FORMAT = '%Y-%m-%d %H:%M:%S' # time format to second
MINUTE_FORMAT = '%Y-%m-%d %H:%M' # time format to minute

ARTICLES_PER_PAGE = 10 # articles per page
COMMENTS_PER_PAGE = 10 # comments per page
RELATIVE_ARTICLES = 5 # relative articles
ARTICLES_FOR_FEED = 10 # articles in feed
LATEST_COMMENTS_FOR_SIDEBAR = 5 # latest comments displayed at sidebar
LATEST_COMMENTS_LENGTH = 20 # the max words of each latest comments at sidebar
LATEST_COMMENTS_FOR_FEED = 10 # latest comments in comment feed
RECENT_TWEETS = 5 # recent tweets displayed at sidebar

ARTICLES_CACHE_TIME = 3600 # articles cache time, 0 means forever (not recommend).
ARTICLE_CACHE_TIME = 600 # single article cache time
FEED_CACHE_TIME = 3600 # feed cache time
SITEMAP_CACHE_TIME = 86400 # sitemap cache time
COMMENTS_CACHE_TIME = 600 # comments cache time
CATEGORY_CACHE_TIME = 86400 # category cache time
TAGS_CACHE_TIME = 86400 # tags cache time
SIDEBAR_BAR_CACHE_TIME = 600 # sidebar bar cache time
USER_CACHE_TIME = 0 # user data cache time
SUBSCRIBER_CACHE_TIME = 21600 # single feed subscribers cache time
SUBSCRIBERS_CACHE_TIME = 86400 # total feed subscribers cache time

COUNTER_TASK_DELAY = 200 # counter task delay time

CATEGORY_PATH_DELIMETER = ',' # category path delimeter, make sure your category name won't include this character. Don't change it latter.

SUMMARY_DELIMETER = re.compile(r'\r?\n\r?\n\[cut1\]\r?\n') # separate summary and content, the part before the delimeter is summary, the part without the delimeter is content
SUMMARY_DELIMETER2 = re.compile(r'\r?\n\r?\n\[cut2\]\r?\n') # separate summary and content, the part before the delimeter is summary, the part after the delimeter is content
# If an article has 2 kinds of delimeters, use the first kind. If an article has several delimeters, use the first one.

OUTPUT_FULLTEXT_FOR_FEED = True # whether output fulltext or summary for feed
if IS_PRODUCTION_SERVER:
	HUBS = ['http://pubsubhubbub.appspot.com/'] # the PubSubHubbub server list, leave it as blank if you don't use it. See http://code.google.com/p/pubsubhubbub/wiki/Hubs for more details.
	XML_RPC_ENDPOINTS = ['http://blogsearch.google.com/ping/RPC2', 'http://rpc.pingomatic.com/', 'http://ping.baidu.com/ping/RPC2'] # XML-RPC end points, leave it as blank if you don't use it.
else:
	HUBS = []
	XML_RPC_ENDPOINTS = []

ENABLE_TAG_CLOUD = True # whether enable tag cloud
REPLACE_SPECIAL_CHARACTERS_FOR_URL = False # whether replace ' ', '"', '<', '>', '&', '#', '%' to "-" when generating article URL
if REPLACE_SPECIAL_CHARACTERS_FOR_URL:
	URL_SPECIAL_CHARACTERS = re.compile(r'[\s\"\'&#<>%]+')
	URL_REPLACE_CHARACTER = '-'

ONLINE_VISITORS_EXPIRY_TIME = 600 # expiry time of online visitors, not counting it if it's not bigger than 0 (the responses will be a little faster)

# below settings is used for Twitter integration, see "Manage blog" - "Twitter" page for setting up details.
TWITTER_CONSUMER_KEY = '' # Twitter consumer key
TWITTER_CONSUMER_SECRET = '' # Twitter consumer secret
