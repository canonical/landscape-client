from twisted.internet.defer import succeed

from landscape.lib.sysstats import MemoryStats


class Memory(object):

    def __init__(self, filename="/proc/meminfo"):
        self._filename = filename

    def register(self, sysinfo):
        self._sysinfo = sysinfo

    def run(self):
        memstats = MemoryStats(self._filename)
        self._sysinfo.add_header("Memory usage", "%d%%" %
                                 memstats.used_memory_percentage)
        self._sysinfo.add_header("Swap usage", "%d%%" %
                                 memstats.used_swap_percentage)
        return succeed(None)
