import smart

from smart.cache import Package

from landscape.package.interface import (
    install_landscape_interface, uninstall_landscape_interface)

from landscape.package.skeleton import (
    build_skeleton, PackageTypeError, build_skeleton_apt, DEB_PROVIDES,
    DEB_NAME_PROVIDES, DEB_REQUIRES, DEB_OR_REQUIRES, DEB_UPGRADES,
    DEB_CONFLICTS)

from landscape.package.tests.helpers import (
    AptFacadeHelper, SmartHelper, HASH1, create_simple_repository, create_deb,
    PKGNAME_MINIMAL, PKGDEB_MINIMAL, HASH_MINIMAL, PKGNAME_SIMPLE_RELATIONS,
    PKGDEB_SIMPLE_RELATIONS, HASH_SIMPLE_RELATIONS, PKGNAME_VERSION_RELATIONS,
    PKGDEB_VERSION_RELATIONS, HASH_VERSION_RELATIONS,
    PKGNAME_MULTIPLE_RELATIONS, PKGDEB_MULTIPLE_RELATIONS,
    HASH_MULTIPLE_RELATIONS, PKGNAME_OR_RELATIONS, PKGDEB_OR_RELATIONS,
    HASH_OR_RELATIONS)
from landscape.tests.helpers import LandscapeTest


class SkeletonTestHelper(object):
    """A helper to set up a repository for the skeleton tests."""

    def set_up(self, test_case):
        test_case.skeleton_repository_dir = test_case.makeDir()
        create_simple_repository(test_case.skeleton_repository_dir)
        create_deb(
            test_case.skeleton_repository_dir, PKGNAME_MINIMAL, PKGDEB_MINIMAL)
        create_deb(
            test_case.skeleton_repository_dir, PKGNAME_SIMPLE_RELATIONS,
            PKGDEB_SIMPLE_RELATIONS)
        create_deb(
            test_case.skeleton_repository_dir, PKGNAME_VERSION_RELATIONS,
            PKGDEB_VERSION_RELATIONS)
        create_deb(
            test_case.skeleton_repository_dir, PKGNAME_MULTIPLE_RELATIONS,
            PKGDEB_MULTIPLE_RELATIONS)
        create_deb(
            test_case.skeleton_repository_dir, PKGNAME_OR_RELATIONS,
            PKGDEB_OR_RELATIONS)

class SkeletonTestMixin(object):
    """Tests for building a skeleton from a package.

    This class should be mixed in to test different backends, like smart
    and apt.

    The main test case classes need to implement C{get_package(name)} to
    get a package by name, and C{build_skeleton(package, with_info,
    with_unicode}, which builds the skeleton.
    """

    def test_build_skeleton(self):
        """
        C{build_skeleton} builds a C{PackageSkeleton} from a package. If
        with_info isn't passed, C{section}, C{summary}, C{description},
        C{size} and C{installed_size} will be C{None}.
        """
        pkg1 = self.get_package("name1")
        skeleton = self.build_skeleton(pkg1)
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
        self.assertEqual(skeleton.get_hash(), HASH1)

    def test_build_skeleton_without_unicode(self):
        """
        If C{with_unicode} isn't passed to C{build_skeleton}, the name
        and version of the skeleton are byte strings. The hash doesn't
        change, though.
        """
        pkg1 = self.get_package("name1")
        skeleton = self.build_skeleton(pkg1)
        self.assertTrue(isinstance(skeleton.name, str))
        self.assertTrue(isinstance(skeleton.version, str))
        self.assertEqual(skeleton.get_hash(), HASH1)

    def test_build_skeleton_with_unicode(self):
        """
        If C{with_unicode} is passed to C{build_skeleton}, the name
        and version of the skeleton are unicode strings.
        """
        pkg1 = self.get_package("name1")
        skeleton = self.build_skeleton(pkg1, with_unicode=True)
        self.assertTrue(isinstance(skeleton.name, unicode))
        self.assertTrue(isinstance(skeleton.version, unicode))
        self.assertEqual(skeleton.get_hash(), HASH1)

    def test_build_skeleton_with_info(self):
        """
        If C{with_info} is passed to C{build_skeleton}, C{section},
        C{summary}, C{description} and the size fields will be extracted
        from the package.
        """
        pkg1 = self.get_package("name1")
        skeleton = self.build_skeleton(pkg1, with_info=True)
        self.assertEqual(skeleton.section, "Group1")
        self.assertEqual(skeleton.summary, "Summary1")
        self.assertEqual(skeleton.description, "Description1")
        self.assertEqual(skeleton.size, 1038)
        self.assertEqual(skeleton.installed_size, 28672)

    def test_build_skeleton_minimal(self):
        """
        A package that has only the required fields will still have some
        relations defined.
        """
        minimal_package = self.get_package("minimal")
        skeleton = self.build_skeleton(minimal_package)
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

    def test_build_skeleton_minimal_with_info(self):
        """
        If some fields that C{with_info} wants aren't there, they will
        be either an empty string or None, depending on which field.
        """
        package = self.get_package("minimal")
        skeleton = self.build_skeleton(package, True)
        self.assertEqual(skeleton.section, "")
        self.assertEqual(
            skeleton.summary,
            "A minimal package with no dependencies or other relations.")
        self.assertEqual(skeleton.description, "")
        self.assertEqual(skeleton.size, 558)
        self.assertEqual(skeleton.installed_size, None)

    def test_build_skeleton_simple_relations(self):
        """
        Relations that are specified in the package control file can be
        simple, i.e. not specifying a version.
        """
        package = self.get_package("simple-relations")
        skeleton = self.build_skeleton(package)
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
        """
        Relations that are specified in the package control file can be
        version dependent.
        """
        package = self.get_package("version-relations")
        skeleton = self.build_skeleton(package)
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

    def test_build_skeleton_multiple_relations(self):
        """
        The relations in the package control can have multiple values.
        In that case, one relation for each value is created in the
        skeleton.
        """
        package = self.get_package("multiple-relations")
        skeleton = self.build_skeleton(package)
        self.assertEqual("multiple-relations", skeleton.name)
        self.assertEqual("1.0", skeleton.version)
        relations = [
            (DEB_PROVIDES, "provide1"),
            (DEB_PROVIDES, "provide2"),
            (DEB_NAME_PROVIDES, "multiple-relations = 1.0"),
            (DEB_REQUIRES, "depend1 = 2.0"),
            (DEB_REQUIRES, "depend2"),
            (DEB_REQUIRES, "predepend1 <= 2.0"),
            (DEB_REQUIRES, "predepend2"),
            (DEB_UPGRADES, "multiple-relations < 1.0"),
            (DEB_CONFLICTS, "conflict1 < 2.0"),
            (DEB_CONFLICTS, "conflict2")]
        self.assertEqual(relations, skeleton.relations)
        self.assertEqual(skeleton.get_hash(), HASH_MULTIPLE_RELATIONS)

    def test_build_skeleton_or_relations(self):
        """
        The Depend and Pre-Depend fields can have an or relation. That
        is considered to be a single relation, with a special type.
        """
        package = self.get_package("or-relations")
        skeleton = self.build_skeleton(package)
        self.assertEqual("or-relations", skeleton.name)
        self.assertEqual("1.0", skeleton.version)
        relations = [
            (DEB_NAME_PROVIDES, "or-relations = 1.0"),
            (DEB_OR_REQUIRES, "depend1 = 2.0 | depend2"),
            (DEB_OR_REQUIRES, "predepend1 <= 2.0 | predepend2"),
            (DEB_UPGRADES, "or-relations < 1.0")]
        self.assertEqual(relations, skeleton.relations)
        self.assertEqual(skeleton.get_hash(), HASH_OR_RELATIONS)


class SmartSkeletonTest(LandscapeTest, SkeletonTestMixin):
    """C{PackageSkeleton} tests for smart packages."""

    helpers = [SmartHelper, SkeletonTestHelper]

    def setUp(self):
        super(SmartSkeletonTest, self).setUp()
        install_landscape_interface()
        self.ctrl = smart.init(interface="landscape", datadir=self.smart_dir)
        smart.sysconf.set(
            "channels", {"alias": {"type": "deb-dir",
                                   "path": self.skeleton_repository_dir}})
        self.ctrl.reloadChannels()
        self.cache = self.ctrl.getCache()

    def tearDown(self):
        uninstall_landscape_interface()
        super(SmartSkeletonTest, self).tearDown()

    def get_package(self, name):
        """Return the package with the specified name."""
        [package] = self.cache.getPackages(name)
        return package

    def build_skeleton(self, *args, **kwargs):
        """Build the skeleton to be tested."""
        return build_skeleton(*args, **kwargs)

    def test_refuse_to_build_non_debian_packages(self):
        self.assertRaises(PackageTypeError, build_skeleton,
                          Package("name", "version"))


class SkeletonAptTest(LandscapeTest, SkeletonTestMixin):
    """C{PackageSkeleton} tests for apt packages."""

    helpers = [AptFacadeHelper, SkeletonTestHelper]

    def setUp(self):
        super(SkeletonAptTest, self).setUp()
        self.facade.add_channel_deb_dir(self.skeleton_repository_dir)
        self.facade.reload_channels()

    def get_package(self, name):
        """Return the package with the specified name."""
        [package] = [
            package for package in self.facade.get_packages()
            if package.name == name]
        return package

    def build_skeleton(self, *args, **kwargs):
        """Build the skeleton to be tested."""
        return build_skeleton_apt(*args, **kwargs)
