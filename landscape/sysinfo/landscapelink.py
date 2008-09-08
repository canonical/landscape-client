from twisted.internet.defer import succeed


class LandscapeLink(object):

    def register(self, sysinfo):
        self._sysinfo = sysinfo

    def run(self):
        self._sysinfo.add_footnote("Graph these measurements at "
                                   "https://landscape.canonical.com")
        return succeed(None)
