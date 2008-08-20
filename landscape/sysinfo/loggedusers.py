from twisted.internet.defer import succeed

from landscape.lib.sysstats import get_logged_users, CommandError


class LoggedUsers(object):

    def register(self, sysinfo):
        self._sysinfo = sysinfo

    def run(self):
        self._sysinfo.add_header("Logged users", None)
        def add_header(logged_users):
            self._sysinfo.add_header("Logged users", str(len(logged_users)))
        result = get_logged_users()
        result.addCallback(add_header)
        result.addErrback(lambda failure: None)
        return result
