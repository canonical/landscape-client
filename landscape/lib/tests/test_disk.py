import os

from landscape.lib.disk import get_filesystem_for_path
from landscape.tests.helpers import LandscapeTest


class DiskUtilitiesTest(LandscapeTest):

    def setUp(self):
        super(DiskUtilitiesTest, self).setUp()
        self.mount_file = self.makeFile("")
        self.stat_results = {}
        self.statvfs = self.stat_results.get

    def set_mount_points(self, points):
        content = "\n".join("/dev/sda%d %s fsfs rw 0 0" % (i, point)
                            for i, point in enumerate(points))
        f = open(self.mount_file, "w")
        f.write(content)
        f.close()
        for point in points:
            self.stat_results[point] = (4096, 0, 1000, 500, 0, 0, 0, 0, 0)

    def test_get_filesystem_for_path(self):
        self.set_mount_points(["/"])
        info = get_filesystem_for_path("/", self.mount_file, self.statvfs)
        self.assertEquals(info["mount-point"], "/")

    def test_get_filesystem_subpath(self):
        self.set_mount_points(["/"])
        self.stat_results["/"] = (4096, 0, 1000, 500, 0, 0, 0, 0, 0)
        info = get_filesystem_for_path("/home", self.mount_file, self.statvfs)
        self.assertEquals(info["mount-point"], "/")

    def test_get_filesystem_subpath_closest(self):
        self.set_mount_points(["/", "/home"])
        info = get_filesystem_for_path("/home", self.mount_file, self.statvfs)
        self.assertEquals(info["mount-point"], "/home")

    def test_get_filesystem_subpath_not_stupid(self):
        self.set_mount_points(["/", "/ho"])
        info = get_filesystem_for_path("/home", self.mount_file, self.statvfs)
        self.assertEquals(info["mount-point"], "/")

    def test_symlink_home(self):
        symlink_path = self.makeFile()
        os.symlink("/foo/bar", symlink_path)
        self.addCleanup(os.remove, symlink_path)
        self.set_mount_points(["/", "/foo"])
        info = get_filesystem_for_path(symlink_path,
                                       self.mount_file, self.statvfs)
        self.assertEquals(info["mount-point"], "/foo")

    def test_whitelist(self):
        self.set_mount_points(["/"])
        info = get_filesystem_for_path(
            "/", self.mount_file, self.statvfs, ["ext3"])
        self.assertIdentical(info, None)
        info = get_filesystem_for_path(
            "/", self.mount_file, self.statvfs, ["ext3", "fsfs"])
        self.assertNotIdentical(info, None)
