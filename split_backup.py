# -*- coding: utf-8 -*-

import gzip
import sys
try:
	import simplejson as json
except ImportError:
	import json

def split(filename, batch_size=1000):
	if batch_size <= 0:
		batch_size = 1000

	try:
		gzip_file = gzip.GzipFile(filename, 'rb')
		json_content = gzip_file.read()
		gzip_file.close()
	except:
		print 'Error: invalid file format.'
		exit(2)

	try:
		entites = json.loads(json_content)
		del json_content
	except:
		print 'Error: invalid file content.'
		exit(3)

	try:
		i = 1
		size = 0
		left = batch_size
		new_entites = {}

		for key, entity_list in entites.items():
			while entity_list:
				if type(entity_list) == dict:
					new_entites[key] = entity_list
					print new_entites
					break
				new_list = entity_list[:left]
				entity_list = entity_list[left:]
				length = len(new_list)
				size += length
				left -= length
				if key in new_entites:
					new_entites[key] += new_list
				else:
					new_entites[key] = new_list
				if left == 0:
					gzip_file = gzip.GzipFile('%s.%d' % (filename, i), 'wb')
					gzip_file.write(json.dumps(new_entites))
					gzip_file.close()

					new_entites = {}
					i += 1
					size = 0
					left = batch_size

		if new_entites:
			gzip_file = gzip.GzipFile('%s.%d' % (filename, i), 'wb')
			gzip_file.write(json.dumps(new_entites))
			gzip_file.close()
	except:
		print 'Error: invalid file content.'
		exit(4)

	print 'File split sucuessfully.'


if __name__ == '__main__':
	if len(sys.argv) < 2:
		print 'Usage: python split_backup.py filename [batch_size]'
		print 'eg(1): python split_backup.py backup.gz'
		print 'eg(2): python split_backup.py backup.gz 500'
		exit(1)
	else:
		try:
			batch_size = int(sys.argv[2])
		except:
			batch_size = 1000
		split(sys.argv[1], batch_size)
