import time
import os
import re
import sys
import textwrap
import tempfile

try:
    import smart
    from smart.control import Control
    from smart.cache import Provides
    from smart.const import NEVER, ALWAYS
except ImportError:
    # Smart is optional if AptFacade is being used.
    pass

import apt_pkg
from apt.package import Package
from aptsources.sourceslist import SourcesList

from twisted.internet import reactor
from twisted.internet.defer import Deferred
from twisted.internet.utils import getProcessOutputAndValue

from landscape.lib.fs import read_file
from landscape.package import facade as facade_module
from landscape.package.facade import (
    TransactionError, DependencyError, ChannelError, SmartError, AptFacade,
    has_new_enough_apt)

from landscape.tests.mocker import ANY
from landscape.tests.helpers import LandscapeTest
from landscape.package.tests.helpers import (
    SmartFacadeHelper, HASH1, HASH2, HASH3, PKGNAME1, PKGNAME2, PKGNAME3,
    PKGNAME4, PKGDEB4, PKGDEB1, PKGNAME_MINIMAL, PKGDEB_MINIMAL,
    create_full_repository, create_deb, AptFacadeHelper,
    create_simple_repository)


class FakeOwner(object):
    """Fake Owner object that apt.progress.text.AcquireProgress expects."""

    def __init__(self, filesize, error_text=""):
        self.id = None
        self.filesize = filesize
        self.complete = False
        self.status = None
        self.STAT_DONE = object()
        self.error_text = error_text


class FakeFetchItem(object):
    """Fake Item object that apt.progress.text.AcquireProgress expects."""

    def __init__(self, owner, description):
        self.owner = owner
        self.description = description


class AptFacadeTest(LandscapeTest):

    if not has_new_enough_apt:
        skip = "Can't use AptFacade on hardy"

    helpers = [AptFacadeHelper]

    def version_sortkey(self, version):
        """Return a key by which a Version object can be sorted."""
        return (version.package, version)

    def test_default_root(self):
        """
        C{AptFacade} can be created by not providing a root directory,
        which means that the currently configured root (most likely /)
        will be used.
        """
        original_dpkg_root = apt_pkg.config.get("Dir")
        AptFacade()
        self.assertEqual(original_dpkg_root, apt_pkg.config.get("Dir"))

    def test_custom_root_create_required_files(self):
        """
        If a custom root is passed to the constructor, the directory and
        files that apt expects to be there will be created.
        """
        root = self.makeDir()
        AptFacade(root=root)
        self.assertTrue(os.path.exists(os.path.join(root, "etc", "apt")))
        self.assertTrue(
            os.path.exists(os.path.join(root, "etc", "apt", "sources.list.d")))
        self.assertTrue(os.path.exists(
            os.path.join(root, "var", "cache", "apt", "archives", "partial")))
        self.assertTrue(os.path.exists(
            os.path.join(root, "var", "lib", "apt", "lists", "partial")))
        self.assertTrue(
            os.path.exists(os.path.join(root, "var", "lib", "dpkg", "status")))

    def test_no_system_packages(self):
        """
        If the dpkg status file is empty, not packages are reported by
        C{get_packages()}.
        """
        self.facade.reload_channels()
        self.assertEqual([], list(self.facade.get_packages()))

    def test_get_packages_single_version(self):
        """
        If the dpkg status file contains some packages, those packages
        are reported by C{get_packages()}.
        """
        self._add_system_package("foo")
        self._add_system_package("bar")
        self.facade.reload_channels()
        self.assertEqual(
            ["bar", "foo"],
            sorted(version.package.name
                   for version in self.facade.get_packages()))

    def test_get_packages_multiple_version(self):
        """
        If there are multiple versions of a package, C{get_packages()}
        returns one object per version.
        """
        deb_dir = self.makeDir()
        self._add_system_package("foo", version="1.0")
        self._add_package_to_deb_dir(deb_dir, "foo", version="1.5")
        self.facade.add_channel_apt_deb("file://%s" % deb_dir, "./")
        self.facade.reload_channels()
        self.assertEqual(
            [("foo", "1.0"), ("foo", "1.5")],
            sorted((version.package.name, version.version)
                   for version in self.facade.get_packages()))

    def test_get_packages_multiple_architectures(self):
        """
        If there are multiple architectures for a package, only the native
        architecture is reported by C{get_packages()}.
        """
        apt_pkg.config.clear("APT::Architectures")
        apt_pkg.config.set("APT::Architecture", "amd64")
        apt_pkg.config.set("APT::Architectures::", "amd64")
        apt_pkg.config.set("APT::Architectures::", "i386")
        facade = AptFacade(apt_pkg.config.get("Dir"))

        self._add_system_package("foo", version="1.0", architecture="amd64")
        self._add_system_package("bar", version="1.1", architecture="i386")
        facade.reload_channels()
        self.assertEqual([("foo", "1.0")],
                         [(version.package.name, version.version)
                          for version in facade.get_packages()])

    def test_add_channel_apt_deb_without_components(self):
        """
        C{add_channel_apt_deb()} adds a new deb URL to a file in
        sources.list.d.

        If no components are given, nothing is written after the dist.
        """
        self.facade.add_channel_apt_deb(
            "http://example.com/ubuntu", "lucid")
        list_filename = (
            self.apt_root +
            "/etc/apt/sources.list.d/_landscape-internal-facade.list")
        sources_contents = read_file(list_filename)
        self.assertEqual(
            "deb http://example.com/ubuntu lucid\n",
            sources_contents)

    def test_add_channel_apt_deb_with_components(self):
        """
        C{add_channel_apt_deb()} adds a new deb URL to a file in
        sources.list.d.

        If components are given, they are included after the dist.
        """
        self.facade.add_channel_apt_deb(
            "http://example.com/ubuntu", "lucid", ["main", "restricted"])
        list_filename = (
            self.apt_root +
            "/etc/apt/sources.list.d/_landscape-internal-facade.list")
        sources_contents = read_file(list_filename)
        self.assertEqual(
            "deb http://example.com/ubuntu lucid main restricted\n",
            sources_contents)

    def test_add_channel_deb_dir_adds_deb_channel(self):
        """
        C{add_channel_deb_dir()} adds a deb channel pointing to the
        directory containing the packages.
        """
        deb_dir = self.makeDir()
        create_simple_repository(deb_dir)
        self.facade.add_channel_deb_dir(deb_dir)
        self.assertEqual(1, len(self.facade.get_channels()))
        self.assertEqual([{"baseurl": "file://%s" % deb_dir,
                           "distribution": "./",
                           "components": "",
                           "type": "deb"}],
                         self.facade.get_channels())

    def test_get_package_stanza(self):
        """
        C{get_package_stanza} returns an entry for the package that can
        be included in a Packages file.
        """
        deb_dir = self.makeDir()
        create_deb(deb_dir, PKGNAME1, PKGDEB1)
        deb_file = os.path.join(deb_dir, PKGNAME1)
        stanza = self.facade.get_package_stanza(deb_file)
        SHA256 = (
            "f899cba22b79780dbe9bbbb802ff901b7e432425c264dc72e6bb20c0061e4f26")
        self.assertEqual(textwrap.dedent("""\
            Package: name1
            Priority: optional
            Section: Group1
            Installed-Size: 28
            Maintainer: Gustavo Niemeyer <gustavo@niemeyer.net>
            Architecture: all
            Version: version1-release1
            Provides: providesname1
            Depends: requirename1 (= requireversion1)
            Pre-Depends: prerequirename1 (= prerequireversion1)
            Recommends: recommendsname1 (= recommendsversion1)
            Suggests: suggestsname1 (= suggestsversion1)
            Conflicts: conflictsname1 (= conflictsversion1)
            Filename: %(filename)s
            Size: 1038
            MD5sum: efe83eb2b891046b303aaf9281c14e6e
            SHA1: b4ebcd2b0493008852a4954edc30a236d516c638
            SHA256: %(sha256)s
            Description: Summary1
             Description1
            """ % {"filename": PKGNAME1, "sha256": SHA256}),
            stanza)

    def test_add_channel_deb_dir_creates_packages_file(self):
        """
        C{add_channel_deb_dir} creates a Packages file in the directory
        with packages.
        """
        deb_dir = self.makeDir()
        create_simple_repository(deb_dir)
        self.facade.add_channel_deb_dir(deb_dir)
        packages_contents = read_file(os.path.join(deb_dir, "Packages"))
        expected_contents = "\n".join(
            self.facade.get_package_stanza(os.path.join(deb_dir, pkg_name))
            for pkg_name in [PKGNAME1, PKGNAME2, PKGNAME3])
        self.assertEqual(expected_contents, packages_contents)

    def test_add_channel_deb_dir_get_packages(self):
        """
        After calling {add_channel_deb_dir} and reloading the channels,
        the packages in the deb dir is included in the package list.
        """
        deb_dir = self.makeDir()
        create_simple_repository(deb_dir)
        self.facade.add_channel_deb_dir(deb_dir)
        self.facade.reload_channels()
        self.assertEqual(
            ["name1", "name2", "name3"],
            sorted(version.package.name
                   for version in self.facade.get_packages()))

    def test_get_channels_with_no_channels(self):
        """
        If no deb URLs have been added, C{get_channels()} returns an
        empty list.
        """
        self.assertEqual([], self.facade.get_channels())

    def test_get_channels_with_channels(self):
        """
        If deb URLs have been added, a list of dict is returned with
        information about the channels.
        """
        self.facade.add_channel_apt_deb(
            "http://example.com/ubuntu", "lucid", ["main", "restricted"])
        self.assertEqual([{"baseurl": "http://example.com/ubuntu",
                           "distribution": "lucid",
                           "components": "main restricted",
                           "type": "deb"}],
                         self.facade.get_channels())

    def test_get_channels_with_disabled_channels(self):
        """
        C{get_channels()} doesn't return disabled deb URLs.
        """
        self.facade.add_channel_apt_deb(
            "http://enabled.example.com/ubuntu", "lucid", ["main"])
        self.facade.add_channel_apt_deb(
            "http://disabled.example.com/ubuntu", "lucid", ["main"])
        sources_list = SourcesList()
        for entry in sources_list:
            if "disabled" in entry.uri:
                entry.set_enabled(False)
        sources_list.save()
        self.assertEqual([{"baseurl": "http://enabled.example.com/ubuntu",
                           "distribution": "lucid",
                           "components": "main",
                           "type": "deb"}],
                         self.facade.get_channels())

    def test_reset_channels(self):
        """
        C{reset_channels()} disables all the configured deb URLs.
        """
        self.facade.add_channel_apt_deb(
            "http://1.example.com/ubuntu", "lucid", ["main", "restricted"])
        self.facade.add_channel_apt_deb(
            "http://2.example.com/ubuntu", "lucid", ["main", "restricted"])
        self.facade.reset_channels()
        self.assertEqual([], self.facade.get_channels())

    def test_reload_includes_added_channels(self):
        """
        When reloading the channels, C{get_packages()} returns the packages
        in the channel.
        """
        deb_dir = self.makeDir()
        self._add_package_to_deb_dir(deb_dir, "foo")
        self._add_package_to_deb_dir(deb_dir, "bar")
        self.facade.add_channel_apt_deb("file://%s" % deb_dir, "./")
        self.facade.reload_channels()
        self.assertEqual(
            ["bar", "foo"],
            sorted(version.package.name
                   for version in self.facade.get_packages()))

    def test_reload_channels_refetch_package_index(self):
        """
        If C{refetch_package_index} is True, reload_channels will
        refetch the Packages files in the channels and rebuild the
        internal database.
        """
        deb_dir = self.makeDir()
        self._add_package_to_deb_dir(deb_dir, "foo")
        self.facade.add_channel_apt_deb("file://%s" % deb_dir, "./")
        self.facade.reload_channels()
        new_facade = AptFacade(root=self.apt_root)
        self._add_package_to_deb_dir(deb_dir, "bar")
        self._touch_packages_file(deb_dir)
        new_facade.refetch_package_index = True
        new_facade.reload_channels()
        self.assertEqual(
            ["bar", "foo"],
            sorted(version.package.name
                   for version in new_facade.get_packages()))

    def test_reload_channels_not_refetch_package_index(self):
        """
        If C{refetch_package_index} is False, reload_channels won't
        refetch the Packages files in the channels, and instead simply
        use the internal database that is already there.
        """
        deb_dir = self.makeDir()
        self._add_package_to_deb_dir(deb_dir, "foo")
        self.facade.add_channel_apt_deb("file://%s" % deb_dir, "./")
        self.facade.reload_channels()
        new_facade = AptFacade(root=self.apt_root)
        self._add_package_to_deb_dir(deb_dir, "bar")
        self._touch_packages_file(deb_dir)
        new_facade.refetch_package_index = False
        new_facade.reload_channels()
        self.assertEqual(
            ["foo"],
            sorted(version.package.name
                   for version in new_facade.get_packages()))

    def test_dont_refetch_package_index_by_default(self):
        """
        By default, package indexes are not refetched, but the local
        database is used.
        """
        new_facade = AptFacade(root=self.apt_root)
        self.assertFalse(new_facade.refetch_package_index)

    def test_ensure_channels_reloaded_do_not_reload_twice(self):
        """
        C{ensure_channels_reloaded} refreshes the channels only when
        first called. If it's called more time, it has no effect.
        """
        self._add_system_package("foo")
        self.facade.ensure_channels_reloaded()
        self.assertEqual(
            ["foo"],
            sorted(version.package.name
                   for version in self.facade.get_packages()))
        self._add_system_package("bar")
        self.facade.ensure_channels_reloaded()
        self.assertEqual(
            ["foo"],
            sorted(version.package.name
                   for version in self.facade.get_packages()))

    def test_reload_channels_with_channel_error(self):
        """
        The C{reload_channels} method raises a L{ChannelsError} if
        apt fails to load the configured channels.
        """
        self.facade.add_channel_apt_deb("non-proto://fail.url", "./")
        self.assertRaises(ChannelError, self.facade.reload_channels)

    def test_get_set_arch(self):
        """
        C{get_arch} returns the architecture that APT is currently
        configured to use. C{set_arch} is used to set the architecture
        that APT should use.
        """
        self.facade.set_arch("amd64")
        self.assertEqual("amd64", self.facade.get_arch())
        self.facade.set_arch("i386")
        self.assertEqual("i386", self.facade.get_arch())

    def test_get_set_arch_none(self):
        """
        If C{None} is passed to C{set_arch()}, the architecture is set
        to "", since it can't be set to C{None}. This is to ensure
        compatibility with C{SmartFacade}, and the architecture should
        be set to C{None} in tests only.
        """
        self.facade.set_arch(None)
        self.assertEqual("", self.facade.get_arch())

    def test_set_arch_get_packages(self):
        """
        After the architecture is set, APT really uses the value.
        """
        self._add_system_package("i386-package", architecture="i386")
        self._add_system_package("amd64-package", architecture="amd64")
        self.facade.set_arch("i386")
        self.facade.reload_channels()
        self.assertEqual(
            ["i386-package"],
            sorted(version.package.name
                   for version in self.facade.get_packages()))
        self.facade.set_arch("amd64")
        self.facade.reload_channels()
        self.assertEqual(
            ["amd64-package"],
            sorted(version.package.name
                   for version in self.facade.get_packages()))

    def test_get_package_skeleton(self):
        """
        C{get_package_skeleton} returns a C{PackageSkeleton} for a
        package. By default extra information is included, but it's
        possible to specify that only basic information should be
        included.

        The information about the package are unicode strings.
        """
        deb_dir = self.makeDir()
        create_simple_repository(deb_dir)
        self.facade.add_channel_deb_dir(deb_dir)
        self.facade.reload_channels()
        [pkg1] = self.facade.get_packages_by_name("name1")
        [pkg2] = self.facade.get_packages_by_name("name2")
        skeleton1 = self.facade.get_package_skeleton(pkg1)
        self.assertTrue(isinstance(skeleton1.summary, unicode))
        self.assertEqual("Summary1", skeleton1.summary)
        skeleton2 = self.facade.get_package_skeleton(pkg2, with_info=False)
        self.assertIs(None, skeleton2.summary)
        self.assertEqual(HASH1, skeleton1.get_hash())
        self.assertEqual(HASH2, skeleton2.get_hash())

    def test_get_package_hash(self):
        """
        C{get_package_hash} returns the hash for a given package.
        """
        deb_dir = self.makeDir()
        create_simple_repository(deb_dir)
        self.facade.add_channel_deb_dir(deb_dir)
        self.facade.reload_channels()
        [pkg] = self.facade.get_packages_by_name("name1")
        self.assertEqual(HASH1, self.facade.get_package_hash(pkg))
        [pkg] = self.facade.get_packages_by_name("name2")
        self.assertEqual(HASH2, self.facade.get_package_hash(pkg))

    def test_get_package_hashes(self):
        """
        C{get_package_hashes} returns the hashes for all packages in the
        channels.
        """
        deb_dir = self.makeDir()
        create_simple_repository(deb_dir)
        self.facade.add_channel_deb_dir(deb_dir)
        self.facade.reload_channels()
        hashes = self.facade.get_package_hashes()
        self.assertEqual(sorted(hashes), sorted([HASH1, HASH2, HASH3]))

    def test_get_package_by_hash(self):
        """
        C{get_package_by_hash} returns the package that has the given hash.
        """
        deb_dir = self.makeDir()
        create_simple_repository(deb_dir)
        self.facade.add_channel_deb_dir(deb_dir)
        self.facade.reload_channels()
        version = self.facade.get_package_by_hash(HASH1)
        self.assertEqual(version.package.name, "name1")
        version = self.facade.get_package_by_hash(HASH2)
        self.assertEqual(version.package.name, "name2")
        version = self.facade.get_package_by_hash("none")
        self.assertEqual(version, None)

    def test_wb_reload_channels_clears_hash_cache(self):
        """
        To improve performance, the hashes for the packages are cached.
        When reloading the channels, the cache is recreated.
        """
        # Load hashes.
        deb_dir = self.makeDir()
        create_simple_repository(deb_dir)
        self.facade.add_channel_deb_dir(deb_dir)
        self.facade.reload_channels()

        # Hold a reference to packages.
        [pkg1] = self.facade.get_packages_by_name("name1")
        [pkg2] = self.facade.get_packages_by_name("name2")
        [pkg3] = self.facade.get_packages_by_name("name3")
        self.assertTrue(pkg1 and pkg2)

        # Remove the package from the repository.
        packages_path = os.path.join(deb_dir, "Packages")
        os.unlink(os.path.join(deb_dir, PKGNAME1))
        os.unlink(packages_path)
        self.facade._create_packages_file(deb_dir)
        # Forcibly change the mtime of our repository's Packages file,
        # so that apt will consider it as changed (if the change is
        # inside the same second the Packages' mtime will be the same)
        self._touch_packages_file(deb_dir)

        # Reload channel to reload the cache.
        self.facade.reload_channels()

        # Only packages with name2 and name3 should be loaded, and they're
        # not the same objects anymore.
        self.assertEqual(
            sorted([version.package.name
                    for version in self.facade.get_packages()]),
            ["name2", "name3"])
        self.assertNotEquals(
            set(version.package for version in self.facade.get_packages()),
            set([pkg2.package, pkg3.package]))

        # The hash cache shouldn't include either of the old packages.
        self.assertEqual(self.facade.get_package_hash(pkg1), None)
        self.assertEqual(self.facade.get_package_hash(pkg2), None)
        self.assertEqual(self.facade.get_package_hash(pkg3), None)

        # Also, the hash for package1 shouldn't be present at all.
        self.assertEqual(self.facade.get_package_by_hash(HASH1), None)

        # While HASH2 and HASH3 should point to the new packages. We
        # look at the Package object instead of the Version objects,
        # since different Version objects may appear to be the same
        # object.
        new_pkgs = [version.package for version in self.facade.get_packages()]
        self.assertTrue(
            self.facade.get_package_by_hash(HASH2).package in new_pkgs)
        self.assertTrue(
            self.facade.get_package_by_hash(HASH3).package in new_pkgs)

        # Which are not the old packages.
        self.assertFalse(pkg2.package in new_pkgs)
        self.assertFalse(pkg3.package in new_pkgs)

    def test_is_package_installed_in_channel_not_installed(self):
        """
        If a package is in a channel, but not installed, it's not
        considered installed.
        """
        deb_dir = self.makeDir()
        create_simple_repository(deb_dir)
        self.facade.add_channel_deb_dir(deb_dir)
        self.facade.reload_channels()
        [package] = self.facade.get_packages_by_name("name1")
        self.assertFalse(self.facade.is_package_installed(package))

    def test_is_package_installed_in_channel_installed(self):
        """
        If a package is in a channel and installed, it's considered
        installed.
        """
        deb_dir = self.makeDir()
        create_simple_repository(deb_dir)
        self.facade.add_channel_deb_dir(deb_dir)
        self._install_deb_file(os.path.join(deb_dir, PKGNAME1))
        self.facade.reload_channels()
        [package] = self.facade.get_packages_by_name("name1")
        self.assertTrue(self.facade.is_package_installed(package))

    def test_is_package_installed_other_verion_in_channel(self):
        """
        If the there are other versions in the channels, only the
        installed version of thepackage is considered installed.
        """
        deb_dir = self.makeDir()
        create_simple_repository(deb_dir)
        self.facade.add_channel_deb_dir(deb_dir)
        self._add_package_to_deb_dir(
            deb_dir, "name1", version="version0-release0")
        self._add_package_to_deb_dir(
            deb_dir, "name1", version="version2-release2")
        self._install_deb_file(os.path.join(deb_dir, PKGNAME1))
        self.facade.reload_channels()
        [version0, version1, version2] = sorted(
            self.facade.get_packages_by_name("name1"))
        self.assertEqual("version0-release0", version0.version)
        self.assertFalse(self.facade.is_package_installed(version0))
        self.assertEqual("version1-release1", version1.version)
        self.assertTrue(self.facade.is_package_installed(version1))
        self.assertEqual("version2-release2", version2.version)
        self.assertFalse(self.facade.is_package_installed(version2))

    def test_is_package_available_in_channel_not_installed(self):
        """
        A package is considered available if the package is in a
        configured channel and not installed.
        """
        deb_dir = self.makeDir()
        create_simple_repository(deb_dir)
        self.facade.add_channel_deb_dir(deb_dir)
        self.facade.reload_channels()
        [package] = self.facade.get_packages_by_name("name1")
        self.assertTrue(self.facade.is_package_available(package))

    def test_is_package_available_not_in_channel_installed(self):
        """
        A package is not considered available if the package is
        installed and not in a configured channel.
        """
        deb_dir = self.makeDir()
        create_simple_repository(deb_dir)
        self._install_deb_file(os.path.join(deb_dir, PKGNAME1))
        self.facade.reload_channels()
        [package] = self.facade.get_packages_by_name("name1")
        self.assertFalse(self.facade.is_package_available(package))

    def test_is_package_available_in_channel_installed(self):
        """
        A package is considered available if the package is
        installed and is in a configured channel.
        """
        deb_dir = self.makeDir()
        create_simple_repository(deb_dir)
        self._install_deb_file(os.path.join(deb_dir, PKGNAME1))
        self.facade.add_channel_deb_dir(deb_dir)
        self.facade.reload_channels()
        [package] = self.facade.get_packages_by_name("name1")
        self.assertTrue(self.facade.is_package_available(package))

    def test_is_package_upgrade_in_channel_not_installed(self):
        """
        A package is not consider an upgrade of no version of it is
        installed.
        """
        deb_dir = self.makeDir()
        self._add_package_to_deb_dir(deb_dir, "foo", version="1.0")
        self.facade.add_channel_apt_deb("file://%s" % deb_dir, "./")
        self.facade.reload_channels()
        [package] = self.facade.get_packages()
        self.assertFalse(self.facade.is_package_upgrade(package))

    def test_is_package_upgrade_in_channel_older_installed(self):
        """
        A package is considered to be an upgrade if some channel has a
        newer version than the installed one.
        """
        deb_dir = self.makeDir()
        self._add_system_package("foo", version="0.5")
        self._add_package_to_deb_dir(deb_dir, "foo", version="1.0")
        self.facade.add_channel_apt_deb("file://%s" % deb_dir, "./")
        self.facade.reload_channels()
        [version_05, version_10] = sorted(self.facade.get_packages())
        self.assertTrue(self.facade.is_package_upgrade(version_10))
        self.assertFalse(self.facade.is_package_upgrade(version_05))

    def test_is_package_upgrade_in_channel_newer_installed(self):
        """
        A package is not considered to be an upgrade if there are only
        older versions than the installed one in the channels.
        """
        deb_dir = self.makeDir()
        self._add_system_package("foo", version="1.5")
        self._add_package_to_deb_dir(deb_dir, "foo", version="1.0")
        self.facade.add_channel_apt_deb("file://%s" % deb_dir, "./")
        self.facade.reload_channels()
        [version_10, version_15] = sorted(self.facade.get_packages())
        self.assertFalse(self.facade.is_package_upgrade(version_10))
        self.assertFalse(self.facade.is_package_upgrade(version_15))

    def test_is_package_upgrade_in_channel_same_as_installed(self):
        """
        A package is not considered to be an upgrade if the newest
        version of the packages available in the channels is the same as
        the installed one.
        """
        deb_dir = self.makeDir()
        self._add_system_package("foo", version="1.0")
        self._add_package_to_deb_dir(deb_dir, "foo", version="1.0")
        self.facade.add_channel_apt_deb("file://%s" % deb_dir, "./")
        self.facade.reload_channels()
        [package] = self.facade.get_packages()
        self.assertFalse(self.facade.is_package_upgrade(package))

    def test_is_package_upgrade_not_in_channel_installed(self):
        """
        A package is not considered to be an upgrade if the package is
        installed but not available in any of the configured channels.
        """
        self._add_system_package("foo", version="1.0")
        self.facade.reload_channels()
        [package] = self.facade.get_packages()
        self.assertFalse(self.facade.is_package_upgrade(package))

    def test_get_packages_by_name_no_match(self):
        """
        If there are no packages with the given name,
        C{get_packages_by_name} returns an empty list.
        """
        self._add_system_package("foo", version="1.0")
        self.facade.reload_channels()
        self.assertEqual([], self.facade.get_packages_by_name("bar"))

    def test_get_packages_by_name_match(self):
        """
        C{get_packages_by_name} returns all the packages in the
        available channels that have the specified name.
        """
        deb_dir = self.makeDir()
        self._add_system_package("foo", version="1.0")
        self._add_package_to_deb_dir(deb_dir, "foo", version="1.5")
        self.facade.add_channel_apt_deb("file://%s" % deb_dir, "./")
        self.facade.reload_channels()
        self.assertEqual(
            [("foo", "1.0"), ("foo", "1.5")],
            sorted([(version.package.name, version.version)
                    for version in self.facade.get_packages_by_name("foo")]))

    def test_perform_changes_with_nothing_to_do(self):
        """
        perform_changes() should return None when there's nothing to do.
        """
        self.facade.reload_channels()
        self.assertEqual(self.facade.perform_changes(), None)

    def test_perform_changes_fetch_progress(self):
        """
        C{perform_changes()} captures the fetch output and returns it.
        """
        deb_dir = self.makeDir()
        self._add_package_to_deb_dir(deb_dir, "foo")
        self.facade.add_channel_apt_deb("file://%s" % deb_dir, "./")
        self.facade.reload_channels()
        foo = self.facade.get_packages_by_name("foo")[0]
        self.facade.mark_install(foo)
        fetch_item = FakeFetchItem(
            FakeOwner(1234, error_text="Some error"), "foo package")

        def commit(fetch_progress):
            fetch_progress.start()
            fetch_progress.fetch(fetch_item)
            fetch_progress.fail(fetch_item)
            fetch_progress.done(fetch_item)
            fetch_progress.stop()

        self.facade._cache.commit = commit
        output = [
            line.rstrip()
            for line in self.facade.perform_changes().splitlines()
            if line.strip()]
        # Don't do a plain comparision of the output, since the output
        # in Lucid is slightly different.
        self.assertEqual(4, len(output))
        self.assertTrue(output[0].startswith("Get:1 foo package"))
        self.assertEqual(
            ["Err foo package", "  Some error"], output[1:3])
        self.assertTrue(output[3].startswith("Fetched "))

    def test_perform_changes_dpkg_output(self):
        """
        C{perform_changes()} captures the dpkg output and returns it.
        """
        deb_dir = self.makeDir()
        self._add_package_to_deb_dir(deb_dir, "foo")
        self.facade.add_channel_apt_deb("file://%s" % deb_dir, "./")
        self.facade.reload_channels()
        foo = self.facade.get_packages_by_name("foo")[0]
        self.facade.mark_install(foo)

        def commit(fetch_progress):
            os.write(1, "Stdout output\n")
            os.write(2, "Stderr output\n")
            os.write(1, "Stdout output again\n")

        self.facade._cache.commit = commit
        output = [
            line.rstrip()
            for line in self.facade.perform_changes().splitlines()
            if line.strip()]
        self.assertEqual(
            ["Stdout output", "Stderr output", "Stdout output again"], output)

    def test_perform_changes_dpkg_output_error(self):
        """
        C{perform_changes()} captures the dpkg output and includes it in
        the exception message, if committing the cache fails.
        """
        deb_dir = self.makeDir()
        self._add_package_to_deb_dir(deb_dir, "foo")
        self.facade.add_channel_apt_deb("file://%s" % deb_dir, "./")
        self.facade.reload_channels()
        foo = self.facade.get_packages_by_name("foo")[0]
        self.facade.mark_install(foo)

        def commit(fetch_progress):
            os.write(1, "Stdout output\n")
            os.write(2, "Stderr output\n")
            os.write(1, "Stdout output again\n")
            raise SystemError("Oops")

        self.facade._cache.commit = commit
        exception = self.assertRaises(
            TransactionError, self.facade.perform_changes)
        output = [
            line.rstrip()
            for line in exception.args[0].splitlines()if line.strip()]
        self.assertEqual(
            ["Oops", "Package operation log:", "Stdout output",
             "Stderr output", "Stdout output again"],
            output)

    def test_perform_changes_install_broken_includes_error_info(self):
        """
        """
        deb_dir = self.makeDir()
        self._add_package_to_deb_dir(
            deb_dir, "foo", control_fields={"Depends": "bar"})
        self.facade.add_channel_apt_deb("file://%s" % deb_dir, "./")
        self.facade.reload_channels()
        [foo] = self.facade.get_packages_by_name("foo")
        self.facade.mark_install(foo)
        self.facade._cache.commit = lambda fetch_progress: None
        error = self.assertRaises(
            TransactionError, self.facade.perform_changes)
        self.assertIn("you have held broken packages", error.args[0])
        self.assertIn(
            "The following packages have unmet dependencies:\n" +
            "  foo",
            error.args[0])

    def test_get_unmet_dependency_info_no_broken(self):
        """
        """
        deb_dir = self.makeDir()
        self._add_package_to_deb_dir(
            deb_dir, "foo", control_fields={"Depends": "bar"})
        self.facade.add_channel_apt_deb("file://%s" % deb_dir, "./")
        self.facade.reload_channels()
        self.assertEqual(set(), self.facade._get_broken_packages())
        self.assertEqual("", self.facade._get_unmet_dependency_info())

    def test_get_unmet_dependency_info_simple(self):
        """
        """
        deb_dir = self.makeDir()
        self._add_package_to_deb_dir(
            deb_dir, "foo", control_fields={"Depends": "bar"})
        self.facade.add_channel_apt_deb("file://%s" % deb_dir, "./")
        self.facade.reload_channels()
        [foo] = self.facade.get_packages_by_name("foo")
        foo.package.mark_install(auto_fix=False)
        self.assertEqual(
            set([foo.package]), self.facade._get_broken_packages())
        self.assertEqual(
            ["The following packages have unmet dependencies:",
             "  foo"],
            self.facade._get_unmet_dependency_info().splitlines())

    def test_get_unmet_dependency_info_multiple(self):
        """
        """
        deb_dir = self.makeDir()
        self._add_package_to_deb_dir(
            deb_dir, "foo", control_fields={"Depends": "bar"})
        self._add_package_to_deb_dir(
            deb_dir, "another-foo", control_fields={"Depends": "another-bar"})
        self.facade.add_channel_apt_deb("file://%s" % deb_dir, "./")
        self.facade.reload_channels()
        [foo] = self.facade.get_packages_by_name("foo")
        [another_foo] = self.facade.get_packages_by_name("another-foo")
        foo.package.mark_install(auto_fix=False)
        another_foo.package.mark_install(auto_fix=False)
        self.assertEqual(
            set([foo.package, another_foo.package]),
            self.facade._get_broken_packages())
        self.assertEqual(
            ["The following packages have unmet dependencies:",
             "  another-foo",
             "  foo"],
            self.facade._get_unmet_dependency_info().splitlines())

    def _mock_output_restore(self):
        """
        Mock methods to ensure that stdout and stderr are restored,
        after they have been captured.

        Return the path to the tempfile that was used to capture the output.
        """
        old_stdout = os.dup(1)
        old_stderr = os.dup(2)
        fd, outfile = tempfile.mkstemp()
        mkstemp = self.mocker.replace("tempfile.mkstemp")
        mkstemp()
        self.mocker.result((fd, outfile))
        dup = self.mocker.replace("os.dup")
        dup(1)
        self.mocker.result(old_stdout)
        dup(2)
        self.mocker.result(old_stderr)
        dup2 = self.mocker.replace("os.dup2")
        dup2(old_stdout, 1)
        self.mocker.passthrough()
        dup2(old_stderr, 2)
        self.mocker.passthrough()
        return outfile

    def test_perform_changes_dpkg_output_reset(self):
        """
        C{perform_changes()} resets stdout and stderr after the cache commit.
        """
        deb_dir = self.makeDir()
        self._add_package_to_deb_dir(deb_dir, "foo")
        self.facade.add_channel_apt_deb("file://%s" % deb_dir, "./")
        self.facade.reload_channels()
        foo = self.facade.get_packages_by_name("foo")[0]
        self.facade.mark_install(foo)

        outfile = self._mock_output_restore()
        self.mocker.replay()
        self.facade._cache.commit = lambda fetch_progress: None
        self.facade.perform_changes()
        # Make sure we don't leave the tempfile behind.
        self.assertFalse(os.path.exists(outfile))

    def test_perform_changes_dpkg_output_reset_error(self):
        """
        C{perform_changes()} resets stdout and stderr after the cache
        commit, even if commit raises an error.
        """
        deb_dir = self.makeDir()
        self._add_package_to_deb_dir(deb_dir, "foo")
        self.facade.add_channel_apt_deb("file://%s" % deb_dir, "./")
        self.facade.reload_channels()
        foo = self.facade.get_packages_by_name("foo")[0]
        self.facade.mark_install(foo)

        outfile = self._mock_output_restore()
        self.mocker.replay()

        def commit(fetch_progress):
            raise SystemError("Error")

        self.facade._cache.commit = commit
        self.assertRaises(TransactionError, self.facade.perform_changes)
        # Make sure we don't leave the tempfile behind.
        self.assertFalse(os.path.exists(outfile))

    def test_reset_marks(self):
        """
        C{reset_marks()} clears things, so that there's nothing to do
        for C{perform_changes()}
        """
        deb_dir = self.makeDir()
        self._add_package_to_deb_dir(deb_dir, "foo")
        self._add_system_package("bar", version="1.0")
        self._add_package_to_deb_dir(deb_dir, "bar", version="1.5")
        self._add_system_package("baz")
        self.facade.add_channel_apt_deb("file://%s" % deb_dir, "./")
        self.facade.reload_channels()
        foo = self.facade.get_packages_by_name("foo")[0]
        self.facade.mark_install(foo)
        self.facade.mark_global_upgrade()
        [baz] = self.facade.get_packages_by_name("baz")
        self.facade.mark_remove(baz)
        self.facade.reset_marks()
        self.assertEqual(self.facade._version_installs, [])
        self.assertEqual(self.facade._version_removals, [])
        self.assertFalse(self.facade._global_upgrade)
        self.assertEqual(self.facade.perform_changes(), None)

    def test_wb_mark_install_adds_to_list(self):
        """
        C{mark_install} adds the package to the list of packages to be
        installed.
        """
        deb_dir = self.makeDir()
        create_deb(deb_dir, PKGNAME_MINIMAL, PKGDEB_MINIMAL)
        self.facade.add_channel_deb_dir(deb_dir)
        self.facade.reload_channels()
        pkg = self.facade.get_packages_by_name("minimal")[0]
        self.facade.mark_install(pkg)
        self.assertEqual(1, len(self.facade._version_installs))
        install = self.facade._version_installs[0]
        self.assertEqual("minimal", install.package.name)

    def test_wb_mark_global_upgrade_sets_variable(self):
        """
        C{mark_global_upgrade} sets a variable, so that the actual
        upgrade happens in C{perform_changes}.
        """
        deb_dir = self.makeDir()
        self._add_system_package("foo", version="1.0")
        self._add_package_to_deb_dir(deb_dir, "foo", version="1.5")
        self.facade.add_channel_apt_deb("file://%s" % deb_dir, "./")
        self.facade.reload_channels()
        foo_10 = sorted(self.facade.get_packages_by_name("foo"))[0]
        self.facade.mark_global_upgrade()
        self.assertTrue(self.facade._global_upgrade)
        self.assertEqual(foo_10, foo_10.package.installed)

    def test_wb_mark_remove_adds_to_list(self):
        """
        C{mark_remove} adds the package to the list of packages to be
        removed.
        """
        self._add_system_package("foo")
        self.facade.reload_channels()
        [foo] = self.facade.get_packages_by_name("foo")
        self.facade.mark_remove(foo)
        self.assertEqual([foo], self.facade._version_removals)

    def test_mark_install_specific_version(self):
        """
        If more than one version is available, the version passed to
        C{mark_install} is marked as the candidate version, so that gets
        installed.
        """
        deb_dir = self.makeDir()
        self._add_package_to_deb_dir(deb_dir, "foo", version="1.0")
        self._add_package_to_deb_dir(deb_dir, "foo", version="2.0")
        self.facade.add_channel_apt_deb("file://%s" % deb_dir, "./")
        self.facade.reload_channels()
        foo1, foo2 = sorted(self.facade.get_packages_by_name("foo"))
        self.assertEqual(foo2, foo1.package.candidate)
        self.facade.mark_install(foo1)
        self.facade._cache.commit = lambda fetch_progress: None
        self.facade.perform_changes()
        self.assertEqual(foo1, foo1.package.candidate)

    def test_wb_mark_install_upgrade_non_main_arch(self):
        """
        If C{mark_install} is used to upgrade a package, its non-main
        architecture version of the package will be upgraded as well, if
        it is installed.
        """
        apt_pkg.config.clear("APT::Architectures")
        apt_pkg.config.set("APT::Architecture", "amd64")
        apt_pkg.config.set("APT::Architectures::", "amd64")
        apt_pkg.config.set("APT::Architectures::", "i386")
        deb_dir = self.makeDir()
        self._add_system_package(
            "multi-arch", architecture="amd64", version="1.0",
            control_fields={"Multi-Arch": "same"})
        self._add_system_package(
            "multi-arch", architecture="i386", version="1.0",
            control_fields={"Multi-Arch": "same"})
        self._add_system_package(
            "single-arch", architecture="amd64", version="1.0")
        self._add_package_to_deb_dir(
            deb_dir, "multi-arch", architecture="amd64", version="2.0",
            control_fields={"Multi-Arch": "same"})
        self._add_package_to_deb_dir(
            deb_dir, "multi-arch", architecture="i386", version="2.0",
            control_fields={"Multi-Arch": "same"})
        self._add_package_to_deb_dir(
            deb_dir, "single-arch", architecture="amd64", version="2.0")
        self._add_package_to_deb_dir(
            deb_dir, "single-arch", architecture="i386", version="2.0")
        self.facade.add_channel_apt_deb("file://%s" % deb_dir, "./")
        self.facade.reload_channels()

        multi_arch1, multi_arch2 = sorted(
            self.facade.get_packages_by_name("multi-arch"))
        single_arch1, single_arch2 = sorted(
            self.facade.get_packages_by_name("single-arch"))
        self.facade.mark_remove(multi_arch1)
        self.facade.mark_install(multi_arch2)
        self.facade.mark_remove(single_arch1)
        self.facade.mark_install(single_arch2)
        self.facade._cache.commit = lambda fetch_progress: None
        self.facade.perform_changes()
        changes = [
            (pkg.name, pkg.candidate.version, pkg.marked_upgrade)
            for pkg in self.facade._cache.get_changes()]
        self.assertEqual(
            [("multi-arch", "2.0", True), ("multi-arch:i386", "2.0", True),
             ("single-arch", "2.0", True)],
            sorted(changes))

    def test_wb_mark_install_upgrade_non_main_arch_dependency_error(self):
        """
        If a non-main architecture is automatically upgraded, and the
        main architecture versions hasn't been marked for installation,
        only the main architecture version is included in the
        C{DependencyError}.
        """
        apt_pkg.config.clear("APT::Architectures")
        apt_pkg.config.set("APT::Architecture", "amd64")
        apt_pkg.config.set("APT::Architectures::", "amd64")
        apt_pkg.config.set("APT::Architectures::", "i386")
        deb_dir = self.makeDir()
        self._add_system_package(
            "multi-arch", architecture="amd64", version="1.0",
            control_fields={"Multi-Arch": "same"})
        self._add_system_package(
            "multi-arch", architecture="i386", version="1.0",
            control_fields={"Multi-Arch": "same"})
        self._add_package_to_deb_dir(
            deb_dir, "multi-arch", architecture="amd64", version="2.0",
            control_fields={"Multi-Arch": "same"})
        self._add_package_to_deb_dir(
            deb_dir, "multi-arch", architecture="i386", version="2.0",
            control_fields={"Multi-Arch": "same"})
        self.facade.add_channel_apt_deb("file://%s" % deb_dir, "./")
        self.facade.reload_channels()

        multi_arch1, multi_arch2 = sorted(
            self.facade.get_packages_by_name("multi-arch"))
        self.facade.mark_global_upgrade()
        self.facade._cache.commit = lambda fetch_progress: None
        exception = self.assertRaises(
            DependencyError, self.facade.perform_changes)
        self.assertEqual(
            sorted([multi_arch1, multi_arch2]), sorted(exception.packages))
        changes = [
            (pkg.name, pkg.candidate.version)
            for pkg in self.facade._cache.get_changes()]
        self.assertEqual(
            [("multi-arch", "2.0"), ("multi-arch:i386", "2.0")],
            sorted(changes))

    def test_mark_global_upgrade(self):
        """
        C{mark_global_upgrade} upgrades all packages that can be
        upgraded. It makes C{perform_changes} raise a C{DependencyError}
        with the required changes, so that the user can review the
        changes and approve them.
        """
        deb_dir = self.makeDir()
        self._add_system_package("foo", version="1.0")
        self._add_system_package("bar")
        self._add_package_to_deb_dir(deb_dir, "foo", version="2.0")
        self._add_package_to_deb_dir(deb_dir, "baz")
        self.facade.add_channel_apt_deb("file://%s" % deb_dir, "./")
        self.facade.reload_channels()
        foo1, foo2 = sorted(self.facade.get_packages_by_name("foo"))
        self.facade.mark_global_upgrade()
        exception = self.assertRaises(
            DependencyError, self.facade.perform_changes)
        self.assertEqual(set([foo1, foo2]), set(exception.packages))

    def test_mark_global_upgrade_candidate_version(self):
        """
        If more than one version is available, the package will be
        upgraded to the candidate version. Since the user didn't request
        from and to which version to upgrade to, a DependencyError error
        will be raised, so that the changes can be reviewed and
        approved.
        """
        deb_dir = self.makeDir()
        self._add_system_package("foo", version="1.0")
        self._add_package_to_deb_dir(deb_dir, "foo", version="2.0")
        self._add_package_to_deb_dir(deb_dir, "foo", version="3.0")
        self.facade.add_channel_apt_deb("file://%s" % deb_dir, "./")
        self.facade.reload_channels()
        foo1, foo2, foo3 = sorted(self.facade.get_packages_by_name("foo"))
        self.assertEqual(foo3, foo1.package.candidate)
        self.facade.mark_global_upgrade()
        exception = self.assertRaises(
            DependencyError, self.facade.perform_changes)
        self.assertEqual(set([foo1, foo3]), set(exception.packages))

    def test_mark_global_upgrade_no_upgrade(self):
        """
        If the candidate version of a package is already installed,
        C{mark_global_upgrade()} won't request an upgrade to be made. I.e.
        C{perform_changes()} won't do anything.
        """
        deb_dir = self.makeDir()
        self._add_system_package("foo", version="3.0")
        self._add_package_to_deb_dir(deb_dir, "foo", version="2.0")
        self._add_package_to_deb_dir(deb_dir, "foo", version="1.0")
        self.facade.add_channel_apt_deb("file://%s" % deb_dir, "./")
        self.facade.reload_channels()
        foo3 = sorted(self.facade.get_packages_by_name("foo"))[-1]
        self.assertEqual(foo3, foo3.package.candidate)
        self.facade.mark_global_upgrade()
        self.assertEqual(None, self.facade.perform_changes())

    def test_mark_global_upgrade_preserves_auto(self):
        """
        Upgrading a package will retain its auto-install status.
        """
        deb_dir = self.makeDir()
        self._add_system_package("auto", version="1.0")
        self._add_package_to_deb_dir(deb_dir, "auto", version="2.0")
        self._add_system_package("noauto", version="1.0")
        self._add_package_to_deb_dir(deb_dir, "noauto", version="2.0")
        self.facade.add_channel_apt_deb("file://%s" % deb_dir, "./")
        self.facade.reload_channels()
        auto1, auto2 = sorted(self.facade.get_packages_by_name("auto"))
        noauto1, noauto2 = sorted(self.facade.get_packages_by_name("noauto"))
        auto1.package.mark_auto(True)
        noauto1.package.mark_auto(False)
        self.facade.mark_global_upgrade()
        self.assertRaises(DependencyError, self.facade.perform_changes)
        self.assertTrue(auto2.package.is_auto_installed)
        self.assertFalse(noauto2.package.is_auto_installed)

    def test_wb_perform_changes_commits_changes(self):
        """
        When calling C{perform_changes}, it will commit the cache, to
        cause all package changes to happen.
        """
        committed = []

        def commit(fetch_progress):
            committed.append(True)

        deb_dir = self.makeDir()
        create_deb(deb_dir, PKGNAME_MINIMAL, PKGDEB_MINIMAL)
        self.facade.add_channel_deb_dir(deb_dir)
        self.facade.reload_channels()
        pkg = self.facade.get_packages_by_name("minimal")[0]
        self.facade.mark_install(pkg)
        self.facade._cache.commit = commit
        self.committed = False
        self.facade.perform_changes()
        self.assertEqual([True], committed)

    def test_perform_changes_return_non_none(self):
        """
        When calling C{perform_changes} with changes to do, it will
        return a string.
        """
        deb_dir = self.makeDir()
        create_deb(deb_dir, PKGNAME_MINIMAL, PKGDEB_MINIMAL)
        self.facade.add_channel_deb_dir(deb_dir)
        self.facade.reload_channels()
        pkg = self.facade.get_packages_by_name("minimal")[0]
        self.facade.mark_install(pkg)
        self.facade._cache.commit = lambda fetch_progress: None
        # An empty string is returned, since we don't call the progress
        # objects, which are the ones that build the output string.
        self.assertEqual("", self.facade.perform_changes())

    def test_perform_changes_with_broken_packages_install_simple(self):
        """
        Even if some installed packages are broken in the system, it's
        still possible to install packages with no dependencies that
        don't touch the broken ones.
        """
        deb_dir = self.makeDir()
        self._add_system_package(
            "broken", control_fields={"Depends": "missing"})
        self._add_package_to_deb_dir(deb_dir, "foo")
        self._add_package_to_deb_dir(deb_dir, "missing")
        self.facade.add_channel_apt_deb("file://%s" % deb_dir, "./")
        self.facade.reload_channels()
        [foo] = self.facade.get_packages_by_name("foo")
        self.facade.mark_install(foo)
        self.facade._cache.commit = lambda fetch_progress: None
        self.assertEqual("", self.facade.perform_changes())
        self.assertEqual(
            [foo.package], self.facade._cache.get_changes())

    def test_perform_changes_with_broken_packages_install_deps(self):
        """
        Even if some installed packages are broken in the system, it's
        still possible to install packages where the dependencies need
        to be calculated.
        """
        deb_dir = self.makeDir()
        self._add_system_package(
            "broken", control_fields={"Depends": "missing"})
        self._add_package_to_deb_dir(
            deb_dir, "foo", control_fields={"Depends": "bar"})
        self._add_package_to_deb_dir(deb_dir, "bar")
        self._add_package_to_deb_dir(deb_dir, "missing")
        self.facade.add_channel_apt_deb("file://%s" % deb_dir, "./")
        self.facade.reload_channels()
        [foo] = self.facade.get_packages_by_name("foo")
        [bar] = self.facade.get_packages_by_name("bar")
        self.facade.mark_install(foo)
        self.facade._cache.commit = lambda fetch_progress: None
        error = self.assertRaises(DependencyError, self.facade.perform_changes)
        self.assertEqual([bar], error.packages)

    def test_perform_changes_with_broken_packages_remove_simple(self):
        """
        Even if some installed packages are broken in the system, it's
        still possible to remove packages that don't affect the broken ones.
        """
        deb_dir = self.makeDir()
        self._add_system_package(
            "broken", control_fields={"Depends": "missing"})
        self._add_system_package("foo")
        self._add_package_to_deb_dir(deb_dir, "missing")
        self.facade.add_channel_apt_deb("file://%s" % deb_dir, "./")
        self.facade.reload_channels()
        [foo] = self.facade.get_packages_by_name("foo")
        self.facade.mark_remove(foo)
        self.facade._cache.commit = lambda fetch_progress: None
        self.assertEqual("", self.facade.perform_changes())
        self.assertEqual(
            [foo.package], self.facade._cache.get_changes())

    def test_perform_changes_with_broken_packages_install_broken(self):
        """
        If some installed package is in a broken state and you install a
        package that fixes the broken package, as well as a new broken
        package, C{perform_changes()} will raise a C{TransactionError}.

        This test specifically tests the case where you replace the
        broken packages, but have the same number of broken packages
        before and after the changes.
        """
        deb_dir = self.makeDir()
        self._add_system_package(
            "broken", control_fields={"Depends": "missing"})
        self._add_package_to_deb_dir(
            deb_dir, "foo", control_fields={"Depends": "really-missing"})
        self._add_package_to_deb_dir(deb_dir, "missing")
        self.facade.add_channel_apt_deb("file://%s" % deb_dir, "./")
        self.facade.reload_channels()
        [broken] = self.facade.get_packages_by_name("broken")
        [foo] = self.facade.get_packages_by_name("foo")
        [missing] = self.facade.get_packages_by_name("missing")
        self.assertEqual(
            set([broken.package]), self.facade._get_broken_packages())
        self.facade.mark_install(foo)
        self.facade.mark_install(missing)
        self.facade._cache.commit = lambda fetch_progress: None
        error = self.assertRaises(
            TransactionError, self.facade.perform_changes)
        self.assertIn("you have held broken packages", error.args[0])
        self.assertEqual(
            set([foo.package]), self.facade._get_broken_packages())

    def test_wb_perform_changes_commit_error(self):
        """
        If an error happens when committing the changes to the cache, a
        transaction error is raised.
        """
        self._add_system_package("foo")
        self.facade.reload_channels()

        [foo] = self.facade.get_packages_by_name("foo")
        self.facade.mark_remove(foo)
        cache = self.mocker.replace(self.facade._cache)
        cache.commit(fetch_progress=ANY)
        self.mocker.throw(SystemError("Something went wrong."))
        self.mocker.replay()
        exception = self.assertRaises(TransactionError,
                                      self.facade.perform_changes)
        self.assertIn("Something went wrong.", exception.args[0])

    def test_mark_install_transaction_error(self):
        """
        Mark package 'name1' for installation, and try to perform changes.
        It should fail because 'name1' depends on 'requirename1', which
        isn't available in the package cache.
        """
        deb_dir = self.makeDir()
        create_simple_repository(deb_dir)
        self.facade.add_channel_deb_dir(deb_dir)
        self.facade.reload_channels()

        pkg = self.facade.get_packages_by_name("name1")[0]
        self.facade.mark_install(pkg)
        exception = self.assertRaises(TransactionError,
                                      self.facade.perform_changes)
        # XXX: Investigate if we can get a better error message.
        #self.assertIn("requirename", exception.args[0])
        self.assertIn("Unable to correct problems", exception.args[0])

    def test_mark_install_dependency_error(self):
        """
        If a dependency hasn't been marked for installation, a
        DependencyError is raised with the packages that need to be installed.
        """
        deb_dir = self.makeDir()
        self._add_package_to_deb_dir(
            deb_dir, "foo", control_fields={"Depends": "bar"})
        self._add_package_to_deb_dir(deb_dir, "bar")
        self.facade.add_channel_apt_deb("file://%s" % deb_dir, "./")
        self.facade.reload_channels()
        [foo] = self.facade.get_packages_by_name("foo")
        [bar] = self.facade.get_packages_by_name("bar")
        self.facade.mark_install(foo)
        error = self.assertRaises(DependencyError, self.facade.perform_changes)
        self.assertEqual([bar], error.packages)

    def test_wb_check_changes_unapproved_install_default(self):
        """
        C{_check_changes} raises C{DependencyError} with the candidate
        version, if a package is marked for installation, but not in the
        requested changes.
        """
        deb_dir = self.makeDir()
        self._add_package_to_deb_dir(deb_dir, "foo", version="1.0")
        self._add_package_to_deb_dir(deb_dir, "foo", version="2.0")
        self.facade.add_channel_apt_deb("file://%s" % deb_dir, "./")
        self.facade.reload_channels()
        [foo1, foo2] = sorted(self.facade.get_packages_by_name("foo"))
        self.assertEqual(foo1.package, foo2.package)
        package = foo1.package
        self.assertEqual(package.candidate, foo2)

        package.mark_install()
        self.assertEqual([package], self.facade._cache.get_changes())
        self.assertTrue(package.marked_install)

        error = self.assertRaises(
            DependencyError, self.facade._check_changes, [])
        self.assertEqual([foo2], error.packages)

    def test_wb_check_changes_unapproved_install_specific_version(self):
        """
        C{_check_changes} raises C{DependencyError} with the candidate
        version, if a package is marked for installation with a
        non-default candidate version.
        """
        deb_dir = self.makeDir()
        self._add_package_to_deb_dir(deb_dir, "foo", version="1.0")
        self._add_package_to_deb_dir(deb_dir, "foo", version="2.0")
        self.facade.add_channel_apt_deb("file://%s" % deb_dir, "./")
        self.facade.reload_channels()
        [foo1, foo2] = sorted(self.facade.get_packages_by_name("foo"))
        self.assertEqual(foo1.package, foo2.package)
        package = foo1.package

        package.candidate = foo1
        package.mark_install()
        self.assertEqual([package], self.facade._cache.get_changes())
        self.assertTrue(package.marked_install)

        error = self.assertRaises(
            DependencyError, self.facade._check_changes, [])
        self.assertEqual([foo1], error.packages)

    def test_check_changes_unapproved_remove(self):
        """
        C{_check_changes} raises C{DependencyError} with the installed
        version, if a package is marked for removal and the change isn't
        in the requested changes.
        """
        self._add_system_package("foo")
        self.facade.reload_channels()
        [foo] = self.facade.get_packages_by_name("foo")

        foo.package.mark_delete()
        self.assertEqual([foo.package], self.facade._cache.get_changes())
        self.assertTrue(foo.package.marked_delete)

        error = self.assertRaises(
            DependencyError, self.facade._check_changes, [])
        self.assertEqual([foo], error.packages)

    def test_check_changes_unapproved_remove_with_update_available(self):
        """
        C{_check_changes} raises C{DependencyError} with the installed
        version, if a package is marked for removal and there is an
        update available.
        """
        self._add_system_package("foo", version="1.0")
        deb_dir = self.makeDir()
        self._add_package_to_deb_dir(deb_dir, "foo", version="2.0")
        self.facade.add_channel_apt_deb("file://%s" % deb_dir, "./")
        self.facade.reload_channels()
        [foo1, foo2] = sorted(self.facade.get_packages_by_name("foo"))
        self.assertEqual(foo1.package, foo2.package)
        package = foo1.package

        package.mark_delete()
        self.assertEqual([package], self.facade._cache.get_changes())
        self.assertTrue(package.marked_delete)

        error = self.assertRaises(
            DependencyError, self.facade._check_changes, [])
        self.assertEqual([foo1], error.packages)

    def test_check_changes_unapproved_upgrade(self):
        """
        If a package is marked to be upgraded, C{_check_changes} raises
        C{DependencyError} with the installed version and the version to
        be upgraded to.
        """
        self._add_system_package("foo", version="1.0")
        deb_dir = self.makeDir()
        self._add_package_to_deb_dir(deb_dir, "foo", version="2.0")
        self.facade.add_channel_apt_deb("file://%s" % deb_dir, "./")
        self.facade.reload_channels()
        [foo1, foo2] = sorted(self.facade.get_packages_by_name("foo"))
        self.assertEqual(foo1.package, foo2.package)
        package = foo1.package

        package.mark_install()
        self.assertEqual([package], self.facade._cache.get_changes())
        self.assertTrue(package.marked_upgrade)

        error = self.assertRaises(
            DependencyError, self.facade._check_changes, [])
        self.assertEqual(set([foo1, foo2]), set(error.packages))

    def test_check_changes_unapproved_downgrade(self):
        """
        If a package is marked to be downgraded, C{_check_changes} raises
        C{DependencyError} with the installed version and the version to
        be downgraded to.
        """
        self._add_system_package("foo", version="2.0")
        deb_dir = self.makeDir()
        self._add_package_to_deb_dir(deb_dir, "foo", version="1.0")
        self._add_package_to_deb_dir(deb_dir, "foo", version="3.0")
        self.facade.add_channel_apt_deb("file://%s" % deb_dir, "./")
        self.facade.reload_channels()
        [foo1, foo2] = sorted(self.facade.get_packages_by_name("foo"))[:2]
        self.assertEqual(foo1.package, foo2.package)
        package = foo1.package
        package.candidate = foo1

        package.mark_install()
        self.assertEqual([package], self.facade._cache.get_changes())
        self.assertTrue(package.marked_downgrade)

        error = self.assertRaises(
            DependencyError, self.facade._check_changes, [])
        self.assertEqual(set([foo1, foo2]), set(error.packages))

    def test_mark_global_upgrade_dependency_error(self):
        """
        If a package is marked for upgrade, a DependencyError will be
        raised, indicating which version of the package will be
        installed and which will be removed.
        """
        deb_dir = self.makeDir()
        self._add_system_package("foo", version="1.0")
        self._add_package_to_deb_dir(
            deb_dir, "foo", version="1.5", control_fields={"Depends": "bar"})
        self._add_package_to_deb_dir(deb_dir, "bar")
        self.facade.add_channel_apt_deb("file://%s" % deb_dir, "./")
        self.facade.reload_channels()
        foo_10, foo_15 = sorted(self.facade.get_packages_by_name("foo"))
        [bar] = self.facade.get_packages_by_name("bar")
        self.facade.mark_global_upgrade()
        error = self.assertRaises(DependencyError, self.facade.perform_changes)
        self.assertEqual(
            sorted([bar, foo_10, foo_15], key=self.version_sortkey),
            sorted(error.packages, key=self.version_sortkey))

    def test_mark_remove_dependency_error(self):
        """
        If a dependency hasn't been marked for removal,
        DependencyError is raised with the packages that need to be removed.
        """
        self._add_system_package("foo")
        self._add_system_package("bar", control_fields={"Depends": "foo"})
        self.facade.reload_channels()
        [foo] = self.facade.get_packages_by_name("foo")
        [bar] = self.facade.get_packages_by_name("bar")
        self.facade.mark_remove(foo)
        error = self.assertRaises(DependencyError, self.facade.perform_changes)
        self.assertEqual([bar], error.packages)

    def test_mark_remove_held_packages(self):
        """
        If a package that is on hold is marked for removal, a
        C{TransactionError} is raised by C{perform_changes}.
        """
        self._add_system_package(
            "foo", control_fields={"Status": "hold ok installed"})
        self._add_system_package(
            "bar", control_fields={"Status": "hold ok installed"})
        self.facade.reload_channels()
        [foo] = self.facade.get_packages_by_name("foo")
        [bar] = self.facade.get_packages_by_name("bar")
        self.facade.mark_remove(foo)
        self.facade.mark_remove(bar)
        error = self.assertRaises(
            TransactionError, self.facade.perform_changes)
        self.assertEqual(
            "Can't perform the changes, since the following packages" +
            " are held: bar, foo", error.args[0])

    def test_changer_upgrade_package(self):
        """
        When the {PackageChanger} requests for a package to be upgraded,
        it requests that the new version is to be installed, and the old
        version to be removed. This is how you had to do it with Smart.
        With Apt we have to take care of not marking the old version for
        removal, since that can result in packages that depend on the
        upgraded package to be removed.
        """
        self._add_system_package(
            "foo", control_fields={"Depends": "bar"})
        self._add_system_package("bar", version="1.0")
        deb_dir = self.makeDir()
        self._add_package_to_deb_dir(deb_dir, "bar", version="2.0")
        self.facade.add_channel_apt_deb("file://%s" % deb_dir, "./")
        self.facade.reload_channels()
        bar_1, bar_2 = sorted(self.facade.get_packages_by_name("bar"))
        self.facade.mark_install(bar_2)
        self.facade.mark_remove(bar_1)
        self.facade._cache.commit = lambda fetch_progress: None
        self.facade.perform_changes()
        [bar] = self.facade._cache.get_changes()
        self.assertTrue(bar.marked_upgrade)

    def test_mark_global_upgrade_held_packages(self):
        """
        If a package that is on hold is marked for upgrade,
        C{perform_changes} won't request to install a newer version of
        that package.
        """
        self._add_system_package(
            "foo", version="1.0",
            control_fields={"Status": "hold ok installed"})
        deb_dir = self.makeDir()
        self._add_package_to_deb_dir(deb_dir, "foo", version="1.5")
        self.facade.add_channel_apt_deb("file://%s" % deb_dir, "./")
        self.facade.reload_channels()
        [foo_10, foo_15] = sorted(self.facade.get_packages_by_name("foo"))
        self.facade.mark_global_upgrade()
        self.assertEqual(None, self.facade.perform_changes())
        self.assertEqual(foo_10, foo_15.package.installed)

    def test_mark_global_upgrade_held_dependencies(self):
        """
        If a package that can be upgraded, but that package depends on a
        newer version of a held package, the first package won't be
        marked as requiring upgrade.
        """
        self._add_system_package(
            "foo", version="1.0",
            control_fields={"Status": "hold ok installed"})
        self._add_system_package(
            "bar", version="1.0",
            control_fields={"Depends": "foo"})
        deb_dir = self.makeDir()
        self._add_package_to_deb_dir(deb_dir, "foo", version="2.0")
        self._add_package_to_deb_dir(
            deb_dir, "bar", version="2.0",
            control_fields={"Depends": "foo (>> 1.0)"})
        self.facade.add_channel_apt_deb("file://%s" % deb_dir, "./")
        self.facade.reload_channels()
        [foo_1, foo_2] = sorted(self.facade.get_packages_by_name("foo"))
        [bar_1, bar_2] = sorted(self.facade.get_packages_by_name("bar"))
        self.facade.mark_global_upgrade()
        self.assertEqual(None, self.facade.perform_changes())
        self.assertEqual(foo_1, foo_2.package.installed)
        self.assertEqual(bar_1, bar_2.package.installed)

    def test_get_locked_packages_simple(self):
        """
        C{get_locked_packages} returns all packages that are marked as
        being held. Locks came from the Smart implementation, but since
        a locked installed package basically is the same as a package
        with a dpkg hold, having C{get_locked_packages} return all the
        held packages, the Landscape server UI won't try to upgrade
        those packages to a newer version.
        """
        self._add_system_package(
            "foo", control_fields={"Status": "hold ok installed"})
        self._add_system_package("bar")
        self.facade.reload_channels()
        [foo] = self.facade.get_packages_by_name("foo")
        self.assertEqual([foo], self.facade.get_locked_packages())

    def test_get_locked_packages_multi(self):
        """
        C{get_locked_packages} returns only the installed version of the
        held package.
        """
        self._add_system_package(
            "foo", version="1.0",
            control_fields={"Status": "hold ok installed"})
        self._add_system_package("bar", version="1.0")
        deb_dir = self.makeDir()
        self._add_package_to_deb_dir(deb_dir, "foo", version="1.5")
        self._add_package_to_deb_dir(deb_dir, "bar", version="1.5")
        self.facade.add_channel_apt_deb("file://%s" % deb_dir, "./")
        self.facade.reload_channels()
        foo_10 = sorted(self.facade.get_packages_by_name("foo"))[0]
        self.assertEqual([foo_10], self.facade.get_locked_packages())

    def test_perform_changes_dependency_error_same_version(self):
        """
        Apt's Version objects have the same hash if the version string
        is the same. So if we have two different packages having the
        same version, perform_changes() needs to take the package into
        account when finding out which changes were requested.
        """
        self._add_system_package("foo", version="1.0")
        self._add_system_package(
            "bar", version="1.0", control_fields={"Depends": "foo"})
        self._add_system_package(
            "baz", version="1.0", control_fields={"Depends": "foo"})
        self.facade.reload_channels()
        [foo] = self.facade.get_packages_by_name("foo")
        [bar] = self.facade.get_packages_by_name("bar")
        [baz] = self.facade.get_packages_by_name("baz")
        self.facade.mark_remove(foo)
        error = self.assertRaises(DependencyError, self.facade.perform_changes)

        self.assertEqual(
            sorted(error.packages, key=self.version_sortkey),
            sorted([bar, baz], key=self.version_sortkey))

    def test_get_package_holds_with_no_hold(self):
        """
        If no package holds are set, C{get_package_holds} returns
        an empty C{list}.
        """
        self._add_system_package("foo")
        self.facade.reload_channels()
        self.assertEqual([], self.facade.get_package_holds())

    def test_get_package_holds_with_holds(self):
        """
        If package holds are set, C{get_package_holds} returns
        the name of the packages that are held.
        """
        self._add_system_package(
            "foo", control_fields={"Status": "hold ok installed"})
        self._add_system_package("bar")
        self._add_system_package(
            "baz", control_fields={"Status": "hold ok installed"})
        self.facade.reload_channels()

        self.assertEqual(
            ["baz", "foo"], sorted(self.facade.get_package_holds()))

    def test_set_package_hold(self):
        """
        C{set_package_hold} marks a package to be on hold.
        """
        self._add_system_package("foo")
        self.facade.reload_channels()
        self.facade.set_package_hold("foo")
        self.facade.reload_channels()

        self.assertEqual(["foo"], self.facade.get_package_holds())

    def test_set_package_hold_existing_hold(self):
        """
        If a package is already hel, C{set_package_hold} doesn't return
        an error.
        """
        self._add_system_package(
            "foo", control_fields={"Status": "hold ok installed"})
        self.facade.reload_channels()
        self.facade.set_package_hold("foo")
        self.facade.reload_channels()

        self.assertEqual(["foo"], self.facade.get_package_holds())

    def test_remove_package_hold(self):
        """
        C{remove_package_hold} marks a package not to be on hold.
        """
        self._add_system_package(
            "foo", control_fields={"Status": "hold ok installed"})
        self.facade.reload_channels()
        self.facade.remove_package_hold("foo")
        self.facade.reload_channels()

        self.assertEqual([], self.facade.get_package_holds())

    def test_remove_package_hold_no_package(self):
        """
        If a package doesn't exist, C{remove_package_hold} doesn't
        return an error. It's up to the caller to make sure that the
        package exist, if it's important.
        """
        self._add_system_package("foo")
        self.facade.reload_channels()
        self.facade.remove_package_hold("bar")
        self.facade.reload_channels()

        self.assertEqual([], self.facade.get_package_holds())

    def test_remove_package_hold_no_hold(self):
        """
        If a package isn't held, the existing selection is retained when
        C{remove_package_hold} is called.
        """
        self._add_system_package(
            "foo", control_fields={"Status": "deinstall ok installed"})
        self.facade.reload_channels()
        self.facade.remove_package_hold("foo")
        self.facade.reload_channels()

        self.assertEqual([], self.facade.get_package_holds())
        [foo] = self.facade.get_packages_by_name("foo")
        self.assertEqual(
            apt_pkg.SELSTATE_DEINSTALL, foo.package._pkg.selected_state)

    if not hasattr(Package, "shortname"):
        # The 'shortname' attribute was added when multi-arch support
        # was added to python-apt. So if it's not there, it means that
        # multi-arch support isn't available.
        skip_message = "multi-arch not supported"
        test_wb_mark_install_upgrade_non_main_arch_dependency_error.skip = (
            skip_message)
        test_wb_mark_install_upgrade_non_main_arch.skip = skip_message


class SmartFacadeTest(LandscapeTest):

    helpers = [SmartFacadeHelper]

    def test_needs_smart(self):
        """
        If the Smart python modules can't be imported, a C{RuntimeError}
        is raised when trying to create a C{SmartFacade}.
        """

        def reset_has_smart():
            facade_module.has_smart = old_has_smart

        self.addCleanup(reset_has_smart)
        old_has_smart = facade_module.has_smart
        facade_module.has_smart = False

        self.assertRaises(RuntimeError, self.Facade)

    def test_get_packages(self):
        self.facade.reload_channels()
        pkgs = self.facade.get_packages()
        self.assertEqual(sorted(pkg.name for pkg in pkgs),
                         ["name1", "name2", "name3"])

    def test_get_packages_wont_return_non_debian_packages(self):
        self.facade.reload_channels()
        ctrl_mock = self.mocker.patch(Control)

        class StubPackage(object):
            pass

        cache_mock = ctrl_mock.getCache()
        cache_mock.getPackages()
        self.mocker.result([StubPackage(), StubPackage()])
        self.mocker.replay()
        self.assertEqual(self.facade.get_packages(), [])

    def test_get_packages_by_name(self):
        self.facade.reload_channels()
        pkgs = self.facade.get_packages_by_name("name1")
        self.assertEqual([pkg.name for pkg in pkgs], ["name1"])
        pkgs = self.facade.get_packages_by_name("name2")
        self.assertEqual([pkg.name for pkg in pkgs], ["name2"])

    def test_get_packages_by_name_wont_return_non_debian_packages(self):
        self.facade.reload_channels()
        ctrl_mock = self.mocker.patch(Control)

        class StubPackage(object):
            pass

        cache_mock = ctrl_mock.getCache()
        cache_mock.getPackages("name")
        self.mocker.result([StubPackage(), StubPackage()])
        self.mocker.replay()
        self.assertEqual(self.facade.get_packages_by_name("name"), [])

    def test_get_package_skeleton(self):
        self.facade.reload_channels()
        pkg1 = self.facade.get_packages_by_name("name1")[0]
        pkg2 = self.facade.get_packages_by_name("name2")[0]
        skeleton1 = self.facade.get_package_skeleton(pkg1)
        skeleton2 = self.facade.get_package_skeleton(pkg2)
        self.assertEqual(skeleton1.get_hash(), HASH1)
        self.assertEqual(skeleton2.get_hash(), HASH2)

    def test_build_skeleton_with_info(self):
        self.facade.reload_channels()
        pkg = self.facade.get_packages_by_name("name1")[0]
        skeleton = self.facade.get_package_skeleton(pkg, True)
        self.assertEqual(skeleton.section, "Group1")
        self.assertEqual(skeleton.summary, "Summary1")
        self.assertEqual(skeleton.description, "Description1")
        self.assertEqual(skeleton.size, 1038)
        self.assertEqual(skeleton.installed_size, 28672)

    def test_get_package_hash(self):
        self.facade.reload_channels()
        pkg = self.facade.get_packages_by_name("name1")[0]
        self.assertEqual(self.facade.get_package_hash(pkg), HASH1)
        pkg = self.facade.get_packages_by_name("name2")[0]
        self.assertEqual(self.facade.get_package_hash(pkg), HASH2)

    def test_get_package_hashes(self):
        self.facade.reload_channels()
        hashes = self.facade.get_package_hashes()
        self.assertEqual(sorted(hashes), sorted([HASH1, HASH2, HASH3]))

    def test_get_package_by_hash(self):
        self.facade.reload_channels()
        pkg = self.facade.get_package_by_hash(HASH1)
        self.assertEqual(pkg.name, "name1")
        pkg = self.facade.get_package_by_hash(HASH2)
        self.assertEqual(pkg.name, "name2")
        pkg = self.facade.get_package_by_hash("none")
        self.assertEqual(pkg, None)

    def test_reload_channels_clears_hash_cache(self):
        # Load hashes.
        self.facade.reload_channels()

        # Hold a reference to packages.
        pkg1 = self.facade.get_packages_by_name("name1")[0]
        pkg2 = self.facade.get_packages_by_name("name2")[0]
        pkg3 = self.facade.get_packages_by_name("name3")[0]
        self.assertTrue(pkg1 and pkg2)

        # Remove the package from the repository.
        os.unlink(os.path.join(self.repository_dir, PKGNAME1))

        # Forcibly change the mtime of our repository, so that Smart
        # will consider it as changed (if the change is inside the
        # same second the directory's mtime will be the same)
        mtime = int(time.time() + 1)
        os.utime(self.repository_dir, (mtime, mtime))

        # Reload channels.
        self.facade.reload_channels()

        # Only packages with name2 and name3 should be loaded, and they're
        # not the same objects anymore.
        self.assertEqual(
            sorted([pkg.name for pkg in self.facade.get_packages()]),
            ["name2", "name3"])
        self.assertNotEquals(set(self.facade.get_packages()),
                             set([pkg2, pkg3]))

        # The hash cache shouldn't include either of the old packages.
        self.assertEqual(self.facade.get_package_hash(pkg1), None)
        self.assertEqual(self.facade.get_package_hash(pkg2), None)
        self.assertEqual(self.facade.get_package_hash(pkg3), None)

        # Also, the hash for package1 shouldn't be present at all.
        self.assertEqual(self.facade.get_package_by_hash(HASH1), None)

        # While HASH2 and HASH3 should point to the new packages.
        new_pkgs = self.facade.get_packages()
        self.assertTrue(self.facade.get_package_by_hash(HASH2)
                        in new_pkgs)
        self.assertTrue(self.facade.get_package_by_hash(HASH3)
                        in new_pkgs)

        # Which are not the old packages.
        self.assertFalse(pkg2 in new_pkgs)
        self.assertFalse(pkg3 in new_pkgs)

    def test_ensure_reload_channels(self):
        """
        The L{SmartFacade.ensure_channels_reloaded} can be called more
        than once, but channels will be reloaded only the first time.
        """
        self.assertEqual(len(self.facade.get_packages()), 0)
        self.facade.ensure_channels_reloaded()
        self.assertEqual(len(self.facade.get_packages()), 3)

        # Calling it once more won't reload channels again.
        self.facade.get_packages_by_name("name1")[0].installed = True
        self.facade.ensure_channels_reloaded()
        self.assertTrue(self.facade.get_packages_by_name("name1")[0].installed)

    def test_perform_changes_with_nothing_to_do(self):
        """perform_changes() should return None when there's nothing to do.
        """
        self.facade.reload_channels()
        self.assertEqual(self.facade.perform_changes(), None)

    def test_reset_marks(self):
        """perform_changes() should return None when there's nothing to do.
        """
        self.facade.reload_channels()
        pkg = self.facade.get_packages_by_name("name1")[0]
        self.facade.mark_install(pkg)
        self.facade.reset_marks()
        self.assertEqual(self.facade.perform_changes(), None)

    def test_mark_install_transaction_error(self):
        """
        Mark package 'name1' for installation, and try to perform changes.
        It should fail because 'name1' depends on 'requirename1'.
        """
        self.facade.reload_channels()

        pkg = self.facade.get_packages_by_name("name1")[0]
        self.facade.mark_install(pkg)
        exception = self.assertRaises(TransactionError,
                                      self.facade.perform_changes)
        self.assertIn("requirename", exception.args[0])

    def test_mark_install_dependency_error(self):
        """
        Now we artificially inject the needed dependencies of 'name1'
        in 'name2', but we don't mark 'name2' for installation, and
        that should make perform_changes() fail with a dependency
        error on the needed package.
        """
        self.facade.reload_channels()

        provide1 = Provides("prerequirename1", "prerequireversion1")
        provide2 = Provides("requirename1", "requireversion1")
        pkg2 = self.facade.get_packages_by_name("name2")[0]
        pkg2.provides += (provide1, provide2)

        # We have to satisfy *both* packages.
        provide1 = Provides("prerequirename2", "prerequireversion2")
        provide2 = Provides("requirename2", "requireversion2")
        pkg1 = self.facade.get_packages_by_name("name1")[0]
        pkg1.provides += (provide1, provide2)

        # Ask Smart to reprocess relationships.
        self.facade.reload_cache()

        self.assertEqual(pkg1.requires[0].providedby[0].packages[0], pkg2)
        self.assertEqual(pkg1.requires[1].providedby[0].packages[0], pkg2)

        self.facade.mark_install(pkg1)
        try:
            self.facade.perform_changes()
        except DependencyError, exception:
            pass
        else:
            exception = None
        self.assertTrue(exception, "DependencyError not raised")
        self.assertEqual(exception.packages, [pkg2])

    def test_mark_remove_dependency_error(self):
        """
        Besides making 'name1' satisfy 'name2' and the contrary.  We'll
        mark both packages installed, so that we can get an error on
        removal.
        """
        self.facade.reload_channels()

        provide1 = Provides("prerequirename1", "prerequireversion1")
        provide2 = Provides("requirename1", "requireversion1")
        pkg2 = self.facade.get_packages_by_name("name2")[0]
        pkg2.provides += (provide1, provide2)

        # We have to satisfy *both* packages.
        provide1 = Provides("prerequirename2", "prerequireversion2")
        provide2 = Provides("requirename2", "requireversion2")
        pkg1 = self.facade.get_packages_by_name("name1")[0]
        pkg1.provides += (provide1, provide2)

        # Ask Smart to reprocess relationships.
        self.facade.reload_cache()

        pkg1.installed = True
        pkg2.installed = True

        self.assertEqual(pkg1.requires[0].providedby[0].packages[0], pkg2)
        self.assertEqual(pkg1.requires[1].providedby[0].packages[0], pkg2)

        self.facade.mark_remove(pkg2)
        try:
            output = self.facade.perform_changes()
        except DependencyError, exception:
            output = ""
        else:
            exception = None
        self.assertTrue(exception, "DependencyError not raised. Output: %s"
                                   % repr(output))
        self.assertEqual(exception.packages, [pkg1])

    def test_mark_upgrade_dependency_error(self):
        """Artificially make pkg2 upgrade pkg1, and mark pkg1 for upgrade."""

        # The backend only works after initialized.
        from smart.backends.deb.base import DebUpgrades, DebConflicts

        self.facade.reload_channels()

        pkg1 = self.facade.get_packages_by_name("name1")[0]
        pkg2 = self.facade.get_packages_by_name("name2")[0]

        # Artificially make pkg2 be self-satisfied, and make it upgrade and
        # conflict with pkg1.
        pkg2.requires = []
        pkg2.upgrades = [DebUpgrades("name1", "=", "version1-release1")]
        pkg2.conflicts = [DebConflicts("name1", "=", "version1-release1")]

        # pkg1 will also be self-satisfied.
        pkg1.requires = []

        # Ask Smart to reprocess relationships.
        self.facade.reload_cache()

        # Mark the pkg1 as installed.  Must be done after reloading
        # the cache as reloading will reset it to the loader installed
        # status.
        pkg1.installed = True

        # Check that the linkage worked.
        self.assertEqual(pkg2.upgrades[0].providedby[0].packages[0], pkg1)

        # Perform the upgrade test.
        self.facade.mark_upgrade(pkg1)
        try:
            self.facade.perform_changes()
        except DependencyError, exception:
            pass
        else:
            exception = None
        self.assertTrue(exception, "DependencyError not raised")

        # Both packages should be included in the dependency error. One
        # must be removed, and the other installed.
        self.assertEqual(set(exception.packages), set([pkg1, pkg2]))

    def test_perform_changes_with_logged_error(self):
        self.log_helper.ignore_errors(".*dpkg")

        self.facade.reload_channels()

        pkg = self.facade.get_packages_by_name("name1")[0]
        pkg.requires = ()

        self.facade.reload_cache()

        self.facade.mark_install(pkg)

        try:
            output = self.facade.perform_changes()
        except SmartError, exception:
            output = ""
        else:
            exception = None

        self.assertTrue(exception,
                        "SmartError not raised. Output: %s" % repr(output))
        # We can't check the whole message because the dpkg error can be
        # localized. We can't use str(exception) either because it can contain
        # unicode
        self.assertIn("ERROR", exception.args[0])
        self.assertIn("(2)", exception.args[0])
        self.assertIn("\n[unpack] name1_version1-release1\ndpkg: ",
                      exception.args[0])

    def test_perform_changes_is_non_interactive(self):
        from smart.backends.deb.pm import DebPackageManager

        self.facade.reload_channels()

        pkg = self.facade.get_packages_by_name("name1")[0]
        pkg.requires = ()

        self.facade.reload_cache()

        self.facade.mark_install(pkg)

        environ = []

        def check_environ(self, argv, output):
            environ.append(os.environ.get("DEBIAN_FRONTEND"))
            environ.append(os.environ.get("APT_LISTCHANGES_FRONTEND"))
            return 0

        DebPackageManager.dpkg, olddpkg = check_environ, DebPackageManager.dpkg

        try:
            self.facade.perform_changes()
        finally:
            DebPackageManager.dpkg = olddpkg

        self.assertEqual(environ, ["noninteractive", "none",
                                   "noninteractive", "none"])

    def test_perform_changes_with_policy_remove(self):
        """
        When requested changes are only about removing packages, we set
        the Smart transaction policy to C{PolicyRemove}.
        """
        create_deb(self.repository_dir, PKGNAME4, PKGDEB4)
        self.facade.reload_channels()

        # Importing these modules fail if Smart is not initialized
        from smart.backends.deb.base import DebRequires

        pkg1 = self.facade.get_package_by_hash(HASH1)
        pkg1.requires.append(DebRequires("name3", ">=", "version3-release3"))

        pkg3 = self.facade.get_package_by_hash(HASH3)

        # Ask Smart to reprocess relationships.
        self.facade.reload_cache()

        pkg1.installed = True
        pkg3.installed = True

        self.facade.mark_remove(pkg3)
        error = self.assertRaises(DependencyError, self.facade.perform_changes)
        [missing] = error.packages
        self.assertIdentical(pkg1, missing)

    def test_perform_changes_with_commit_change_set_errors(self):

        self.facade.reload_channels()

        pkg = self.facade.get_packages_by_name("name1")[0]
        pkg.requires = ()

        self.facade.mark_install(pkg)

        ctrl_mock = self.mocker.patch(Control)
        ctrl_mock.commitChangeSet(ANY)
        self.mocker.throw(smart.Error("commit error"))
        self.mocker.replay()

        self.assertRaises(TransactionError, self.facade.perform_changes)

    def test_deinit_cleans_the_state(self):
        self.facade.reload_channels()
        self.assertTrue(self.facade.get_package_by_hash(HASH1))
        self.facade.deinit()
        self.assertFalse(self.facade.get_package_by_hash(HASH1))

    def test_deinit_deinits_smart(self):
        self.facade.reload_channels()
        self.assertTrue(smart.iface.object)
        self.facade.deinit()
        self.assertFalse(smart.iface.object)

    def test_deinit_when_smart_wasnt_initialized(self):
        self.assertFalse(smart.iface.object)
        # Nothing bad should happen.
        self.facade.deinit()

    def test_reload_channels_wont_consider_non_debian_packages(self):

        class StubPackage(object):
            pass

        pkg = StubPackage()

        ctrl_mock = self.mocker.patch(Control)
        cache_mock = ctrl_mock.getCache()
        cache_mock.getPackages()
        self.mocker.result([pkg])
        self.mocker.replay()

        self.facade.reload_channels()
        self.assertEqual(self.facade.get_package_hash(pkg), None)

    def test_reload_channels_with_channel_error(self):
        """
        The L{SmartFacade.reload_channels} method raises a L{ChannelsError} if
        smart fails to load the configured channels.
        """
        ctrl_mock = self.mocker.patch(Control)
        ctrl_mock.reloadChannels(caching=ALWAYS)
        self.mocker.throw(smart.Error(u"Channel information is locked"))
        self.mocker.replay()
        self.assertRaises(ChannelError, self.facade.reload_channels)

    def test_reset_add_get_channels(self):

        channels = [("alias0", {"type": "test"}),
                    ("alias1", {"type": "test"})]

        self.facade.reset_channels()

        self.assertEqual(self.facade.get_channels(), {})

        self.facade.add_channel(*channels[0])
        self.facade.add_channel(*channels[1])

        self.assertEqual(self.facade.get_channels(), dict(channels))

    def test_add_apt_deb_channel(self):
        """
        The L{SmartFacade.add_channel_apt_deb} add a Smart channel of
        type C{"apt-deb"}.
        """
        self.facade.reset_channels()
        self.facade.add_channel_apt_deb("http://url/", "name", "component")
        self.assertEqual(self.facade.get_channels(),
                         {"name": {"baseurl": "http://url/",
                                   "distribution": "name",
                                   "components": "component",
                                   "type": "apt-deb"}})

    def test_add_deb_dir_channel(self):
        """
        The L{SmartFacade.add_channel_deb_dir} add a Smart channel of
        type C{"deb-dir"}.
        """
        self.facade.reset_channels()
        self.facade.add_channel_deb_dir("/my/repo")
        self.assertEqual(self.facade.get_channels(),
                         {"/my/repo": {"path": "/my/repo",
                                       "type": "deb-dir"}})

    def test_get_arch(self):
        """
        The L{SmartFacade.get_arch} should return the system dpkg
        architecture.
        """
        deferred = Deferred()

        def do_test():
            result = getProcessOutputAndValue("/usr/bin/dpkg",
                                              ("--print-architecture",))

            def callback((out, err, code)):
                self.assertEqual(self.facade.get_arch(), out.strip())
            result.addCallback(callback)
            result.chainDeferred(deferred)

        reactor.callWhenRunning(do_test)
        return deferred

    def test_set_arch_multiple_times(self):

        repo = create_full_repository(self.makeDir())

        self.facade.set_arch("i386")
        self.facade.reset_channels()
        self.facade.add_channel_apt_deb(repo.url, repo.codename,
                                        " ".join(repo.components))
        self.facade.reload_channels()

        pkgs = self.facade.get_packages()
        self.assertEqual(len(pkgs), 2)
        self.assertEqual(pkgs[0].name, "syslinux")
        self.assertEqual(pkgs[1].name, "kairos")

        self.facade.deinit()
        self.facade.set_arch("amd64")
        self.facade.reset_channels()
        self.facade.add_channel_apt_deb(repo.url, repo.codename,
                                        " ".join(repo.components))
        self.facade.reload_channels()

        pkgs = self.facade.get_packages()
        self.assertEqual(len(pkgs), 2)
        self.assertEqual(pkgs[0].name, "libclthreads2")
        self.assertEqual(pkgs[1].name, "kairos")

    def test_set_caching_with_reload_error(self):

        alias = "alias"
        channel = {"type": "deb-dir",
                   "path": "/does/not/exist"}

        self.facade.reset_channels()
        self.facade.add_channel(alias, channel)
        self.facade.set_caching(NEVER)

        self.assertRaises(ChannelError, self.facade.reload_channels)
        self.facade._channels = {}

        ignore_re = re.compile("\[Smart\].*'alias'.*/does/not/exist")

        self.log_helper.ignored_exception_regexes = [ignore_re]

    def test_init_landscape_plugins(self):
        """
        The landscape plugin which helps managing proxies is loaded when smart
        is initialized: this sets a smart configuration variable and load the
        module.
        """
        self.facade.reload_channels()
        self.assertTrue(smart.sysconf.get("use-landscape-proxies"))
        self.assertIn("smart.plugins.landscape", sys.modules)

    def test_get_package_locks_with_no_lock(self):
        """
        If no package locks are set, L{SmartFacade.get_package_locks} returns
        an empty C{list}.
        """
        self.assertEqual(self.facade.get_package_locks(), [])

    def test_get_package_locks_with_one_lock(self):
        """
        If one lock is set, the list of locks contains one item.
        """
        self.facade.set_package_lock("name1", "<", "version1")
        self.assertEqual(self.facade.get_package_locks(),
                         [("name1", "<", "version1")])

    def test_get_package_locks_with_many_locks(self):
        """
        It's possible to have more than one package lock and several conditions
        for each of them.
        """
        self.facade.set_package_lock("name1", "<", "version1")
        self.facade.set_package_lock("name1", ">=", "version3")
        self.facade.set_package_lock("name2")
        self.assertEqual(sorted(self.facade.get_package_locks()),
                         sorted([("name1", "<", "version1"),
                                 ("name1", ">=", "version3"),
                                 ("name2", "", "")]))

    def test_set_package_lock(self):
        """
        It is possible to lock a package by simply specifying its name.
        """
        self.facade.set_package_lock("name1")
        self.facade.reload_channels()
        [package] = self.facade.get_locked_packages()
        self.assertEqual(package.name, "name1")

    def test_set_package_lock_with_matching_condition(self):
        """
        It is possible to set a package lock specifying both a
        package name and version condition. Any matching package
        will be locked.
        """
        self.facade.set_package_lock("name1", "<", "version2")
        self.facade.reload_channels()
        [package] = self.facade.get_locked_packages()
        self.assertEqual(package.name, "name1")

    def test_set_package_lock_with_non_matching_condition(self):
        """
        If the package lock conditions do not match any package,
        no package will be locked.
        """
        self.facade.set_package_lock("name1", "<", "version1")
        self.facade.reload_channels()
        self.assertEqual(self.facade.get_locked_packages(), [])

    def test_set_package_lock_with_missing_version(self):
        """
        When specifing a relation for a package lock condition, a version
        must be provided as well.
        """
        error = self.assertRaises(RuntimeError, self.facade.set_package_lock,
                                  "name1", "<", "")
        self.assertEqual(str(error), "Package lock version not provided")

    def test_set_package_lock_with_missing_relation(self):
        """
        When specifing a version for a package lock condition, a relation
        must be provided as well.
        """
        error = self.assertRaises(RuntimeError, self.facade.set_package_lock,
                                  "name1", "", "version1")
        self.assertEqual(str(error), "Package lock relation not provided")

    def test_remove_package_lock(self):
        """
        It is possibly to remove a package lock without any version condition.
        """
        self.facade.set_package_lock("name1")
        self.facade.remove_package_lock("name1")
        self.assertEqual(self.facade.get_locked_packages(), [])

    def test_remove_package_lock_with_condition(self):
        """
        It is possibly to remove a package lock with a version condition.
        """
        self.facade.set_package_lock("name1", "<", "version1")
        self.facade.remove_package_lock("name1", "<", "version1")
        self.assertEqual(self.facade.get_locked_packages(), [])

    def test_save_config(self):
        """
        It is possible to lock a package by simply specifying its name.
        """
        self.facade.set_package_lock("python", "=>", "2.5")
        self.facade.save_config()
        self.facade.deinit()
        self.assertEqual(self.facade.get_package_locks(),
                         [("python", "=>", "2.5")])
