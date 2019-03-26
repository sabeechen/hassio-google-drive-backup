import os, sys

from .helpers import formatException


class Watcher(object):

	def __init__(self, config):
		self.last_list = None
		self.config = config

	def haveFilesChanged(self):
		try:
			if self.last_list is None:
				self.last_list = os.listdir(self.config.backupDirectory())
				self.last_list.sort()
				return False
			dirs = os.listdir(self.config.backupDirectory())
			if self.config.verbose():
				print("Backup directory: {}".format(dirs))
			dirs.sort()
			if dirs == self.last_list:
				return False
			else:
				print("Backup directory has changed")
				self.last_list = dirs
				return True
		except Exception as e:
			print(formatException(e))
			return False

