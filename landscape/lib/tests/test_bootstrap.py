import os
import unittest

from mock import patch, Mock

from landscape.lib import testing
from landscape.lib.bootstrap import (
    BootstrapPath, BootstrapFile, BootstrapDirectory, BootstrapList)


class BaseTestCase(testing.FSTestCase, unittest.TestCase):
    pass


class BootstrapPathTest(BaseTestCase):

    bootstrap_class = BootstrapPath

    def setUp(self):
        super(BootstrapPathTest, self).setUp()
        self.dirname = self.makeDir()
        self.path = os.path.join(self.dirname, "$my_var")
        self.real_path = os.path.join(self.dirname, "my_var_value")

    @patch("os.chown")
    @patch("os.getuid")
    @patch("pwd.getpwnam")
    def test_username(self, getpwnam, getuid, chown):
        getpwnam.return_value = Mock()
        getpwnam.return_value.pw_uid = 1234

        getuid.return_value = 0

        file = self.bootstrap_class(self.real_path, username="username")
        file.bootstrap(my_var="my_var_value")

        getpwnam.assert_called_with("username")
        getuid.assert_called_with()
        chown.assert_called_with(self.real_path, 1234, -1)

    @patch("os.chown")
    @patch("os.getuid")
    @patch("grp.getgrnam")
    def test_group(self, getgrnam, getuid, chown):
        getgrnam.return_value = Mock()
        getgrnam.return_value.gr_gid = 5678

        getuid.return_value = 0

        file = self.bootstrap_class(self.path, group="group")
        file.bootstrap(my_var="my_var_value")

        getgrnam.assert_called_with("group")
        getuid.assert_called_with()
        chown.assert_called_with(self.real_path, -1, 5678)

    @patch("os.chmod")
    def test_mode(self, chmod):
        file = self.bootstrap_class(self.path, mode=0o644)
        file.bootstrap(my_var="my_var_value")

        chmod.assert_called_with(self.real_path, 0o644)

    @patch("os.chmod")
    @patch("os.chown")
    @patch("grp.getgrnam")
    @patch("pwd.getpwnam")
    @patch("os.getuid")
    def test_all_details(self, getuid, getpwnam, getgrnam, chown, chmod):
        getuid.return_value = 0

        getpwnam.return_value = Mock()
        getpwnam.return_value.pw_uid = 1234

        getgrnam.return_value = Mock()
        getgrnam.return_value.gr_gid = 5678

        file = self.bootstrap_class(self.path, "username", "group", 0o644)
        file.bootstrap(my_var="my_var_value")

        getuid.assert_called_with()
        getpwnam.assert_called_with("username")
        getgrnam.assert_called_with("group")
        chown.assert_called_with(self.real_path, 1234, 5678)
        chmod.assert_called_with(self.real_path, 0o644)

    @patch("os.chmod")
    @patch("os.getuid")
    def test_all_details_with_non_root(self, getuid, chmod):
        getuid.return_value = 1000

        file = self.bootstrap_class(self.path, "username", "group", 0o644)
        file.bootstrap(my_var="my_var_value")

        getuid.assert_called_with()
        chmod.assert_called_with(self.real_path, 0o644)


class BootstrapCreationTest(BootstrapPathTest):

    bootstrap_class = BootstrapFile

    def exists(self, path):
        return os.path.isfile(path)

    def test_creation(self):
        file = self.bootstrap_class(self.path)
        self.assertFalse(self.exists(self.real_path))
        file.bootstrap(my_var="my_var_value")
        self.assertTrue(self.exists(self.real_path))


class BootstrapFileTest(BootstrapCreationTest):

    def test_creation_wont_overwrite(self):
        filename = self.makeFile("CONTENT")
        file = self.bootstrap_class(filename)
        file.bootstrap()
        self.assertEqual(open(filename).read(), "CONTENT")


class BootstrapDirectoryTest(BootstrapCreationTest):

    bootstrap_class = BootstrapDirectory

    def exists(self, path):
        return os.path.isdir(path)

    def test_creation_works_with_existing(self):
        dirname = self.makeDir()
        dir = self.bootstrap_class(dirname)
        dir.bootstrap()
        self.assertTrue(self.exists(dirname))

    def test_creation_will_fail_correctly(self):
        filename = self.makeFile("I AM A *FILE*")
        dir = self.bootstrap_class(filename)
        self.assertRaises(OSError, dir.bootstrap)


class BootstrapListTest(BaseTestCase):

    def test_creation(self):
        dirname = self.makeDir()

        list = BootstrapList([BootstrapFile("$dirname/filename"),
                              BootstrapDirectory("$dirname/dirname"),
                              BootstrapFile("$dirname/dirname/filename")])

        list.bootstrap(dirname=dirname)

        self.assertTrue(os.path.isfile(os.path.join(dirname, "filename")))
        self.assertTrue(os.path.isdir(os.path.join(dirname, "dirname")))
        self.assertTrue(os.path.isfile(os.path.join(dirname,
                                                    "dirname/filename")))
