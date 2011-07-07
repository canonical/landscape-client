import os

from landscape.lib.disk import get_filesystem_for_path
from landscape.tests.helpers import LandscapeTest


class DiskUtilitiesTest(LandscapeTest):

    def setUp(self):
        super(DiskUtilitiesTest, self).setUp()
        self.mount_file = self.makeFile("")
        self.stat_results = {}

    def statvfs(self, point):
        """
        Return the requested mount point information. If C{read_access} was
        set to C{False} when this mount point was created, then we raise an
        exception to simulate a permission denied error.
        """
        if self.read_access:
            return self.stat_results[point]
        else:
            raise OSError("Permission denied")

    def set_mount_points(self, points, read_access=True):
        """
        This method prepares a fake mounts file containing the
        mount points specified in the C{points} list of strings. This file
        can then be used by referencing C{self.mount_file}.

        If C{read_access} is set to C{False}, then all mount points will
        yield a permission denied error when inspected.
        """
        self.read_access = read_access
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
        self.assertEqual(info["mount-point"], "/")

    def test_get_filesystem_subpath(self):
        self.set_mount_points(["/"])
        self.stat_results["/"] = (4096, 0, 1000, 500, 0, 0, 0, 0, 0)
        info = get_filesystem_for_path("/home", self.mount_file, self.statvfs)
        self.assertEqual(info["mount-point"], "/")

    def test_get_filesystem_subpath_closest(self):
        self.set_mount_points(["/", "/home"])
        info = get_filesystem_for_path("/home", self.mount_file, self.statvfs)
        self.assertEqual(info["mount-point"], "/home")

    def test_get_filesystem_subpath_not_stupid(self):
        self.set_mount_points(["/", "/ho"])
        info = get_filesystem_for_path("/home", self.mount_file, self.statvfs)
        self.assertEqual(info["mount-point"], "/")

    def test_symlink_home(self):
        symlink_path = self.makeFile()
        os.symlink("/foo/bar", symlink_path)
        self.addCleanup(os.remove, symlink_path)
        self.set_mount_points(["/", "/foo"])
        info = get_filesystem_for_path(symlink_path,
                                       self.mount_file, self.statvfs)
        self.assertEqual(info["mount-point"], "/foo")

    def test_whitelist(self):
        self.set_mount_points(["/"])
        info = get_filesystem_for_path(
            "/", self.mount_file, self.statvfs, ["ext3"])
        self.assertIdentical(info, None)
        info = get_filesystem_for_path(
            "/", self.mount_file, self.statvfs, ["ext3", "fsfs"])
        self.assertNotIdentical(info, None)

    def test_ignore_unreadable_mount_point(self):
        """
        We should ignore mountpoints which are unreadable by the user who
        is logging in.
        """
        self.set_mount_points(["/secret"], read_access=False)
        info = get_filesystem_for_path(
            "/secret", self.mount_file, self.statvfs)
        self.assertIdentical(info, None)
