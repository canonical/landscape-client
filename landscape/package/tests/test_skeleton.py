import smart

from smart.cache import Package

from landscape.package.interface import (
    install_landscape_interface, uninstall_landscape_interface)

from landscape.package.skeleton import (
    build_skeleton, PackageTypeError, build_skeleton_apt, DEB_PROVIDES,
    DEB_NAME_PROVIDES, DEB_REQUIRES, DEB_UPGRADES, DEB_CONFLICTS)

from landscape.package.tests.helpers import (
    AptFacadeHelper, SmartHelper, HASH1, create_simple_repository, create_deb,
    PKGNAME_MINIMAL, PKGDEB_MINIMAL, HASH_MINIMAL, PKGNAME_SIMPLE_RELATIONS,
    PKGDEB_SIMPLE_RELATIONS, HASH_SIMPLE_RELATIONS, PKGNAME_VERSION_RELATIONS,
    PKGDEB_VERSION_RELATIONS, HASH_VERSION_RELATIONS)
from landscape.tests.helpers import LandscapeTest


class SkeletonTest(LandscapeTest):

    helpers = [SmartHelper]

    def setUp(self):
        super(SkeletonTest, self).setUp()
        create_deb(self.repository_dir, PKGNAME_MINIMAL, PKGDEB_MINIMAL)
        create_deb(
            self.repository_dir, PKGNAME_SIMPLE_RELATIONS,
            PKGDEB_SIMPLE_RELATIONS)
        create_deb(
            self.repository_dir, PKGNAME_VERSION_RELATIONS,
            PKGDEB_VERSION_RELATIONS)
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

    def test_build_skeleton_simple_relations(self):
        [package] = self.cache.getPackages("simple-relations")
        skeleton = build_skeleton(package)
        self.assertEqual("simple-relations", skeleton.name)
        self.assertEqual("1.0", skeleton.version)
        relations = [
            (DEB_PROVIDES, "provide1"),
            (DEB_NAME_PROVIDES, "simple-relations = 1.0"),
            (DEB_REQUIRES, "depend1"),
            (DEB_REQUIRES, "predepend1"),
            (DEB_UPGRADES, "simple-relations < 1.0"),
            (DEB_CONFLICTS, "conflict1")]
        self.assertEqual(relations, skeleton.relations)
        self.assertEqual(skeleton.get_hash(), HASH_SIMPLE_RELATIONS)

    def test_build_skeleton_version_relations(self):
        [package] = self.cache.getPackages("version-relations")
        skeleton = build_skeleton(package)
        self.assertEqual("version-relations", skeleton.name)
        self.assertEqual("1.0", skeleton.version)
        relations = [
            (DEB_PROVIDES, "provide1"),
            (DEB_NAME_PROVIDES, "version-relations = 1.0"),
            (DEB_REQUIRES, "depend1 = 2.0"),
            (DEB_REQUIRES, "predepend1 <= 2.0"),
            (DEB_UPGRADES, "version-relations < 1.0"),
            (DEB_CONFLICTS, "conflict1 < 2.0")]
        self.assertEqual(relations, skeleton.relations)
        self.assertEqual(skeleton.get_hash(), HASH_VERSION_RELATIONS)

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
            self.repository_dir, PKGNAME_SIMPLE_RELATIONS,
            PKGDEB_SIMPLE_RELATIONS)
        create_deb(
            self.repository_dir, PKGNAME_VERSION_RELATIONS,
            PKGDEB_VERSION_RELATIONS)
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

    def test_build_skeleton_simple_relations(self):
        [package] = [
            package for package in self.facade.get_packages()
            if package.name == "simple-relations"]
        skeleton = build_skeleton_apt(package)
        self.assertEqual("simple-relations", skeleton.name)
        self.assertEqual("1.0", skeleton.version)
        relations = [
            (DEB_PROVIDES, "provide1"),
            (DEB_NAME_PROVIDES, "simple-relations = 1.0"),
            (DEB_REQUIRES, "depend1"),
            (DEB_REQUIRES, "predepend1"),
            (DEB_UPGRADES, "simple-relations < 1.0"),
            (DEB_CONFLICTS, "conflict1")]
        self.assertEqual(relations, skeleton.relations)
        self.assertEqual(skeleton.get_hash(), HASH_SIMPLE_RELATIONS)

    def test_build_skeleton_version_relations(self):
        [package] = [
            package for package in self.facade.get_packages()
            if package.name == "version-relations"]
        skeleton = build_skeleton_apt(package)
        self.assertEqual("version-relations", skeleton.name)
        self.assertEqual("1.0", skeleton.version)
        relations = [
            (DEB_PROVIDES, "provide1"),
            (DEB_NAME_PROVIDES, "version-relations = 1.0"),
            (DEB_REQUIRES, "depend1 = 2.0"),
            (DEB_REQUIRES, "predepend1 <= 2.0"),
            (DEB_UPGRADES, "version-relations < 1.0"),
            (DEB_CONFLICTS, "conflict1 < 2.0")]
        self.assertEqual(relations, skeleton.relations)
        self.assertEqual(skeleton.get_hash(), HASH_VERSION_RELATIONS)

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
