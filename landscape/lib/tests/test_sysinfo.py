from landscape.lib.sysinfo import get_memory_info
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


class MemoryInfoTest(LandscapeTest):

    helpers = [MakePathHelper]

    def test_get_memory_info(self):
        filename = self.make_path(SAMPLE_MEMORY_INFO)
        free_mem, free_swap = get_memory_info(filename)
        self.assertEquals(free_mem, 503)
        self.assertEquals(free_swap, 1567)
