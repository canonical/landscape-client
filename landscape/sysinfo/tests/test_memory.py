import unittest

from landscape.lib.testing import TwistedTestCase, FSTestCase
from landscape.sysinfo.sysinfo import SysInfoPluginRegistry
from landscape.sysinfo.memory import Memory


MEMINFO_SAMPLE = """
MemTotal:      2074536 kB
MemFree:        436468 kB
Buffers:        385596 kB
Cached:         672856 kB
SwapCached:          0 kB
Active:         708424 kB
Inactive:       705292 kB
HighTotal:     1178432 kB
HighFree:       137220 kB
LowTotal:       896104 kB
LowFree:        299248 kB
SwapTotal:     2562356 kB
SwapFree:      1562356 kB
Dirty:             300 kB
Writeback:           0 kB
AnonPages:      355388 kB
Mapped:         105028 kB
Slab:           152664 kB
SReclaimable:   136372 kB
SUnreclaim:      16292 kB
PageTables:       3124 kB
NFS_Unstable:        0 kB
Bounce:              0 kB
CommitLimit:   3599624 kB
Committed_AS:  1136296 kB
VmallocTotal:   114680 kB
VmallocUsed:     27796 kB
VmallocChunk:    86764 kB
"""


class MemoryTest(FSTestCase, TwistedTestCase, unittest.TestCase):

    def setUp(self):
        super(MemoryTest, self).setUp()
        self.memory = Memory(self.makeFile(MEMINFO_SAMPLE))
        self.sysinfo = SysInfoPluginRegistry()
        self.sysinfo.add(self.memory)

    def test_run_returns_succeeded_deferred(self):
        self.assertIs(None, self.successResultOf(self.memory.run()))

    def test_run_adds_header(self):
        self.memory.run()
        self.assertEqual(self.sysinfo.get_headers(),
                         [("Memory usage", "27%"),
                          ("Swap usage", "39%")])
