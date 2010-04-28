from landscape.lib.sysstats import get_logged_in_users


class LoggedInUsers(object):

    def register(self, sysinfo):
        self._sysinfo = sysinfo

    def run(self):
        self._sysinfo.add_header("Users logged in", None)

        def add_header(logged_users):
            self._sysinfo.add_header("Users logged in", str(len(logged_users)))
        result = get_logged_in_users()
        result.addCallback(add_header)
        result.addErrback(lambda failure: None)
        return result
