import os
import unittest

from mock import patch

from landscape.lib import testing
from landscape.lib.disk import (
    get_filesystem_for_path, get_mount_info, is_device_removable,
    _get_device_removable_file_path)


class BaseTestCase(testing.FSTestCase, unittest.TestCase):
    pass


class DiskUtilitiesTest(BaseTestCase):

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

    def set_mount_points(self, points, read_access=True, fs='ext4'):
        """
        This method prepares a fake mounts file containing the
        mount points specified in the C{points} list of strings. This file
        can then be used by referencing C{self.mount_file}.

        If C{read_access} is set to C{False}, then all mount points will
        yield a permission denied error when inspected.
        """
        self.read_access = read_access
        content = "\n".join("/dev/sda%d %s %s rw 0 0" % (i, point, fs)
                            for i, point in enumerate(points))
        f = open(self.mount_file, "w")
        f.write(content)
        f.close()
        for point in points:
            self.stat_results[point] = os.statvfs_result(
                (4096, 0, 1000, 500, 0, 0, 0, 0, 0, 0))

    def test_get_filesystem_for_path(self):
        self.set_mount_points(["/"])
        info = get_filesystem_for_path("/", self.mount_file, self.statvfs)
        self.assertEqual(info["mount-point"], "/")

    def test_get_filesystem_subpath(self):
        self.set_mount_points(["/"])
        self.stat_results["/"] = os.statvfs_result(
            (4096, 0, 1000, 500, 0, 0, 0, 0, 0, 0))
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

    def test_get_filesystem_weird_fs(self):
        self.set_mount_points(["/"], fs='simfs')
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

    def test_ignore_unreadable_mount_point(self):
        """
        We should ignore mountpoints which are unreadable by the user who
        is logging in.
        """
        self.set_mount_points(["/secret"], read_access=False)
        info = get_filesystem_for_path(
            "/secret", self.mount_file, self.statvfs)
        self.assertIs(info, None)

    def test_ignore_unmounted_and_virtual_mountpoints(self):
        """
        Make sure autofs and virtual mountpoints are ignored. This is to
        ensure non-regression on bug #1045374.
        """
        self.read_access = True
        content = "\n".join(["auto_direct /opt/whatever autofs",
                             "none /run/lock tmpfs",
                             "proc /proc proc",
                             "/dev/sda1 /home ext4"])

        f = open(self.mount_file, "w")
        f.write(content)
        f.close()

        self.stat_results["/home"] = os.statvfs_result(
            (4096, 0, 1000, 500, 0, 0, 0, 0, 0, 0))

        result = [x for x in get_mount_info(self.mount_file, self.statvfs)]
        expected = {"device": "/dev/sda1", "mount-point": "/home",
                    "filesystem": "ext4", "total-space": 3, "free-space": 1}
        self.assertEqual([expected], result)


class RemovableDiskTest(BaseTestCase):

    @patch("os.path.islink")
    def test_wb_get_device_removable_file_path(self, is_link_mock):
        """
        When passed a device in /dev, the L{_get_device_removable_file_path}
        function returns the corresponding removable file path in /sys/block.
        """
        device = "/dev/sdb"
        expected = "/sys/block/sdb/removable"

        is_link_mock.return_value = False

        result = _get_device_removable_file_path(device)

        is_link_mock.assert_called_once_with(device)
        self.assertEqual(expected, result)

    @patch("os.path.islink")
    def test_wb_with_partition(self, is_link_mock):
        """
        When passed a device in /dev with a partition number, the
        L{_get_device_removable_file_path} function returns the corresponding
        removable file path in /sys/block.
        """
        device = "/dev/sdb1"
        expected = "/sys/block/sdb/removable"

        is_link_mock.return_value = False

        result = _get_device_removable_file_path(device)

        is_link_mock.assert_called_once_with(device)
        self.assertEqual(expected, result)

    @patch("os.path.islink")
    def test_wb_get_device_removable_file_path_without_dev(self, is_link_mock):
        """
        When passed a device name (not the whole path), the
        L{_get_device_removable_file_path} function returns the corresponding
        removable file path in /sys/block.
        """
        device = "sdb1"
        expected = "/sys/block/sdb/removable"

        is_link_mock.return_value = False

        result = _get_device_removable_file_path(device)

        is_link_mock.assert_called_once_with(device)
        self.assertEqual(expected, result)

    @patch("os.path.islink")
    @patch("os.readlink")
    def test_wb_with_symlink(self, readlink_mock, is_link_mock):
        """
        When the device path passed to L{_get_device_removable_file_path} is a
        symlink (it's the case when disks are mounted by uuid or by label),
        the L{_get_device_removable_file_path} function returns the proper
        corresponding file path in /sys/block.
        """
        device = "/dev/disk/by-uuid/8b2ec410-ebd2-49ec-bb3c-b8b13effab08"

        readlink_mock.return_value = "../../sda1"
        is_link_mock.return_value = True

        expected = "/sys/block/sda/removable"
        result = _get_device_removable_file_path(device)

        readlink_mock.assert_called_once_with(device)
        is_link_mock.assert_called_once_with(device)
        self.assertEqual(expected, result)

    @patch("os.path.islink")
    def test_wb_get_device_removable_file_path_raid_device(self, is_link_mock):
        """
        When passed a more exotic device file, like for example a raid device
        (e.g. /dev/cciss/c0d1p1), the L{_get_device_removable_file_path}
        function does not fail, and returns the expected
        /sys/block/<device>/removable path.
        """
        device = "/dev/cciss/c0d0p0"
        # The expected path does not exists, but it doesn't matter here.
        expected = "/sys/block/c/removable"

        is_link_mock.return_value = False

        result = _get_device_removable_file_path(device)
        is_link_mock.assert_called_once_with(device)
        self.assertEqual(expected, result)

    @patch("landscape.lib.disk._get_device_removable_file_path")
    def test_is_device_removable(self, removable_mock):
        """
        Given the path to a file, determine if it means the device is removable
        or not.
        """
        device = "/dev/sdb1"
        path = self.makeFile("1")

        removable_mock.return_value = path

        self.assertTrue(is_device_removable(device))
        removable_mock.assert_called_once_with(device)

    @patch("landscape.lib.disk._get_device_removable_file_path")
    def test_is_device_removable_false(self, removable_mock):
        """
        Given the path to a file, determine if it means the device is removable
        or not.
        """
        device = "/dev/sdb1"
        path = self.makeFile("0")

        removable_mock.return_value = path

        self.assertFalse(is_device_removable(device))
        removable_mock.assert_called_once_with(device)

    @patch("landscape.lib.disk._get_device_removable_file_path")
    def test_is_device_removable_garbage(self, removable_mock):
        """
        Given the path to a file, determine if it means the device is removable
        or not.
        """
        device = "/dev/sdb1"
        path = self.makeFile("Some garbage")

        removable_mock.return_value = path

        self.assertFalse(is_device_removable(device))
        removable_mock.assert_called_once_with(device)

    @patch("landscape.lib.disk._get_device_removable_file_path")
    def test_is_device_removable_path_doesnt_exist(self, removable_mock):
        """
        When given a non-existing path, report the device as not removable.
        """
        device = "/dev/sdb1"
        path = "/what/ever"

        removable_mock.return_value = path

        self.assertFalse(is_device_removable(device))
        removable_mock.assert_called_once_with(device)

    @patch("os.path.islink")
    def test_is_removable_raid_device(self, is_link_mock):
        """
        When passed the path to a raid device (e.g. /dev/cciss/c0d0p0), the
        is_device_removable function returns False.
        """
        device = "/dev/cciss/c0d1p1"

        is_link_mock.return_value = False

        self.assertFalse(is_device_removable(device))
        is_link_mock.assert_called_once_with(device)

    def test_is_device_removable_memory_card(self):
        """
        The kernel/udev currently consider memory cards such as SD cards as non
        removable
        """
        device = "/dev/mmcblk0p1"  # Device 0, parition 1
        self.assertTrue(is_device_removable(device))
