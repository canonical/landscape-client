from twisted.internet.defer import succeed

from landscape.lib.sysstats import get_logged_users, CommandError


class LoggedUsers(object):

    def register(self, sysinfo):
        self._sysinfo = sysinfo

    def run(self):
        try:
            logged_users = get_logged_users()
        except CommandError:
            pass
        else:
            self._sysinfo.add_header("Logged users", str(len(logged_users)))
        return succeed(None)
