import smart

from smart.cache import Package

from landscape.package.interface import (
    install_landscape_interface, uninstall_landscape_interface)

from landscape.package.skeleton import (
    build_skeleton, PackageTypeError, build_skeleton_apt, DEB_PROVIDES,
    DEB_NAME_PROVIDES)

from landscape.package.tests.helpers import (
    AptFacadeHelper, SmartHelper, HASH1, create_simple_repository)
from landscape.tests.helpers import LandscapeTest


class SkeletonTest(LandscapeTest):

    helpers = [SmartHelper]

    def setUp(self):
        super(SkeletonTest, self).setUp()
        install_landscape_interface()
        self.ctrl = smart.init(interface="landscape", datadir=self.smart_dir)
        smart.sysconf.set("channels", {"alias": {"type": "deb-dir",
                                                 "path": self.repository_dir}})
        self.ctrl.reloadChannels()
        self.cache = self.ctrl.getCache()

    def tearDown(self):
        uninstall_landscape_interface()
        super(SkeletonTest, self).tearDown()

    def test_build_skeleton(self):
        pkg1 = self.cache.getPackages("name1")[0]
        skeleton = build_skeleton(pkg1)
        self.assertEqual(skeleton.get_hash(), HASH1)

    def test_build_skeleton_with_info(self):
        pkg1 = self.cache.getPackages("name1")[0]
        skeleton = build_skeleton(pkg1, True)
        self.assertEqual(skeleton.section, "Group1")
        self.assertEqual(skeleton.summary, "Summary1")
        self.assertEqual(skeleton.description, "Description1")
        self.assertEqual(skeleton.size, 1038)
        self.assertEqual(skeleton.installed_size, 28672)

    def test_refuse_to_build_non_debian_packages(self):
        self.assertRaises(PackageTypeError, build_skeleton,
                          Package("name", "version"))


class SkeletonAptTest(LandscapeTest):

    helpers = [AptFacadeHelper]

    def setUp(self):
        super(SkeletonAptTest, self).setUp()
        self.repository_dir = self.makeDir()
        create_simple_repository(self.repository_dir)
        self.facade.add_channel_deb_dir(self.repository_dir)
        self.facade.reload_channels()
        [self.name1_package] = [
            package for package in self.facade.get_packages()
            if package.name == "name1"]

    def test_build_skeleton(self):
        skeleton = build_skeleton_apt(self.name1_package)
        self.assertEqual("name1", skeleton.name)
        self.assertEqual("version1-release1", skeleton.version)
        self.assertEqual(skeleton.section, None)
        self.assertEqual(skeleton.summary, None)
        self.assertEqual(skeleton.description, None)
        self.assertEqual(skeleton.size, None)
        self.assertEqual(skeleton.installed_size, None)
        relations = [
            (DEB_PROVIDES, "providesname1"),
            (DEB_NAME_PROVIDES, "name1 = version1-release1")]
        self.assertEqual(relations, skeleton.relations)
