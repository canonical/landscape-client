from twisted.internet.defer import Deferred

from landscape.sysinfo.sysinfo import SysInfoPluginRegistry
from landscape.sysinfo.disk import Disk, format_megabytes
from landscape.tests.helpers import LandscapeTest

class DiskTest(LandscapeTest):

    def setUp(self):
        super(DiskTest, self).setUp()
        self.mount_file = self.make_path("")
        self.stat_results = {}

        self.disk = Disk(mounts_file=self.mount_file,
                         statvfs=self.stat_results.get)
        self.sysinfo = SysInfoPluginRegistry()
        self.sysinfo.add(self.disk)

    def set_mounts(self, mounts):
        mounts_content = []
        for i, mount in enumerate(mounts):
            (mount_point, block_size, total_blocks, free_blocks) = mount
            mounts_content.append("/dev/sd%d %s fsfs rw 0 0" % (i, mount_point))
            self.stat_results[mount_point] = (block_size, 0,
                                              total_blocks, free_blocks,
                                              0, 0, 0, 0, 0)
        f = open(self.mount_file, "w")
        f.write("\n".join(mounts_content))
        f.close()

    def test_run_returns_succeeded_deferred(self):
        self.set_mounts([("/", 4096, 1000, 1000)])
        result = self.disk.run()
        self.assertTrue(isinstance(result, Deferred))
        called = []
        def callback(result):
            called.append(True)
        result.addCallback(callback)
        self.assertTrue(called)

    def test_everything_is_cool(self):
        self.set_mounts([("/", 4096, 1000, 1000)])
        self.disk.run()
        self.assertEquals(self.sysinfo.get_notes(), [])

    def test_zero_total_space(self):
        """
        When the total space for a mount is 0, the plugin shouldn't flip out
        and kill everybody.
        
        This is a regression test for a ZeroDivisionError!
        """
        self.set_mounts([("/sys", 4096, 0, 0),
                         ("/", 4096, 1000, 1000)])
        self.disk.run()
        self.assertEquals(self.sysinfo.get_notes(), [])

    def test_over_85_percent(self):
        """
        When a filesystem is using more than 85% capacity, a note will be
        displayed.
        """
        self.set_mounts([("/", 4096, 1000000, 150000)])
        self.disk.run()
        self.assertEquals(self.sysinfo.get_notes(),
                          ["/ is using 85.0% of 3.81GB"])

    def test_under_85_percent(self):
        """No note is displayed for a filesystem using less than 85% capacity.
        """
        self.set_mounts([("/", 1024, 1000000, 151000)])
        self.disk.run()
        self.assertEquals(self.sysinfo.get_notes(), [])

    def test_multiple_notes(self):
        """
        A note will be displayed for each filesystem using 85% or more capacity.
        """
        self.set_mounts([("/", 1024, 1000000, 150000),
                         ("/use", 2048, 2000000, 200000),
                         ("/emp", 4096, 3000000, 460000)])
        self.disk.run()
        self.assertEquals(self.sysinfo.get_notes(),
                          ["/ is using 85.0% of 976MB",
                           "/use is using 90.0% of 3.81GB"])

    def test_format_megabytes(self):
        self.assertEquals(format_megabytes(100), "100MB")
        self.assertEquals(format_megabytes(1023), "1023MB")
        self.assertEquals(format_megabytes(1024), "1.00GB")
        self.assertEquals(format_megabytes(1024*1024-1), "1024.00GB")
        self.assertEquals(format_megabytes(1024*1024), "1.00TB")

    def test_header(self):
        """
        A header is printed with usage for the 'primary' filesystem, where
        'primary' means 'filesystem that has /home on it'.
        """
        self.set_mounts([("/", 4096, 1000, 500),
                         ("/home", 4096, 1000, 500)])
        self.disk.run()
        self.assertEquals(self.sysinfo.get_headers(),
                          [("Usage of /home", "66.7%")])
