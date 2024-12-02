from twisted.internet.defer import succeed


class LandscapeLink:
    def register(self, sysinfo):
        self._sysinfo = sysinfo

    def run(self):
        self._sysinfo.add_footnote(
            "Graph this data and manage this system with Landscape. \n"
            "https://ubuntu.com/landscape",
        )
        return succeed(None)
