import os

from twisted.internet.defer import succeed


class Load:
    def register(self, sysinfo):
        self._sysinfo = sysinfo

    def run(self):
        self._sysinfo.add_header(
            "System load",
            str(round(os.getloadavg()[0], 2)),
        )
        return succeed(None)
