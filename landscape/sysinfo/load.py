import os

from twisted.internet.defer import succeed


class Load(object):

    def register(self, sysinfo):
        self._sysinfo = sysinfo

    def run(self):
        self._sysinfo.add_header("System load", str(os.getloadavg()[0]))
        return succeed(None)
