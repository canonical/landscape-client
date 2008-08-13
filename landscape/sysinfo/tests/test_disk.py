from twisted.internet.defer import Deferred

from landscape.sysinfo.sysinfo import SysInfoPluginRegistry
from landscape.sysinfo.disk import Disk
from landscape.tests.helpers import LandscapeTest


class DiskTest(LandscapeTest):

    def setUp(self):
        super(DiskTest, self).setUp()
        self.disk = Disk()
        self.sysinfo = SysInfoPluginRegistry()
        self.sysinfo.add(self.disk)

    def test_run_returns_succeeded_deferred(self):
        result = self.disk.run()
        self.assertTrue(isinstance(result, Deferred))
        called = []
        def callback(result):
            called.append(True)
        result.addCallback(callback)
        self.assertTrue(called)

    def test_everything_is_cool(self):
        self.disk.run()
        self.assertEquals(self.sysinfo.get_notes(), [])

    