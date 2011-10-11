import time
import os
import re
import sys
import textwrap

from smart.control import Control
from smart.cache import Provides
from smart.const import NEVER, ALWAYS

import apt_inst
from aptsources.sourceslist import SourcesList

from twisted.internet import reactor
from twisted.internet.defer import Deferred
from twisted.internet.utils import getProcessOutputAndValue

import smart

from landscape.lib.fs import append_file, read_file
from landscape.package.facade import (
    TransactionError, DependencyError, ChannelError, SmartError)

from landscape.tests.mocker import ANY
from landscape.tests.helpers import LandscapeTest
from landscape.package.tests.helpers import (
    SmartFacadeHelper, HASH1, HASH2, HASH3, PKGNAME1, PKGNAME2, PKGNAME3,
    PKGNAME4, PKGDEB4, PKGDEB1, create_full_repository, create_deb,
    AptFacadeHelper, create_simple_repository)


class AptFacadeTest(LandscapeTest):

    helpers = [AptFacadeHelper]

    def _add_system_package(self, name, architecture="all", version="1.0"):
        """Add a package to the dpkg status file."""
        append_file(self.dpkg_status, textwrap.dedent("""\
                Package: %s
                Status: install ok installed
                Priority: optional
                Section: misc
                Installed-Size: 1234
                Maintainer: Someone
                Architecture: %s
                Source: source
                Version: %s
                Config-Version: 1.0
                Description: description

                """ % (name, architecture, version)))

    def _install_deb_file(self, path):
        """Fake the the given deb file is installed in the system."""
        deb_file = open(path)
        deb = apt_inst.DebFile(deb_file)
        control = deb.control.extractdata("control")
        deb_file.close()
        lines = control.splitlines()
        lines.insert(1, "Status: install ok installed")
        status = "\n".join(lines)
        append_file(self.dpkg_status, status + "\n\n")

    def _add_package_to_deb_dir(self, path, name, version="1.0"):
        """Add fake package information to a directory.

        There will only be basic information about the package
        available, so that get_packages() have something to return.
        There won't be an actual package in the dir.
        """
        package_stanza = textwrap.dedent("""
                Package: %(name)s
                Priority: optional
                Section: misc
                Installed-Size: 1234
                Maintainer: Someone
                Architecture: all
                Source: source
                Version: %(version)s
                Config-Version: 1.0
                Description: description

                """)
        append_file(
            os.path.join(path, "Packages"),
            package_stanza % {"name": name, "version": version})

    def test_no_system_packages(self):
        """
        If the dpkg status file is empty, not packages are reported by
        C{get_packages()}.
        """
        self.facade.reload_channels()
        self.assertEqual([], self.facade.get_packages())

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
            SHA256: f899cba22b79780dbe9bbbb802ff901b7e432425c264dc72e6bb20c0061e4f26
            Description: Summary1
             Description1
            """ % {"filename": PKGNAME1}),
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
        self.facade.reload_channels(True)
        self.assertEqual(
            ["bar", "foo"],
            sorted(version.package.name
                   for version in self.facade.get_packages()))

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
        """
        deb_dir = self.makeDir()
        create_simple_repository(deb_dir)
        self.facade.add_channel_deb_dir(deb_dir)
        self.facade.reload_channels()
        [pkg1] = self.facade.get_packages_by_name("name1")
        [pkg2] = self.facade.get_packages_by_name("name2")
        skeleton1 = self.facade.get_package_skeleton(pkg1)
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
        # inside the same second the directory's mtime will be the same)
        mtime = int(time.time() + 1)
        os.utime(packages_path, (mtime, mtime))

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
        [version_10, version_15] = self.facade.get_packages()
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
        self.facade.reload_channels()
        # XXX: This should return two packages, but it doesn't at the
        # moment. Bug #871641 should make this return ("foo", "1.5") as
        # well.
        self.assertEqual(
            [("foo", "1.0"), ("foo", "1.5")],
            sorted([(version.package.name, version.version)
                    for version in self.facade.get_packages_by_name("foo")]))


class SmartFacadeTest(LandscapeTest):

    helpers = [SmartFacadeHelper]

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
                                        repo.components)
        self.facade.reload_channels()

        pkgs = self.facade.get_packages()
        self.assertEqual(len(pkgs), 2)
        self.assertEqual(pkgs[0].name, "syslinux")
        self.assertEqual(pkgs[1].name, "kairos")

        self.facade.deinit()
        self.facade.set_arch("amd64")
        self.facade.reset_channels()
        self.facade.add_channel_apt_deb(repo.url, repo.codename,
                                        repo.components)
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
