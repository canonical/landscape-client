import smart

from smart.cache import Package

from landscape.package.interface import (
    install_landscape_interface, uninstall_landscape_interface)

from landscape.package.skeleton import (
    build_skeleton, PackageTypeError, build_skeleton_apt, DEB_PROVIDES,
    DEB_NAME_PROVIDES, DEB_REQUIRES, DEB_UPGRADES, DEB_CONFLICTS)

from landscape.package.tests.helpers import (
    AptFacadeHelper, SmartHelper, HASH1, create_simple_repository, create_deb,
    PKGNAME_MINIMAL, PKGDEB_MINIMAL, HASH_MINIMAL, PKGNAME_SIMPLE_CONFLICT,
    PKGDEB_SIMPLE_CONFLICT, HASH_SIMPLE_CONFLICT)
from landscape.tests.helpers import LandscapeTest


class SkeletonTest(LandscapeTest):

    helpers = [SmartHelper]

    def setUp(self):
        super(SkeletonTest, self).setUp()
        create_deb(self.repository_dir, PKGNAME_MINIMAL, PKGDEB_MINIMAL)
        create_deb(
            self.repository_dir, PKGNAME_SIMPLE_CONFLICT,
            PKGDEB_SIMPLE_CONFLICT)
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

    def test_build_skeleton_minimal(self):
        [minimal_package] = self.cache.getPackages("minimal")
        skeleton = build_skeleton(minimal_package)
        self.assertEqual("minimal", skeleton.name)
        self.assertEqual("1.0", skeleton.version)
        self.assertEqual(skeleton.section, None)
        self.assertEqual(skeleton.summary, None)
        self.assertEqual(skeleton.description, None)
        self.assertEqual(skeleton.size, None)
        self.assertEqual(skeleton.installed_size, None)
        relations = [
            (DEB_NAME_PROVIDES, "minimal = 1.0"),
            (DEB_UPGRADES, "minimal < 1.0")]
        self.assertEqual(relations, skeleton.relations)
        self.assertEqual(skeleton.get_hash(), HASH_MINIMAL)

    def test_build_skeleton_simple_conflict(self):
        [conflict_package] = self.cache.getPackages("simple-conflict")
        skeleton = build_skeleton(conflict_package)
        self.assertEqual("simple-conflict", skeleton.name)
        self.assertEqual("1.0", skeleton.version)
        relations = [
            (DEB_NAME_PROVIDES, "simple-conflict = 1.0"),
            (DEB_UPGRADES, "simple-conflict < 1.0"),
            (DEB_CONFLICTS, "conflict-package")]
        self.assertEqual(relations, skeleton.relations)
        self.assertEqual(skeleton.get_hash(), HASH_SIMPLE_CONFLICT)

    def test_refuse_to_build_non_debian_packages(self):
        self.assertRaises(PackageTypeError, build_skeleton,
                          Package("name", "version"))


class SkeletonAptTest(LandscapeTest):

    helpers = [AptFacadeHelper]

    def setUp(self):
        super(SkeletonAptTest, self).setUp()
        self.repository_dir = self.makeDir()
        create_simple_repository(self.repository_dir)
        create_deb(self.repository_dir, PKGNAME_MINIMAL, PKGDEB_MINIMAL)
        create_deb(
            self.repository_dir, PKGNAME_SIMPLE_CONFLICT,
            PKGDEB_SIMPLE_CONFLICT)
        self.facade.add_channel_deb_dir(self.repository_dir)
        self.facade.reload_channels()
        [self.name1_package] = [
            package for package in self.facade.get_packages()
            if package.name == "name1"]

    def test_build_skeleton_minimal(self):
        [minimal_package] = [
            package for package in self.facade.get_packages()
            if package.name == "minimal"]
        skeleton = build_skeleton_apt(minimal_package)
        self.assertEqual("minimal", skeleton.name)
        self.assertEqual("1.0", skeleton.version)
        self.assertEqual(skeleton.section, None)
        self.assertEqual(skeleton.summary, None)
        self.assertEqual(skeleton.description, None)
        self.assertEqual(skeleton.size, None)
        self.assertEqual(skeleton.installed_size, None)
        relations = [
            (DEB_NAME_PROVIDES, "minimal = 1.0"),
            (DEB_UPGRADES, "minimal < 1.0")]
        self.assertEqual(relations, skeleton.relations)
        self.assertEqual(skeleton.get_hash(), HASH_MINIMAL)

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
            (DEB_NAME_PROVIDES, "name1 = version1-release1"),
            (DEB_REQUIRES, "prerequirename1 = prerequireversion1"),
            (DEB_REQUIRES, "requirename1 = requireversion1"),
            (DEB_UPGRADES, "name1 < version1-release1"),
            (DEB_CONFLICTS, "conflictsname1 = conflictsversion1")]
        self.assertEqual(relations, skeleton.relations)
        self.assertEqual(skeleton.get_hash(), HASH1)

    def test_build_skeleton_simple_conflict(self):
        [conflict_package] = [
            package for package in self.facade.get_packages()
            if package.name == "simple-conflict"]
        skeleton = build_skeleton_apt(conflict_package)
        self.assertEqual("simple-conflict", skeleton.name)
        self.assertEqual("1.0", skeleton.version)
        relations = [
            (DEB_NAME_PROVIDES, "simple-conflict = 1.0"),
            (DEB_UPGRADES, "simple-conflict < 1.0"),
            (DEB_CONFLICTS, "conflict-package")]
        self.assertEqual(relations, skeleton.relations)
        self.assertEqual(skeleton.get_hash(), HASH_SIMPLE_CONFLICT)
