from landscape.lib.sysstats import MemoryStats
from landscape.tests.helpers import LandscapeTest, MakePathHelper
from landscape.tests.mocker import ANY


SAMPLE_MEMORY_INFO = """
MemTotal:      1546436 kB
MemFree:         23452 kB
Buffers:         41656 kB
Cached:         807628 kB
SwapCached:      17572 kB
Active:        1030792 kB
Inactive:       426892 kB
HighTotal:           0 kB
HighFree:            0 kB
LowTotal:      1546436 kB
LowFree:         23452 kB
SwapTotal:     1622524 kB
SwapFree:      1604936 kB
Dirty:            1956 kB
Writeback:           0 kB
Mapped:         661772 kB
Slab:            54980 kB
CommitLimit:   2395740 kB
Committed_AS:  1566888 kB
PageTables:       2728 kB
VmallocTotal:   516088 kB
VmallocUsed:      5660 kB
VmallocChunk:   510252 kB
"""


class MemoryStatsTest(LandscapeTest):

    helpers = [MakePathHelper]

    def test_get_memory_info(self):
        filename = self.make_path(SAMPLE_MEMORY_INFO)
        memstats = MemoryStats(filename)
        self.assertEquals(memstats.total_memory, 1510)
        self.assertEquals(memstats.free_memory, 503)
        self.assertEquals(memstats.used_memory, 1007)
        self.assertEquals(memstats.total_swap, 1584)
        self.assertEquals(memstats.free_swap, 1567)
        self.assertEquals(memstats.used_swap, 17)
        self.assertEquals("%.2f" % memstats.free_memory_percentage, "33.31")
        self.assertEquals("%.2f" % memstats.free_swap_percentage, "98.93")
        self.assertEquals("%.2f" % memstats.used_memory_percentage, "66.69")
        self.assertEquals("%.2f" % memstats.used_swap_percentage, "1.07")

