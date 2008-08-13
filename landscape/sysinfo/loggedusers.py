import os

from twisted.internet.defer import succeed

from landscape.lib.sysstats import get_logged_users


class LoggedUsers(object):

    def register(self, sysinfo):
        self._sysinfo = sysinfo

    def run(self):
        self._sysinfo.add_header("Logged users", str(len(get_logged_users())))
        return succeed(None)
