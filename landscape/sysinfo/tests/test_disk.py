from twisted.internet.defer import Deferred

from landscape.sysinfo.sysinfo import SysInfoPluginRegistry
from landscape.sysinfo.disk import Disk, format_megabytes
from landscape.tests.helpers import LandscapeTest

def mb(n): return n * 1024 * 1024

class DiskTest(LandscapeTest):

    def setUp(self):
        super(DiskTest, self).setUp()
        self.mount_file = self.make_path("")
        self.stat_results = {}

        self.disk = Disk(mounts_file=self.mount_file,
                         statvfs=self.stat_results.get)
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

    def test_over_85_percent(self):
        """
        When a filesystem is using more than 85% capacity, a note will be
        displayed.
        """
        self.stat_results["/"] = (4096, 0, mb(1000), mb(150), 0, 0, 0, 0, 0)
        f = open(self.mount_file, "w")
        f.write("/dev/sda1 / rootfs rw 0 0\n")
        f.close()

        self.disk.run()
        self.assertEquals(self.sysinfo.get_notes(),
                          ["/ is using 85.0% of 3.91GB"])

    def test_under_85_percent(self):
        """No note is displayed for a filesystem using less than 85% capacity.
        """
        self.stat_results["/"] = (4096, 0, mb(1000), mb(151), 0, 0, 0, 0, 0)
        f = open(self.mount_file, "w")
        f.write("/dev/sda1 / rootfs rw 0 0\n")
        f.close()

        self.disk.run()
        self.assertEquals(self.sysinfo.get_notes(), [])

    def test_multiple_notes(self):
        """
        A note will be displayed for each filesystem using 85% or more capacity.
        """
        self.stat_results["/"] = (4096, 0, mb(1000), mb(150), 0, 0, 0, 0, 0)
        self.stat_results["/use"] = (8192, 0, mb(2000), mb(200), 0, 0, 0, 0, 0)
        self.stat_results["/emp"] = (12288, 0, mb(3000), mb(500), 0, 0, 0, 0, 0)

        f = open(self.mount_file, "w")
        f.write("""\
/dev/sda1 / rootfs rw 0 0
/dev/sda2 /use rootfs rw 0 0
/dev/sda3 /emp rootfs rw 0 0
""")
        f.close()

        self.disk.run()
        self.assertEquals(self.sysinfo.get_notes(),
                          ["/ is using 85.0% of 3.91GB",
                           "/use is using 90.0% of 15.62GB"])

    def test_format_megabytes(self):
        self.assertEquals(format_megabytes(100), "100MB")
        self.assertEquals(format_megabytes(1023), "1023MB")
        self.assertEquals(format_megabytes(1024), "1.00GB")
        self.assertEquals(format_megabytes(1024*1024-1), "1024.00GB")
        self.assertEquals(format_megabytes(1024*1024), "1.00TB")