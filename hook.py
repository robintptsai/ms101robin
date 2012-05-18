# -*- coding: utf-8 -*-

import logging
from time import time

from google.appengine.api import apiproxy_stub_map
import setting


if setting.THREAD_SAFE:
	import threading
	local = threading.local()
else:
	class _Local:
		pass
	local = _Local()

def init():
	local.request_arrive_time = time()
	local.db_count = 0
	local.db_time = 0
	local.db_start_time = 0

def hook_app(app):
	def wrap(environ, start_response):
		init()
		return app(environ, start_response)
	return wrap

def before_db(service, call, request, response):
	if hasattr(local, 'db_count'):
		local.db_count += 1
	else:
		local.db_count = 1
	local.db_start_time = time()

def after_db(service, call, request, response):
	if hasattr(local, 'db_start_time') and hasattr(local, 'db_time'):
		dt = time() - local.db_start_time
		local.db_time += dt
		if dt > 1:
			logging.warning('This request took %s seconds.' % dt)
			logging.info(request)

apiproxy_stub_map.apiproxy.GetPreCallHooks().Append('before_db', before_db, 'datastore_v3')
apiproxy_stub_map.apiproxy.GetPostCallHooks().Push('after_db', after_db, 'datastore_v3')
