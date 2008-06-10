import os

from landscape.tests.helpers import LandscapeTest

from landscape.lib.bootstrap import (
    BootstrapPath, BootstrapFile, BootstrapDirectory, BootstrapList)


class BootstrapPathTest(LandscapeTest):

    bootstrap_class = BootstrapPath

    def setUp(self):
        super(BootstrapPathTest, self).setUp()
        self.dirname = self.makeDir()
        self.path = os.path.join(self.dirname, "$my_var")
        self.real_path = os.path.join(self.dirname, "my_var_value")

    def test_username(self):
        getpwnam = self.mocker.replace("pwd.getpwnam")
        getpwnam("username").pw_uid
        self.mocker.result(1234)

        getuid = self.mocker.replace("os.getuid")
        getuid()
        self.mocker.result(0)

        chown = self.mocker.replace("os.chown")
        chown(self.real_path, 1234, -1)

        self.mocker.replay()

        file = self.bootstrap_class(self.real_path, username="username")
        file.bootstrap(my_var="my_var_value")

    def test_group(self):
        getgrnam = self.mocker.replace("grp.getgrnam")
        getgrnam("group").gr_gid
        self.mocker.result(5678)

        getuid = self.mocker.replace("os.getuid")
        getuid()
        self.mocker.result(0)

        chown = self.mocker.replace("os.chown")
        chown(self.real_path, -1, 5678)

        self.mocker.replay()

        file = self.bootstrap_class(self.path, group="group")
        file.bootstrap(my_var="my_var_value")

    def test_mode(self):
        chmod = self.mocker.replace("os.chmod")
        chmod(self.real_path, 0644)

        self.mocker.replay()

        file = self.bootstrap_class(self.path, mode=0644)
        file.bootstrap(my_var="my_var_value")

    def test_all_details(self):
        getuid = self.mocker.replace("os.getuid")
        getuid()
        self.mocker.result(0)

        getpwnam = self.mocker.replace("pwd.getpwnam")
        getpwnam("username").pw_uid
        self.mocker.result(1234)

        getgrnam = self.mocker.replace("grp.getgrnam")
        getgrnam("group").gr_gid
        self.mocker.result(5678)

        chown = self.mocker.replace("os.chown")
        chown(self.real_path, 1234, 5678)

        chmod = self.mocker.replace("os.chmod")
        chmod(self.real_path, 0644)

        self.mocker.replay()

        file = self.bootstrap_class(self.path, "username", "group", 0644)
        file.bootstrap(my_var="my_var_value")

    def test_all_details_with_non_root(self):
        getuid = self.mocker.replace("os.getuid")
        getuid()
        self.mocker.result(1000)

        chmod = self.mocker.replace("os.chmod")
        chmod(self.real_path, 0644)

        self.mocker.replay()

        file = self.bootstrap_class(self.path, "username", "group", 0644)
        file.bootstrap(my_var="my_var_value")


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
        self.assertEquals(open(filename).read(), "CONTENT")


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


class BootstrapListTest(LandscapeTest):

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
