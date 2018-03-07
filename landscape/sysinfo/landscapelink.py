from twisted.internet.defer import succeed


class LandscapeLink(object):

    def register(self, sysinfo):
        self._sysinfo = sysinfo

    def run(self):
        self._sysinfo.add_footnote(
            "Graph this data and manage this system at:\n"
            "    https://landscape.canonical.com/")
        return succeed(None)
