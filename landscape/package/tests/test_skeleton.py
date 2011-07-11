import smart

from smart.cache import Package

from landscape.package.interface import (
    install_landscape_interface, uninstall_landscape_interface)

from landscape.package.skeleton import build_skeleton, PackageTypeError

from landscape.package.tests.helpers import SmartHelper, HASH1
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
