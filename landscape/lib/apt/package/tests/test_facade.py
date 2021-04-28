from collections import namedtuple
import os
import sys
import textwrap
import tempfile
import unittest
import weakref

import apt
import apt_pkg
from apt.package import Package
from aptsources.sourceslist import SourcesList
from apt.cache import LockFailedException
import mock
from twisted.python.compat import unicode

from landscape.lib.fs import read_text_file, create_text_file
from landscape.lib import testing
from landscape.lib.apt.package.testing import (
    HASH1, HASH2, HASH3, PKGNAME1, PKGNAME2, PKGNAME3,
    PKGDEB1, PKGNAME_MINIMAL, PKGDEB_MINIMAL,
    create_deb, AptFacadeHelper,
    create_simple_repository)
from landscape.lib.apt.package.facade import (
    TransactionError, DependencyError, ChannelError, AptFacade,
    LandscapeInstallProgress)


_normalize_field = (lambda f: f.replace("-", "_").lower())
_DEB_STANZA_FIELDS = [_normalize_field(f) for f in [
        "Package",
        "Architecture",
        "Version",
        "Priority",
        "Section",
        "Maintainer",
        "Installed-Size",
        "Provides",
        "Pre-Depends",
        "Depends",
        "Recommends",
        "Suggests",
        "Conflicts",
        "Filename",
        "Size",
        "MD5sum",
        "SHA1",
        "SHA256",
        "Description",
        ]]
_DebStanza = namedtuple("DebStanza", _DEB_STANZA_FIELDS)


def _parse_deb_stanza(text):
    last = None
    data = {}
    for line in text.splitlines():
        field, sep, value = line.strip().partition(": ")
        if not sep:
            if not last:
                raise NotImplementedError
            data[last] += "\n" + line
            continue

        field = _normalize_field(field)
        if field in data:
            raise NotImplementedError
        data[field] = value
        last = field

    return _DebStanza(**data)


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


class TestCache(apt.cache.Cache):
    """An apt cache wrapper which we can tell has been updated.

    When updating the client to work with Xenial, apt.cache.Cache behaviour
    which tests depended on changed in such a way that we could no longer
    easily tell from the outside if the cache had been updated or not.  This
    wrapper was introduced to regain that ability.  See bug 1548946 for more
    information.
    """

    _update_called = False

    def update(self):
        self._update_called = True
        return super(TestCache, self).update()


class AptFacadeTest(testing.HelperTestCase, testing.FSTestCase,
                    unittest.TestCase):

    helpers = [AptFacadeHelper, testing.EnvironSaverHelper]

    def setUp(self):
        super(AptFacadeTest, self).setUp()
        self.facade.max_dpkg_retries = 0
        self.facade.dpkg_retry_sleep = 0

    def version_sortkey(self, version):
        """Return a key by which a Version object can be sorted."""
        return (version.package, version)

    def patch_cache_commit(self, commit_function=None):
        """Patch the apt cache's commit function as to not call dpkg.

        @param commit_function: A function accepting two parameters,
            fetch_progress and install_progress.
        """

        def commit(fetch_progress, install_progress):
            install_progress.dpkg_exited = True
            if commit_function:
                commit_function(fetch_progress, install_progress)

        self.facade._cache.commit = commit

    def test_default_root(self):
        """
        C{AptFacade} can be created by not providing a root directory,
        which means that the currently configured root (most likely /)
        will be used.
        """
        original_dpkg_root = apt_pkg.config.get("Dir")
        facade = AptFacade()
        self.assertEqual(original_dpkg_root, apt_pkg.config.get("Dir"))
        # Make sure that at least reloading the channels work.
        facade.reload_channels()

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
        self.facade.add_channel_apt_deb(
            "file://%s" % deb_dir, "./", trusted=True)
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
        self.facade.add_channel_apt_deb("http://example.com/ubuntu", "lucid")
        list_filename = (
            self.apt_root +
            "/etc/apt/sources.list.d/_landscape-internal-facade.list")
        sources_contents = read_text_file(list_filename)
        self.assertEqual(
            "deb http://example.com/ubuntu lucid\n",
            sources_contents)

    def test_add_channel_apt_deb_no_duplicate(self):
        """
        C{add_channel_apt_deb} doesn't put duplicate lines in the landscape
        internal apt sources list.
        """
        self.facade.add_channel_apt_deb("http://example.com/ubuntu", "lucid")
        self.facade.add_channel_apt_deb("http://example.com/ubuntu", "lucid")
        self.facade.add_channel_apt_deb("http://example.com/ubuntu", "lucid")
        list_filename = (
            self.apt_root +
            "/etc/apt/sources.list.d/_landscape-internal-facade.list")
        sources_contents = read_text_file(list_filename)
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
        sources_contents = read_text_file(list_filename)
        self.assertEqual(
            "deb http://example.com/ubuntu lucid main restricted\n",
            sources_contents)

    def test_add_channel_apt_deb_trusted(self):
        """add_channel_apt_deb sets trusted option if trusted and local."""
        # Don't override trust on unsigned/signed remotes.
        self.facade.add_channel_apt_deb(
            "http://example.com/ubuntu", "unsigned", ["main"], trusted=True)
        self.facade.add_channel_apt_deb(
            "http://example.com/ubuntu", "signed", ["main"], trusted=False)

        # We explicitly trust local
        self.facade.add_channel_apt_deb(
            "file://opt/spam", "unsigned", ["main"], trusted=True)
        # We explicitly distrust local (thus check gpg signatures)
        self.facade.add_channel_apt_deb(
            "file://opt/spam", "signed", ["main"], trusted=False)
        # apt defaults (which is to check signatures on >xenial)
        self.facade.add_channel_apt_deb(
            "file://opt/spam", "default", ["main"])

        list_filename = (
            self.apt_root +
            "/etc/apt/sources.list.d/_landscape-internal-facade.list")
        sources_contents = read_text_file(list_filename)
        self.assertEqual(
            textwrap.dedent("""\
            deb http://example.com/ubuntu unsigned main
            deb http://example.com/ubuntu signed main
            deb [ trusted=yes ] file://opt/spam unsigned main
            deb [ trusted=no ] file://opt/spam signed main
            deb file://opt/spam default main
            """),
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

    def test_clear_channels(self):
        """
        C{clear_channels} revoves all the channels added to the facade.
        It also removes the internal .list file.
        """
        deb_dir = self.makeDir()
        self.facade.add_channel_deb_dir(deb_dir)
        self.facade.add_channel_apt_deb("http://example.com/ubuntu", "lucid")
        self.facade.clear_channels()
        self.assertEqual([], self.facade.get_channels())
        self.assertFalse(
            os.path.exists(self.facade._get_internal_sources_list()))

    def test_clear_channels_no_channels(self):
        """
        If no channels have been added, C{clear_channels()} still succeeds.
        """
        self.facade.clear_channels()
        self.assertEqual([], self.facade.get_channels())

    def test_clear_channels_only_internal(self):
        """
        Only channels added through the facade are removed by
        C{clear_channels}. Other .list files in sources.list.d as well
        as the sources.list file are intact.
        """
        sources_list_file = apt_pkg.config.find_file("Dir::Etc::sourcelist")
        sources_list_d_file = os.path.join(
            apt_pkg.config.find_dir("Dir::Etc::sourceparts"), "example.list")
        create_text_file(
            sources_list_file, "deb http://example1.com/ubuntu lucid main")
        create_text_file(
            sources_list_d_file, "deb http://example2.com/ubuntu lucid main")

        self.facade.clear_channels()
        self.assertEqual(
            [{'baseurl': 'http://example1.com/ubuntu',
              'components': 'main', 'distribution': 'lucid', 'type': 'deb'},
             {'baseurl': 'http://example2.com/ubuntu',
              'components': 'main', 'distribution': 'lucid', 'type': 'deb'}],
            self.facade.get_channels())

    def test_write_package_stanza(self):
        """
        C{write_package_stanza} returns an entry for the package that can
        be included in a Packages file.
        """
        deb_dir = self.makeDir()
        create_deb(deb_dir, PKGNAME1, PKGDEB1)
        deb_file = os.path.join(deb_dir, PKGNAME1)
        packages_file = os.path.join(deb_dir, "Packages")
        with open(packages_file, "wb") as packages:
            self.facade.write_package_stanza(deb_file, packages)
        SHA256 = (
            "f899cba22b79780dbe9bbbb802ff901b7e432425c264dc72e6bb20c0061e4f26")
        expected = textwrap.dedent("""\
            Package: name1
            Architecture: all
            Version: version1-release1
            Priority: optional
            Section: Group1
            Maintainer: Gustavo Niemeyer <gustavo@niemeyer.net>
            Installed-Size: 28
            Provides: providesname1
            Pre-Depends: prerequirename1 (= prerequireversion1)
            Depends: requirename1 (= requireversion1)
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
            """ % {"filename": PKGNAME1, "sha256": SHA256})
        expected = _parse_deb_stanza(expected)
        stanza = _parse_deb_stanza(open(packages_file).read())
        self.assertEqual(expected, stanza)

    def test_add_channel_deb_dir_creates_packages_file(self):
        """
        C{add_channel_deb_dir} creates a Packages file in the directory
        with packages.
        """
        deb_dir = self.makeDir()
        create_simple_repository(deb_dir)
        self.facade.add_channel_deb_dir(deb_dir)
        packages_contents = read_text_file(os.path.join(deb_dir, "Packages"))
        stanzas = []
        for pkg_name in [PKGNAME1, PKGNAME2, PKGNAME3]:
            with open(self.makeFile(), "wb+", 0) as tmp:
                self.facade.write_package_stanza(
                    os.path.join(deb_dir, pkg_name), tmp)
                tmp.seek(0)
                stanzas.append(tmp.read().decode("utf-8"))
        expected_contents = "\n".join(stanzas)
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
        self.facade.add_channel_apt_deb(
            "file://%s" % deb_dir, "./", trusted=True)
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
        self.facade.add_channel_apt_deb(
            "file://%s" % deb_dir, "./", trusted=True)
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
        self.facade.add_channel_apt_deb(
            "file://%s" % deb_dir, "./", trusted=True)
        self.facade.reload_channels()
        new_facade = AptFacade(root=self.apt_root)
        self._add_package_to_deb_dir(deb_dir, "foo", version="2.0")
        self._touch_packages_file(deb_dir)
        new_facade.refetch_package_index = False
        new_facade._cache = TestCache(rootdir=new_facade._root)
        new_facade.reload_channels()
        self.assertFalse(new_facade._cache._update_called)

    def test_reload_channels_force_reload_binaries(self):
        """
        If C{force_reload_binaries} is True, reload_channels will
        refetch the Packages files in the channels and rebuild the
        internal database.
        """
        deb_dir = self.makeDir()
        self._add_package_to_deb_dir(deb_dir, "foo")
        self.facade.add_channel_apt_deb(
            "file://%s" % deb_dir, "./", trusted=True)
        self.facade.reload_channels()
        self._add_package_to_deb_dir(deb_dir, "bar")
        self._touch_packages_file(deb_dir)
        self.facade.refetch_package_index = False
        self.facade._cache = TestCache(rootdir=self.facade._root)
        self.facade.reload_channels(force_reload_binaries=True)
        self.assertTrue(self.facade._cache._update_called)

    def test_reload_channels_no_force_reload_binaries(self):
        """
        If C{force_reload_binaries} False, C{reload_channels} won't pass
        a sources_list parameter to limit to update to the internal
        repos only.
        """
        passed_in_lists = []

        def new_apt_update(sources_list=None):
            passed_in_lists.append(sources_list)

        self.facade.refetch_package_index = True
        self.facade._cache.update = new_apt_update
        self.facade.reload_channels(force_reload_binaries=False)
        self.assertEqual([None], passed_in_lists)

    def test_reload_channels_force_reload_binaries_no_internal_repos(self):
        """
        If C{force_reload_binaries} is True, but there are no internal
        repos, C{reload_channels} won't update the package index if
        C{refetch_package_index} is False.
        """
        passed_in_lists = []

        def apt_update(sources_list=None):
            passed_in_lists.append(sources_list)

        self.facade.refetch_package_index = False
        self.facade._cache.update = apt_update
        self.facade.reload_channels(force_reload_binaries=True)
        self.assertEqual([], passed_in_lists)

    def test_reload_channels_force_reload_binaries_refetch_package_index(self):
        """
        If C{refetch_package_index} is True, C{reload_channels} won't
        limit the update to the internal repos, even if
        C{force_reload_binaries} is specified.
        """
        passed_in_lists = []

        def new_apt_update(sources_list=None):
            passed_in_lists.append(sources_list)

        deb_dir = self.makeDir()
        self._add_package_to_deb_dir(deb_dir, "foo")
        self.facade.add_channel_apt_deb(
            "file://%s" % deb_dir, "./", trusted=True)
        self.facade.refetch_package_index = True
        self.facade._cache.update = new_apt_update
        self.facade.reload_channels(force_reload_binaries=True)
        self.assertEqual([None], passed_in_lists)

    def test_reload_channels_force_reload_binaries_new_apt(self):
        """
        If python-apt is new enough (i.e. the C{update()} method accepts
        a C{sources_list} parameter), the .list file containing the
        repos managed by the facade will be passed to C{update()}, so
        that only the internal repos are updated if
        C{force_reload_binaries} is specified.
        """
        passed_in_lists = []

        def new_apt_update(sources_list=None):
            passed_in_lists.append(sources_list)

        deb_dir = self.makeDir()
        self._add_package_to_deb_dir(deb_dir, "foo")
        self.facade.add_channel_apt_deb(
            "file://%s" % deb_dir, "./", trusted=True)
        self.facade.refetch_package_index = False
        self.facade._cache.update = new_apt_update
        self.facade.reload_channels(force_reload_binaries=True)
        self.assertEqual(
            [self.facade._get_internal_sources_list()], passed_in_lists)

    def test_reload_channels_force_reload_binaries_old_apt(self):
        """
        If python-apt is old (i.e. the C{update()} method doesn't accept
        a C{sources_list} parameter), everything will be updated if
        C{force_reload_binaries} is specified, since there is no API for
        limiting which repos should be updated.
        """
        passed_in_lists = []

        def old_apt_update():
            passed_in_lists.append(None)

        deb_dir = self.makeDir()
        self._add_package_to_deb_dir(deb_dir, "foo")
        self.facade.add_channel_apt_deb(
            "file://%s" % deb_dir, "./", trusted=True)
        self.facade.refetch_package_index = False
        self.facade._cache.update = old_apt_update
        self.facade.reload_channels(force_reload_binaries=True)
        self.assertEqual([None], passed_in_lists)

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

    def test_ensure_channels_reloaded_reload_channels(self):
        """
        C{ensure_channels_reloaded} doesn't refresh the channels if
        C{reload_chanels} have been called first.
        """
        self._add_system_package("foo")
        self.facade.reload_channels()
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
        with self.assertRaises(ChannelError):
            self.facade.reload_channels()

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
        pkg2 = weakref.ref(pkg2)
        pkg3 = weakref.ref(pkg3)

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

        # Only packages with name2 and name3 should be loaded, and they might
        # be the same objects if references were held, as apt-cache tries
        # not to re-create objects anymore.
        self.assertEqual(
            sorted([version.package.name
                    for version in self.facade.get_packages()]),
            ["name2", "name3"])
        # Those should have been collected.
        self.assertIsNone(pkg2())
        self.assertIsNone(pkg3())

        # The hash cache shouldn't include either of the old packages.
        self.assertEqual(self.facade.get_package_hash(pkg1), None)

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

    def test_is_package_autoremovable(self):
        """
        Check that auto packages without dependencies on them are correctly
        detected as being autoremovable.
        """
        self._add_system_package("dep")
        self._add_system_package("newdep")
        self._add_system_package("foo", control_fields={"Depends": "newdep"})
        self.facade.reload_channels()
        dep, = sorted(self.facade.get_packages_by_name("dep"))
        dep.package.mark_auto(True)
        # dep should not be explicitely installed
        dep.package.mark_install(False)
        newdep, = sorted(self.facade.get_packages_by_name("newdep"))
        newdep, = sorted(self.facade.get_packages_by_name("newdep"))
        newdep.package.mark_auto(True)
        self.assertTrue(dep.package.is_installed)
        self.assertTrue(dep.package.is_auto_installed)
        self.assertTrue(newdep.package.is_installed)
        self.assertTrue(dep.package.is_auto_installed)

        self.assertTrue(self.facade.is_package_autoremovable(dep))
        self.assertFalse(self.facade.is_package_autoremovable(newdep))

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
        self.facade.add_channel_apt_deb(
            "file://%s" % deb_dir, "./", trusted=True)
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
        self.facade.add_channel_apt_deb(
            "file://%s" % deb_dir, "./", trusted=True)
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
        self.facade.add_channel_apt_deb(
            "file://%s" % deb_dir, "./", trusted=True)
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
        self.facade.add_channel_apt_deb(
            "file://%s" % deb_dir, "./", trusted=True)
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

    def test_is_package_upgrade_with_apt_preferences(self):
        """
        A package is not considered to be an upgrade if the package has
        a higher version of an installed package, but it's being held back
        because of APT pinning.
        """
        # Create an APT preferences file that assigns a very low priority
        # to all local packages.
        self.makeFile(
            content="Package: *\nPin: origin \"\"\nPin-priority: 10\n",
            path=os.path.join(self.apt_root, "etc", "apt", "preferences"))
        self._add_system_package("foo", version="0.5")
        deb_dir = self.makeDir()
        self._add_package_to_deb_dir(deb_dir, "foo", version="1.0")
        self.facade.add_channel_apt_deb(
            "file://%s" % deb_dir, "./", trusted=True)
        self.facade.reload_channels()
        [version_05, version_10] = sorted(self.facade.get_packages())
        self.assertFalse(self.facade.is_package_upgrade(version_10))

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
        self.facade.add_channel_apt_deb(
            "file://%s" % deb_dir, "./", trusted=True)
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
        self.assertEqual("none", os.environ["APT_LISTCHANGES_FRONTEND"])
        self.assertEqual("none", os.environ["APT_LISTBUGS_FRONTEND"])
        self.assertEqual("noninteractive", os.environ["DEBIAN_FRONTEND"])
        self.assertEqual(["--force-confold"],
                         apt_pkg.config.value_list("DPkg::options"))

    def test_perform_changes_with_path(self):
        """
        perform_changes() doesn't set C{PATH} if it's set already.
        """
        os.environ["PATH"] = "custom-path"
        self.facade.reload_channels()
        self.assertEqual(self.facade.perform_changes(), None)
        self.assertEqual("custom-path", os.environ["PATH"])

    def test_perform_changes_fetch_progress(self):
        """
        C{perform_changes()} captures the fetch output and returns it.
        """
        deb_dir = self.makeDir()
        self._add_package_to_deb_dir(deb_dir, "foo")
        self.facade.add_channel_apt_deb(
            "file://%s" % deb_dir, "./", trusted=True)
        self.facade.reload_channels()
        [foo] = self.facade.get_packages_by_name("foo")
        self.facade.mark_install(foo)
        fetch_item = FakeFetchItem(
            FakeOwner(1234, error_text="Some error"), "foo package")

        def output_progress(fetch_progress, install_progress):
            fetch_progress.start()
            fetch_progress.fetch(fetch_item)
            fetch_progress.fail(fetch_item)
            fetch_progress.done(fetch_item)
            fetch_progress.stop()

        self.patch_cache_commit(output_progress)
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
        self.facade.add_channel_apt_deb(
            "file://%s" % deb_dir, "./", trusted=True)
        self.facade.reload_channels()
        [foo] = self.facade.get_packages_by_name("foo")
        self.facade.mark_install(foo)

        def print_output(fetch_progress, install_progress):
            os.write(1, b"Stdout output\n")
            os.write(2, b"Stderr output\n")
            os.write(1, b"Stdout output again\n")

        self.patch_cache_commit(print_output)
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
        self.facade.add_channel_apt_deb(
            "file://%s" % deb_dir, "./", trusted=True)
        self.facade.reload_channels()
        [foo] = self.facade.get_packages_by_name("foo")
        self.facade.mark_install(foo)

        def commit(fetch_progress, install_progress):
            os.write(1, b"Stdout output\n")
            os.write(2, b"Stderr output\n")
            os.write(1, b"Stdout output again\n")
            raise SystemError("Oops")

        self.facade._cache.commit = commit
        with self.assertRaises(TransactionError) as cm:
            self.facade.perform_changes()
        output = [
            line.rstrip()
            for line in cm.exception.args[0].splitlines() if line.strip()]
        self.assertEqual(
            ["Oops", "Package operation log:", "Stdout output",
             "Stderr output", "Stdout output again"],
            output)

    def test_retry_changes_lock_failed(self):
        """
        Test that changes are retried with the given exception type.
        """
        self.facade.max_dpkg_retries = 1
        deb_dir = self.makeDir()
        self._add_package_to_deb_dir(deb_dir, "foo")
        self.facade.add_channel_apt_deb(
            "file://%s" % deb_dir, "./", trusted=True)
        self.facade.reload_channels()
        [foo] = self.facade.get_packages_by_name("foo")
        self.facade.mark_install(foo)

        def commit1(fetch_progress, install_progress):
            self.facade._cache.commit = commit2
            os.write(2, b"bad stuff!\n")
            raise LockFailedException("Oops")

        def commit2(fetch_progress, install_progress):
            install_progress.dpkg_exited = True
            os.write(1, b"good stuff!")

        self.facade._cache.commit = commit1
        output = [
            line.rstrip()
            for line in self.facade.perform_changes().splitlines()
            if line.strip()]
        self.assertEqual(["bad stuff!", "good stuff!"], output)

    def test_retry_changes_system_error(self):
        """
        Changes are not retried in the event of a SystemError, since
        it's most likely a permanent error.
        """
        self.facade.max_dpkg_retries = 1
        deb_dir = self.makeDir()
        self._add_package_to_deb_dir(deb_dir, "foo")
        self.facade.add_channel_apt_deb(
            "file://%s" % deb_dir, "./", trusted=True)
        self.facade.reload_channels()
        [foo] = self.facade.get_packages_by_name("foo")
        self.facade.mark_install(foo)

        def commit1(fetch_progress, install_progress):
            self.facade._cache.commit = commit2
            os.write(2, b"bad stuff!\n")
            raise SystemError("Oops")

        def commit2(fetch_progress, install_progress):
            install_progress.dpkg_exited = True
            os.write(1, b"good stuff!")

        self.facade._cache.commit = commit1
        with self.assertRaises(TransactionError):
            self.facade.perform_changes()

    def test_perform_changes_dpkg_error_real(self):
        """
        C{perform_changes()} detects whether the dpkg call fails and
        raises a C{TransactionError}.

        This test executes dpkg for real, which should fail, complaining
        that superuser privileges are needed.

        The error from the dpkg sub process is included.
        """
        self._add_system_package("foo")
        self.facade.reload_channels()
        foo = self.facade.get_packages_by_name("foo")[0]
        self.facade.mark_remove(foo)
        with self.assertRaises(TransactionError):
            self.facade.perform_changes()

    def test_perform_changes_dpkg_error_retains_excepthook(self):
        """
        We install a special excepthook when preforming package
        operations, to prevent Apport from generating crash reports when
        dpkg returns a failure. It's only installed when doing the
        actual package operation, so the original excepthook is there
        after the perform_changes() method returns.
        """
        old_excepthook = sys.excepthook
        self._add_system_package("foo")
        self.facade.reload_channels()
        foo = self.facade.get_packages_by_name("foo")[0]
        self.facade.mark_remove(foo)
        with self.assertRaises(TransactionError):
            self.facade.perform_changes()
        self.assertIs(old_excepthook, sys.excepthook)

    def test_prevent_dpkg_apport_error_system_error(self):
        """
        C{_prevent_dpkg_apport_error} prevents the Apport excepthook
        from being called when a SystemError happens, since SystemErrors
        are expected to happen and will be caught in the Apt C binding..
        """
        hook_calls = []

        progress = LandscapeInstallProgress()
        progress.old_excepthook = (
            lambda exc_type, exc_value, exc_tb: hook_calls.append(
                (exc_type, exc_value, exc_tb)))
        progress._prevent_dpkg_apport_error(
            SystemError, SystemError("error"), object())
        self.assertEqual([], hook_calls)

    def test_prevent_dpkg_apport_error_system_error_calls_system_hook(self):
        """
        C{_prevent_dpkg_apport_error} prevents the Apport excepthook
        from being called when a SystemError happens, but it does call
        the system except hook, which is the one that was in place
        before apport installed a custom one. This makes the exception
        to be printed to stderr.
        """
        progress = LandscapeInstallProgress()
        with mock.patch("sys.__excepthook__") as sys_except_hook:
            error = SystemError("error")
            tb = object()
            progress._prevent_dpkg_apport_error(SystemError, error, tb)
            sys_except_hook.assert_called_once_with(SystemError, error, tb)

    def test_prevent_dpkg_apport_error_non_system_error(self):
        """
        If C{_prevent_dpkg_apport_error} gets an exception that isn't a
        SystemError, the old Apport hook is being called.
        """
        hook_calls = []

        progress = LandscapeInstallProgress()
        progress.old_excepthook = (
            lambda exc_type, exc_value, exc_tb: hook_calls.append(
                (exc_type, exc_value, exc_tb)))
        error = object()
        traceback = object()
        progress._prevent_dpkg_apport_error(Exception, error, traceback)
        self.assertEqual([(Exception, error, traceback)], hook_calls)

    def test_perform_changes_dpkg_exit_dirty(self):
        """
        C{perform_changes()} checks whether dpkg exited cleanly and
        raises a TransactionError if it didn't.
        """
        deb_dir = self.makeDir()
        self._add_package_to_deb_dir(deb_dir, "foo")
        self.facade.add_channel_apt_deb(
            "file://%s" % deb_dir, "./", trusted=True)
        self.facade.reload_channels()
        foo = self.facade.get_packages_by_name("foo")[0]
        self.facade.mark_install(foo)

        def commit(fetch_progress, install_progress):
            install_progress.dpkg_exited = False
            os.write(1, b"Stdout output\n")

        self.facade._cache.commit = commit
        with self.assertRaises(TransactionError) as cm:
            self.facade.perform_changes()
        output = [
            line.rstrip()
            for line in cm.exception.args[0].splitlines()if line.strip()]
        self.assertEqual(
            ["dpkg didn't exit cleanly.", "Package operation log:",
             "Stdout output"],
            output)

    def test_perform_changes_install_broken_includes_error_info(self):
        """
        If some packages are broken and can't be installed, information
        about the unmet dependencies is included in the error message
        that C{perform_changes()} will raise.
        """
        deb_dir = self.makeDir()
        self._add_package_to_deb_dir(
            deb_dir, "foo",
            control_fields={"Depends": "missing | lost (>= 1.0)",
                            "Pre-Depends": "pre-missing | pre-lost"})
        self._add_package_to_deb_dir(
            deb_dir, "bar",
            control_fields={"Depends": "also-missing | also-lost (>= 1.0)",
                            "Pre-Depends": "also-pre-missing | also-pre-lost"})
        self.facade.add_channel_apt_deb(
            "file://%s" % deb_dir, "./", trusted=True)
        self.facade.reload_channels()
        [foo] = self.facade.get_packages_by_name("foo")
        [bar] = self.facade.get_packages_by_name("bar")
        self.facade.mark_install(foo)
        self.facade.mark_install(bar)
        self.patch_cache_commit()
        with self.assertRaises(TransactionError) as cm:
            self.facade.perform_changes()
        self.assertEqual(
            ["The following packages have unmet dependencies:",
             "  bar: PreDepends: also-pre-missing but is not installable or",
             "                   also-pre-lost but is not installable",
             "  bar: Depends: also-missing but is not installable or",
             "                also-lost (>= 1.0) but is not installable",
             "  foo: PreDepends: pre-missing but is not installable or",
             "                   pre-lost but is not installable",
             "  foo: Depends: missing but is not installable or",
             "                lost (>= 1.0) but is not installable"],
            cm.exception.args[0].splitlines()[-9:])

    def test_get_broken_packages_already_installed(self):
        """
        Trying to install a package that is already installed is a noop,
        not causing any packages to be broken.
        """
        self._add_system_package("foo")
        self.facade.reload_channels()
        [foo] = self.facade.get_packages_by_name("foo")
        self.facade.mark_install(foo)
        self.facade._preprocess_package_changes()
        self.assertEqual(set(), self.facade._get_broken_packages())

    def test_get_unmet_dependency_info_no_broken(self):
        """
        If there are no broken packages, C{_get_unmet_dependency_info}
        returns no dependency information.
        """
        deb_dir = self.makeDir()
        self._add_package_to_deb_dir(
            deb_dir, "foo", control_fields={"Depends": "bar"})
        self.facade.add_channel_apt_deb(
            "file://%s" % deb_dir, "./", trusted=True)
        self.facade.reload_channels()
        self.assertEqual(set(), self.facade._get_broken_packages())
        self.assertEqual("", self.facade._get_unmet_dependency_info())

    def test_get_unmet_dependency_info_depend(self):
        """
        If a C{Depends} dependency is unmet,
        C{_get_unmet_dependency_info} returns information about it,
        including the dependency type.
        """
        deb_dir = self.makeDir()
        self._add_package_to_deb_dir(
            deb_dir, "foo", control_fields={"Depends": "bar"})
        self.facade.add_channel_apt_deb(
            "file://%s" % deb_dir, "./", trusted=True)
        self.facade.reload_channels()
        [foo] = self.facade.get_packages_by_name("foo")
        self.facade.mark_install(foo)
        with self.assertRaises(TransactionError):
            self.facade._preprocess_package_changes()
        self.assertEqual(
            set([foo.package]), self.facade._get_broken_packages())
        self.assertEqual(
            ["The following packages have unmet dependencies:",
             "  foo: Depends: bar but is not installable"],
            self.facade._get_unmet_dependency_info().splitlines())

    def test_get_unmet_dependency_info_predepend(self):
        """
        If a C{Pre-Depends} dependency is unmet,
        C{_get_unmet_dependency_info} returns information about it,
        including the dependency type.
        """
        deb_dir = self.makeDir()
        self._add_package_to_deb_dir(
            deb_dir, "foo", control_fields={"Pre-Depends": "bar"})
        self.facade.add_channel_apt_deb(
            "file://%s" % deb_dir, "./", trusted=True)
        self.facade.reload_channels()
        [foo] = self.facade.get_packages_by_name("foo")
        self.facade.mark_install(foo)
        with self.assertRaises(TransactionError):
            self.facade._preprocess_package_changes()
        self.assertEqual(
            set([foo.package]), self.facade._get_broken_packages())
        self.assertEqual(
            ["The following packages have unmet dependencies:",
             "  foo: PreDepends: bar but is not installable"],
            self.facade._get_unmet_dependency_info().splitlines())

    def test_get_unmet_dependency_info_with_version(self):
        """
        If an unmet dependency includes a version relation, it's
        included in the error information from
        C{_get_unmet_dependency_info}.
        """
        deb_dir = self.makeDir()
        self._add_package_to_deb_dir(
            deb_dir, "foo", control_fields={"Depends": "bar (>= 1.0)"})
        self.facade.add_channel_apt_deb(
            "file://%s" % deb_dir, "./", trusted=True)
        self.facade.reload_channels()
        [foo] = self.facade.get_packages_by_name("foo")
        self.facade.mark_install(foo)
        with self.assertRaises(TransactionError):
            self.facade._preprocess_package_changes()
        self.assertEqual(
            set([foo.package]), self.facade._get_broken_packages())
        self.assertEqual(
            ["The following packages have unmet dependencies:",
             "  foo: Depends: bar (>= 1.0) but is not installable"],
            self.facade._get_unmet_dependency_info().splitlines())

    def test_get_unmet_dependency_info_with_dep_install(self):
        """
        If an unmet dependency is being installed (but still doesn't
        meet the vesion requirements), the version being installed is
        included in the error information from
        C{_get_unmet_dependency_info}.
        """
        deb_dir = self.makeDir()
        self._add_package_to_deb_dir(deb_dir, "bar", version="0.5")
        self._add_package_to_deb_dir(
            deb_dir, "foo", control_fields={"Depends": "bar (>= 1.0)"})
        self.facade.add_channel_apt_deb(
            "file://%s" % deb_dir, "./", trusted=True)
        self.facade.reload_channels()
        [foo] = self.facade.get_packages_by_name("foo")
        [bar] = self.facade.get_packages_by_name("bar")
        self.facade.mark_install(foo)
        self.facade.mark_install(bar)
        with self.assertRaises(TransactionError):
            self.facade._preprocess_package_changes()
        self.assertEqual(
            set([foo.package]), self.facade._get_broken_packages())
        self.assertEqual(
            ["The following packages have unmet dependencies:",
             "  foo: Depends: bar (>= 1.0) but 0.5 is to be installed"],
            self.facade._get_unmet_dependency_info().splitlines())

    def test_get_unmet_dependency_info_with_dep_already_installed(self):
        """
        If an unmet dependency is already installed (but still doesn't
        meet the vesion requirements), the version that is installed is
        included in the error information from
        C{_get_unmet_dependency_info}.
        """
        deb_dir = self.makeDir()
        self._add_system_package("bar", version="1.0")
        self._add_package_to_deb_dir(
            deb_dir, "foo", control_fields={"Depends": "bar (>= 3.0)"})
        self._add_package_to_deb_dir(deb_dir, "bar", version="2.0")
        self.facade.add_channel_apt_deb(
            "file://%s" % deb_dir, "./", trusted=True)
        self.facade.reload_channels()
        [foo] = self.facade.get_packages_by_name("foo")
        [bar1, bar2] = sorted(self.facade.get_packages_by_name("bar"))
        self.assertEqual(bar2, bar1.package.candidate)
        self.facade.mark_install(foo)
        with self.assertRaises(TransactionError):
            self.facade._preprocess_package_changes()
        self.assertEqual(
            set([foo.package]), self.facade._get_broken_packages())
        self.assertEqual(
            ["The following packages have unmet dependencies:",
             "  foo: Depends: bar (>= 3.0) but 1.0 is to be installed"],
            self.facade._get_unmet_dependency_info().splitlines())

    def test_get_unmet_dependency_info_with_dep_upgraded(self):
        """
        If an unmet dependency is being upgraded (but still doesn't meet
        the vesion requirements), the version that it is upgraded to is
        included in the error information from
        C{_get_unmet_dependency_info}.
        """
        deb_dir = self.makeDir()
        self._add_system_package("bar", version="1.0")
        self._add_package_to_deb_dir(
            deb_dir, "foo", control_fields={"Depends": "bar (>= 3.0)"})
        self._add_package_to_deb_dir(deb_dir, "bar", version="2.0")
        self.facade.add_channel_apt_deb(
            "file://%s" % deb_dir, "./", trusted=True)
        self.facade.reload_channels()
        [foo] = self.facade.get_packages_by_name("foo")
        [bar1, bar2] = sorted(self.facade.get_packages_by_name("bar"))
        self.assertEqual(bar2, bar1.package.candidate)
        self.facade.mark_install(foo)
        self.facade.mark_install(bar2)
        self.facade.mark_remove(bar1)
        with self.assertRaises(TransactionError):
            self.facade._preprocess_package_changes()
        self.assertEqual(
            set([foo.package]), self.facade._get_broken_packages())
        self.assertEqual(
            ["The following packages have unmet dependencies:",
             "  foo: Depends: bar (>= 3.0) but 2.0 is to be installed"],
            self.facade._get_unmet_dependency_info().splitlines())

    def test_get_unmet_dependency_info_with_dep_downgraded(self):
        """
        If an unmet dependency is being downgraded (but still doesn't meet
        the vesion requirements), the version that it is downgraded to is
        included in the error information from
        C{_get_unmet_dependency_info}.
        """
        deb_dir = self.makeDir()
        self._add_system_package("bar", version="2.0")
        self._add_package_to_deb_dir(
            deb_dir, "foo", control_fields={"Depends": "bar (>= 3.0)"})
        self._add_package_to_deb_dir(deb_dir, "bar", version="1.0")
        self.facade.add_channel_apt_deb(
            "file://%s" % deb_dir, "./", trusted=True)
        self.facade.reload_channels()
        [foo] = self.facade.get_packages_by_name("foo")
        [bar1, bar2] = sorted(self.facade.get_packages_by_name("bar"))
        self.assertEqual(bar2, bar1.package.candidate)
        self.facade.mark_install(foo)
        self.facade.mark_install(bar1)
        self.facade.mark_remove(bar2)
        with self.assertRaises(TransactionError):
            self.facade._preprocess_package_changes()
        self.assertEqual(
            set([foo.package]), self.facade._get_broken_packages())
        self.assertEqual(
            ["The following packages have unmet dependencies:",
             "  foo: Depends: bar (>= 3.0) but 1.0 is to be installed"],
            self.facade._get_unmet_dependency_info().splitlines())

    def test_get_unmet_dependency_info_with_or_deps(self):
        """
        If an unmet dependency includes an or relation, all of the
        possible options are included in the error information from
        C{_get_unmet_dependency_info}.
        """
        deb_dir = self.makeDir()
        self._add_package_to_deb_dir(
            deb_dir, "foo", control_fields={"Depends": "bar | baz (>= 1.0)"})
        self.facade.add_channel_apt_deb(
            "file://%s" % deb_dir, "./", trusted=True)
        self.facade.reload_channels()
        [foo] = self.facade.get_packages_by_name("foo")
        self.facade.mark_install(foo)
        with self.assertRaises(TransactionError):
            self.facade._preprocess_package_changes()
        self.assertEqual(
            set([foo.package]), self.facade._get_broken_packages())
        self.assertEqual(
            ["The following packages have unmet dependencies:",
             "  foo: Depends: bar but is not installable or",
             "                baz (>= 1.0) but is not installable"],
            self.facade._get_unmet_dependency_info().splitlines())

    def test_get_unmet_dependency_info_with_conflicts(self):
        """
        If a package is broken because it conflicts with a package to be
        installed, information about the conflict is included in the
        error information from C{_get_unmet_dependency_info}.
        """
        deb_dir = self.makeDir()
        self._add_system_package("foo")
        self._add_package_to_deb_dir(
            deb_dir, "bar", control_fields={"Conflicts": "foo"})
        self.facade.add_channel_apt_deb(
            "file://%s" % deb_dir, "./", trusted=True)
        self.facade.reload_channels()
        [foo] = self.facade.get_packages_by_name("foo")
        [bar] = self.facade.get_packages_by_name("bar")
        self.facade.mark_install(bar)
        # Mark as keep to ensure it stays broken and isn't automatically
        # removed by the resolver.
        self.facade._preprocess_package_changes()
        foo.package.mark_keep()
        self.assertEqual(
            set([bar.package]), self.facade._get_broken_packages())
        self.assertEqual(
            ["The following packages have unmet dependencies:",
             "  bar: Conflicts: foo but 1.0 is to be installed"],
            self.facade._get_unmet_dependency_info().splitlines())

    def test_get_unmet_dependency_info_with_breaks(self):
        """
        If a package is broken because it breaks a package to be
        installed, information about the conflict is included in the
        error information from C{_get_unmet_dependency_info}.
        """
        deb_dir = self.makeDir()
        self._add_package_to_deb_dir(
            deb_dir, "foo", control_fields={"Depends": "bar"})
        self._add_package_to_deb_dir(
            deb_dir, "bar", control_fields={"Breaks": "foo"})
        self.facade.add_channel_apt_deb(
            "file://%s" % deb_dir, "./", trusted=True)
        self.facade.reload_channels()
        [foo] = self.facade.get_packages_by_name("foo")
        [bar] = self.facade.get_packages_by_name("bar")
        self.facade.mark_install(foo)
        with self.assertRaises(TransactionError):
            self.facade._preprocess_package_changes()
        self.assertEqual(
            set([foo.package]), self.facade._get_broken_packages())
        self.assertEqual(
            ["The following packages have unmet dependencies:",
             "  foo: Depends: bar but is not installable"],
            self.facade._get_unmet_dependency_info().splitlines())

    def test_get_unmet_dependency_info_with_conflicts_not_installed(self):
        """
        If a broken package conflicts or breaks a package that isn't
        installed or marked for installation, information about that
        conflict isn't reported by C{_get_unmet_dependency_info}.
        """
        deb_dir = self.makeDir()
        self._add_system_package("foo")
        self._add_package_to_deb_dir(
            deb_dir, "bar",
            control_fields={"Conflicts": "foo, baz", "Breaks": "foo, baz"})
        self._add_package_to_deb_dir(deb_dir, "baz")
        self.facade.add_channel_apt_deb(
            "file://%s" % deb_dir, "./", trusted=True)
        self.facade.reload_channels()
        [foo] = self.facade.get_packages_by_name("foo")
        [bar] = self.facade.get_packages_by_name("bar")
        self.facade.mark_install(bar)
        self.facade._preprocess_package_changes()
        # Mark as keep to ensure it stays broken and isn't automatically
        # removed by the resolver.
        foo.package.mark_keep()
        self.assertEqual(
            set([bar.package]), self.facade._get_broken_packages())
        self.assertEqual(
            ["The following packages have unmet dependencies:",
             "  bar: Conflicts: foo but 1.0 is to be installed",
             "  bar: Breaks: foo but 1.0 is to be installed"],
            self.facade._get_unmet_dependency_info().splitlines())

    def test_get_unmet_dependency_info_with_conflicts_marked_delete(self):
        """
        If a broken package conflicts or breaks an installed package
        that is marekd for removal, information about that conflict
        isn't reported by C{_get_unmet_dependency_info}.
        """
        deb_dir = self.makeDir()
        self._add_system_package("foo")
        self._add_package_to_deb_dir(
            deb_dir, "bar",
            control_fields={"Conflicts": "foo, baz", "Breaks": "foo, baz"})
        self._add_system_package("baz")
        self.facade.add_channel_apt_deb(
            "file://%s" % deb_dir, "./", trusted=True)
        self.facade.reload_channels()
        [foo] = self.facade.get_packages_by_name("foo")
        [bar] = self.facade.get_packages_by_name("bar")
        [baz] = self.facade.get_packages_by_name("baz")
        self.facade.mark_remove(baz)
        self.facade.mark_install(bar)
        self.facade._preprocess_package_changes()
        # Mark as keep to ensure it stays broken and isn't automatically
        # removed by the resolver.
        foo.package.mark_keep()
        self.assertEqual(
            set([bar.package]), self.facade._get_broken_packages())
        self.assertEqual(
            ["The following packages have unmet dependencies:",
             "  bar: Conflicts: foo but 1.0 is to be installed",
             "  bar: Breaks: foo but 1.0 is to be installed"],
            self.facade._get_unmet_dependency_info().splitlines())

    def test_get_unmet_dependency_info_only_unmet(self):
        """
        If a broken packages have some dependencies that are being
        fulfilled, those aren't included in the error information from
        C{_get_unmet_dependency_info}.
        """
        deb_dir = self.makeDir()
        self._add_system_package("there1")
        self._add_system_package("there2")
        self._add_package_to_deb_dir(
            deb_dir, "foo",
            control_fields={"Depends": "there1, missing1, there2 | missing2"})
        self.facade.add_channel_apt_deb(
            "file://%s" % deb_dir, "./", trusted=True)
        self.facade.reload_channels()
        [foo] = self.facade.get_packages_by_name("foo")
        self.facade.mark_install(foo)
        with self.assertRaises(TransactionError):
            self.facade._preprocess_package_changes()
        self.assertEqual(
            set([foo.package]), self.facade._get_broken_packages())
        self.assertEqual(
            ["The following packages have unmet dependencies:",
             "  foo: Depends: missing1 but is not installable"],
            self.facade._get_unmet_dependency_info().splitlines())

    def test_get_unmet_dependency_info_multiple_broken(self):
        """
        If multiple packages are broken, all broken packages are listed
        in the error information from C{_get_unmet_dependency_info}.
        """
        deb_dir = self.makeDir()
        self._add_package_to_deb_dir(
            deb_dir, "foo", control_fields={"Depends": "bar"})
        self._add_package_to_deb_dir(
            deb_dir, "another-foo", control_fields={"Depends": "another-bar"})
        self.facade.add_channel_apt_deb(
            "file://%s" % deb_dir, "./", trusted=True)
        self.facade.reload_channels()
        [foo] = self.facade.get_packages_by_name("foo")
        [another_foo] = self.facade.get_packages_by_name("another-foo")
        self.facade.mark_install(foo)
        self.facade.mark_install(another_foo)
        with self.assertRaises(TransactionError):
            self.facade._preprocess_package_changes()
        self.assertEqual(
            set([foo.package, another_foo.package]),
            self.facade._get_broken_packages())
        self.assertEqual(
            ["The following packages have unmet dependencies:",
             "  another-foo: Depends: another-bar but is not installable",
             "  foo: Depends: bar but is not installable"],
            self.facade._get_unmet_dependency_info().splitlines())

    def test_get_unmet_dependency_info_unknown(self):
        """
        If a package is broken but fulfills all PreDepends, Depends,
        Conflicts and Breaks dependencies, C{_get_unmet_dependency_info}
        reports that that package has an unknown dependency error, since
        we don't know why it's broken.
        """
        self._add_system_package("foo")
        self.facade.reload_channels()
        [foo] = self.facade.get_packages_by_name("foo")
        self.facade._version_installs.append(foo)
        self.facade._get_broken_packages = lambda: set([foo.package])
        self.assertEqual(
            ["The following packages have unmet dependencies:",
             "  foo: Unknown dependency error"],
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
        mkstemp_patcher = mock.patch("tempfile.mkstemp")
        mock_mkstemp = mkstemp_patcher.start()
        self.addCleanup(mkstemp_patcher.stop)
        mock_mkstemp.return_value = (fd, outfile)

        dup_patcher = mock.patch("os.dup")
        mock_dup = dup_patcher.start()
        self.addCleanup(dup_patcher.stop)
        mock_dup.side_effect = lambda fd: {1: old_stdout, 2: old_stderr}[fd]

        dup2_patcher = mock.patch("os.dup2", wraps=os.dup2)
        mock_dup2 = dup2_patcher.start()
        self.addCleanup(dup2_patcher.stop)
        return outfile, mock_dup2

    def test_perform_changes_dpkg_output_reset(self):
        """
        C{perform_changes()} resets stdout and stderr after the cache commit.
        """
        deb_dir = self.makeDir()
        self._add_package_to_deb_dir(deb_dir, "foo")
        self.facade.add_channel_apt_deb(
            "file://%s" % deb_dir, "./", trusted=True)
        self.facade.reload_channels()
        [foo] = self.facade.get_packages_by_name("foo")
        self.facade.mark_install(foo)

        outfile, mock_dup2 = self._mock_output_restore()
        self.patch_cache_commit()
        self.facade.perform_changes()
        # Make sure we don't leave the tempfile behind.
        self.assertFalse(os.path.exists(outfile))
        mock_dup2.assert_any_call(mock.ANY, 1)
        mock_dup2.assert_any_call(mock.ANY, 2)

    def test_perform_changes_dpkg_output_reset_error(self):
        """
        C{perform_changes()} resets stdout and stderr after the cache
        commit, even if commit raises an error.
        """
        deb_dir = self.makeDir()
        self._add_package_to_deb_dir(deb_dir, "foo")
        self.facade.add_channel_apt_deb(
            "file://%s" % deb_dir, "./", trusted=True)
        self.facade.reload_channels()
        [foo] = self.facade.get_packages_by_name("foo")
        self.facade.mark_install(foo)

        outfile, mock_dup2 = self._mock_output_restore()

        def commit(fetch_progress, install_progress):
            raise SystemError("Error")

        self.facade._cache.commit = commit
        with self.assertRaises(TransactionError):
            self.facade.perform_changes()
        # Make sure we don't leave the tempfile behind.
        self.assertFalse(os.path.exists(outfile))
        mock_dup2.assert_any_call(mock.ANY, 1)
        mock_dup2.assert_any_call(mock.ANY, 2)

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
        self.facade.add_channel_apt_deb(
            "file://%s" % deb_dir, "./", trusted=True)
        self._add_system_package("quux", version="1.0")
        self._add_system_package("wibble", version="1.0")
        self.facade.reload_channels()
        [foo] = self.facade.get_packages_by_name("foo")
        self.facade.mark_install(foo)
        self.facade.mark_global_upgrade()
        [baz] = self.facade.get_packages_by_name("baz")
        self.facade.mark_remove(baz)
        [quux] = self.facade.get_packages_by_name("quux")
        self.facade.mark_hold(quux)
        [wibble] = self.facade.get_packages_by_name("wibble")
        self.facade.mark_remove_hold(wibble)
        self.facade.reset_marks()
        self.assertEqual(self.facade._version_installs, [])
        self.assertEqual(self.facade._version_removals, [])
        self.assertFalse(self.facade._global_upgrade)
        self.assertEqual(self.facade._version_hold_creations, [])
        self.assertEqual(self.facade._version_hold_removals, [])
        self.assertEqual(self.facade.perform_changes(), None)

    def test_reset_marks_resets_cache(self):
        """
        C{reset_marks()} clears the apt cache, so that no changes will
        be pending.
        """
        deb_dir = self.makeDir()
        self._add_package_to_deb_dir(
            deb_dir, "foo", control_fields={"Depends": "bar"})
        self._add_package_to_deb_dir(deb_dir, "bar")
        self.facade.add_channel_apt_deb(
            "file://%s" % deb_dir, "./", trusted=True)
        self.facade.reload_channels()
        [foo] = self.facade.get_packages_by_name("foo")
        self.facade.mark_install(foo)
        with self.assertRaises(DependencyError):
            self.facade.perform_changes()
        self.assertNotEqual([], list(self.facade._cache.get_changes()))
        self.facade.reset_marks()
        self.assertEqual([], list(self.facade._cache.get_changes()))

    def test_wb_mark_install_adds_to_list(self):
        """
        C{mark_install} adds the package to the list of packages to be
        installed.
        """
        deb_dir = self.makeDir()
        create_deb(deb_dir, PKGNAME_MINIMAL, PKGDEB_MINIMAL)
        self.facade.add_channel_deb_dir(deb_dir)
        self.facade.reload_channels()
        [pkg] = self.facade.get_packages_by_name("minimal")
        self.facade.mark_install(pkg)
        self.assertEqual(1, len(self.facade._version_installs))
        [install] = self.facade._version_installs
        self.assertEqual("minimal", install.package.name)

    def test_wb_mark_global_upgrade_sets_variable(self):
        """
        C{mark_global_upgrade} sets a variable, so that the actual
        upgrade happens in C{perform_changes}.
        """
        deb_dir = self.makeDir()
        self._add_system_package("foo", version="1.0")
        self._add_package_to_deb_dir(deb_dir, "foo", version="1.5")
        self.facade.add_channel_apt_deb(
            "file://%s" % deb_dir, "./", trusted=True)
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
        self.facade.add_channel_apt_deb(
            "file://%s" % deb_dir, "./", trusted=True)
        self.facade.reload_channels()
        foo1, foo2 = sorted(self.facade.get_packages_by_name("foo"))
        self.assertEqual(foo2, foo1.package.candidate)
        self.facade.mark_install(foo1)
        self.patch_cache_commit()
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
        self.facade.add_channel_apt_deb(
            "file://%s" % deb_dir, "./", trusted=True)
        self.facade.reload_channels()

        multi_arch1, multi_arch2 = sorted(
            self.facade.get_packages_by_name("multi-arch"))
        single_arch1, single_arch2 = sorted(
            self.facade.get_packages_by_name("single-arch"))
        self.facade.mark_remove(multi_arch1)
        self.facade.mark_install(multi_arch2)
        self.facade.mark_remove(single_arch1)
        self.facade.mark_install(single_arch2)
        self.patch_cache_commit()
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
        self.facade.add_channel_apt_deb(
            "file://%s" % deb_dir, "./", trusted=True)
        self.facade.reload_channels()

        multi_arch1, multi_arch2 = sorted(
            self.facade.get_packages_by_name("multi-arch"))
        self.facade.mark_global_upgrade()
        self.patch_cache_commit()
        with self.assertRaises(DependencyError) as cm:
            self.facade.perform_changes()
        self.assertEqual(
            sorted([multi_arch1, multi_arch2]), sorted(cm.exception.packages))
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
        self.facade.add_channel_apt_deb(
            "file://%s" % deb_dir, "./", trusted=True)
        self.facade.reload_channels()
        foo1, foo2 = sorted(self.facade.get_packages_by_name("foo"))
        self.facade.mark_global_upgrade()
        with self.assertRaises(DependencyError) as cm:
            self.facade.perform_changes()
        self.assertEqual(set([foo1, foo2]), set(cm.exception.packages))

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
        self.facade.add_channel_apt_deb(
            "file://%s" % deb_dir, "./", trusted=True)
        self.facade.reload_channels()
        foo1, foo2, foo3 = sorted(self.facade.get_packages_by_name("foo"))
        self.assertEqual(foo3, foo1.package.candidate)
        self.facade.mark_global_upgrade()
        with self.assertRaises(DependencyError) as cm:
            self.facade.perform_changes()
        self.assertEqual(set([foo1, foo3]), set(cm.exception.packages))

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
        self.facade.add_channel_apt_deb(
            "file://%s" % deb_dir, "./", trusted=True)
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
        self.facade.add_channel_apt_deb(
            "file://%s" % deb_dir, "./", trusted=True)
        self.facade.reload_channels()
        auto1, auto2 = sorted(self.facade.get_packages_by_name("auto"))
        noauto1, noauto2 = sorted(self.facade.get_packages_by_name("noauto"))
        auto1.package.mark_auto(True)
        noauto1.package.mark_auto(False)
        self.facade.mark_global_upgrade()
        with self.assertRaises(DependencyError):
            self.facade.perform_changes()
        self.assertTrue(auto2.package.is_auto_installed)
        self.assertFalse(noauto2.package.is_auto_installed)

    def test_wb_perform_changes_commits_changes(self):
        """
        When calling C{perform_changes}, it will commit the cache, to
        cause all package changes to happen.
        """
        committed = []

        def commit(fetch_progress, install_progress):
            committed.append(True)

        deb_dir = self.makeDir()
        create_deb(deb_dir, PKGNAME_MINIMAL, PKGDEB_MINIMAL)
        self.facade.add_channel_deb_dir(deb_dir)
        self.facade.reload_channels()
        [pkg] = self.facade.get_packages_by_name("minimal")
        self.facade.mark_install(pkg)
        self.patch_cache_commit(commit)
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
        [pkg] = self.facade.get_packages_by_name("minimal")
        self.facade.mark_install(pkg)
        self.patch_cache_commit()
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
        self.facade.add_channel_apt_deb(
            "file://%s" % deb_dir, "./", trusted=True)
        self.facade.reload_channels()
        [foo] = self.facade.get_packages_by_name("foo")
        self.facade.mark_install(foo)
        self.patch_cache_commit()
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
        self.facade.add_channel_apt_deb(
            "file://%s" % deb_dir, "./", trusted=True)
        self.facade.reload_channels()
        [foo] = self.facade.get_packages_by_name("foo")
        [bar] = self.facade.get_packages_by_name("bar")
        self.facade.mark_install(foo)
        self.patch_cache_commit()
        with self.assertRaises(DependencyError) as cm:
            self.facade.perform_changes()
        self.assertEqual([bar], cm.exception.packages)

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
        self.facade.add_channel_apt_deb(
            "file://%s" % deb_dir, "./", trusted=True)
        self.facade.reload_channels()
        [foo] = self.facade.get_packages_by_name("foo")
        self.facade.mark_remove(foo)
        self.patch_cache_commit()
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
        self.facade.add_channel_apt_deb(
            "file://%s" % deb_dir, "./", trusted=True)
        self.facade.reload_channels()
        [broken] = self.facade.get_packages_by_name("broken")
        [foo] = self.facade.get_packages_by_name("foo")
        [missing] = self.facade.get_packages_by_name("missing")
        self.assertEqual(
            set([broken.package]), self.facade._get_broken_packages())
        self.facade.mark_install(foo)
        self.facade.mark_install(missing)
        self.patch_cache_commit()
        with self.assertRaises(TransactionError) as cm:
            self.facade.perform_changes()
        self.assertIn(
            "The following packages have unmet dependencies",
            cm.exception.args[0])
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
        with mock.patch.object(self.facade._cache, "commit") as mock_commit:
            mock_commit.side_effect = SystemError("Something went wrong.")
            with self.assertRaises(TransactionError) as cm:
                self.facade.perform_changes()
            mock_commit.assert_called_with(
                fetch_progress=mock.ANY, install_progress=mock.ANY)
        self.assertIn("Something went wrong.", cm.exception.args[0])

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

        [pkg] = self.facade.get_packages_by_name("name1")
        self.facade.mark_install(pkg)
        with self.assertRaises(TransactionError) as cm:
            self.facade.perform_changes()
        self.assertEqual(
            ["The following packages have unmet dependencies:",
             "  name1: PreDepends: prerequirename1 (= prerequireversion1)" +
                " but is not installable",
             "  name1: Depends: requirename1 (= requireversion1) but is not" +
                " installable"],
            cm.exception.args[0].splitlines()[-3:])

    def test_mark_install_dependency_error(self):
        """
        If a dependency hasn't been marked for installation, a
        DependencyError is raised with the packages that need to be installed.
        """
        deb_dir = self.makeDir()
        self._add_package_to_deb_dir(
            deb_dir, "foo", control_fields={"Depends": "bar"})
        self._add_package_to_deb_dir(deb_dir, "bar")
        self.facade.add_channel_apt_deb(
            "file://%s" % deb_dir, "./", trusted=True)
        self.facade.reload_channels()
        [foo] = self.facade.get_packages_by_name("foo")
        [bar] = self.facade.get_packages_by_name("bar")
        self.facade.mark_install(foo)
        with self.assertRaises(DependencyError) as cm:
            self.facade.perform_changes()
        self.assertEqual([bar], cm.exception.packages)

    def test_wb_check_changes_unapproved_install_default(self):
        """
        C{_check_changes} raises C{DependencyError} with the candidate
        version, if a package is marked for installation, but not in the
        requested changes.
        """
        deb_dir = self.makeDir()
        self._add_package_to_deb_dir(deb_dir, "foo", version="1.0")
        self._add_package_to_deb_dir(deb_dir, "foo", version="2.0")
        self.facade.add_channel_apt_deb(
            "file://%s" % deb_dir, "./", trusted=True)
        self.facade.reload_channels()
        [foo1, foo2] = sorted(self.facade.get_packages_by_name("foo"))
        self.assertEqual(foo1.package, foo2.package)
        package = foo1.package
        self.assertEqual(package.candidate, foo2)

        package.mark_install()
        self.assertEqual([package], self.facade._cache.get_changes())
        self.assertTrue(package.marked_install)

        with self.assertRaises(DependencyError) as cm:
            self.facade._check_changes([])
        self.assertEqual([foo2], cm.exception.packages)

    def test_wb_check_changes_unapproved_install_specific_version(self):
        """
        C{_check_changes} raises C{DependencyError} with the candidate
        version, if a package is marked for installation with a
        non-default candidate version.
        """
        deb_dir = self.makeDir()
        self._add_package_to_deb_dir(deb_dir, "foo", version="1.0")
        self._add_package_to_deb_dir(deb_dir, "foo", version="2.0")
        self.facade.add_channel_apt_deb(
            "file://%s" % deb_dir, "./", trusted=True)
        self.facade.reload_channels()
        [foo1, foo2] = sorted(self.facade.get_packages_by_name("foo"))
        self.assertEqual(foo1.package, foo2.package)
        package = foo1.package

        package.candidate = foo1
        package.mark_install()
        self.assertEqual([package], self.facade._cache.get_changes())
        self.assertTrue(package.marked_install)

        with self.assertRaises(DependencyError) as cm:
            self.facade._check_changes([])
        self.assertEqual([foo1], cm.exception.packages)

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

        with self.assertRaises(DependencyError) as cm:
            self.facade._check_changes([])
        self.assertEqual([foo], cm.exception.packages)

    def test_check_changes_unapproved_remove_with_update_available(self):
        """
        C{_check_changes} raises C{DependencyError} with the installed
        version, if a package is marked for removal and there is an
        update available.
        """
        self._add_system_package("foo", version="1.0")
        deb_dir = self.makeDir()
        self._add_package_to_deb_dir(deb_dir, "foo", version="2.0")
        self.facade.add_channel_apt_deb(
            "file://%s" % deb_dir, "./", trusted=True)
        self.facade.reload_channels()
        [foo1, foo2] = sorted(self.facade.get_packages_by_name("foo"))
        self.assertEqual(foo1.package, foo2.package)
        package = foo1.package

        package.mark_delete()
        self.assertEqual([package], self.facade._cache.get_changes())
        self.assertTrue(package.marked_delete)

        with self.assertRaises(DependencyError) as cm:
            self.facade._check_changes([])
        self.assertEqual([foo1], cm.exception.packages)

    def test_check_changes_unapproved_upgrade(self):
        """
        If a package is marked to be upgraded, C{_check_changes} raises
        C{DependencyError} with the installed version and the version to
        be upgraded to.
        """
        self._add_system_package("foo", version="1.0")
        deb_dir = self.makeDir()
        self._add_package_to_deb_dir(deb_dir, "foo", version="2.0")
        self.facade.add_channel_apt_deb(
            "file://%s" % deb_dir, "./", trusted=True)
        self.facade.reload_channels()
        [foo1, foo2] = sorted(self.facade.get_packages_by_name("foo"))
        self.assertEqual(foo1.package, foo2.package)
        package = foo1.package

        package.mark_install()
        self.assertEqual([package], self.facade._cache.get_changes())
        self.assertTrue(package.marked_upgrade)

        with self.assertRaises(DependencyError) as cm:
            self.facade._check_changes([])
        self.assertEqual(set([foo1, foo2]), set(cm.exception.packages))

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
        self.facade.add_channel_apt_deb(
            "file://%s" % deb_dir, "./", trusted=True)
        self.facade.reload_channels()
        [foo1, foo2] = sorted(self.facade.get_packages_by_name("foo"))[:2]
        self.assertEqual(foo1.package, foo2.package)
        package = foo1.package
        package.candidate = foo1

        package.mark_install()
        self.assertEqual([package], self.facade._cache.get_changes())
        self.assertTrue(package.marked_downgrade)

        with self.assertRaises(DependencyError) as cm:
            self.facade._check_changes([])
        self.assertEqual(set([foo1, foo2]), set(cm.exception.packages))

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
        self.facade.add_channel_apt_deb(
            "file://%s" % deb_dir, "./", trusted=True)
        self.facade.reload_channels()
        foo_10, foo_15 = sorted(self.facade.get_packages_by_name("foo"))
        [bar] = self.facade.get_packages_by_name("bar")
        self.facade.mark_global_upgrade()
        with self.assertRaises(DependencyError) as cm:
            self.facade.perform_changes()
        self.assertEqual(
            sorted([bar, foo_10, foo_15], key=self.version_sortkey),
            sorted(cm.exception.packages, key=self.version_sortkey))

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
        with self.assertRaises(DependencyError) as cm:
            self.facade.perform_changes()
        self.assertEqual([bar], cm.exception.packages)

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
        with self.assertRaises(TransactionError) as cm:
            self.facade.perform_changes()
        self.assertEqual(
            "Can't perform the changes, since the following packages" +
            " are held: bar, foo", cm.exception.args[0])

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
        self.facade.add_channel_apt_deb(
            "file://%s" % deb_dir, "./", trusted=True)
        self.facade.reload_channels()
        bar_1, bar_2 = sorted(self.facade.get_packages_by_name("bar"))
        self.facade.mark_install(bar_2)
        self.facade.mark_remove(bar_1)
        self.patch_cache_commit()
        self.facade.perform_changes()
        [bar] = self.facade._cache.get_changes()
        self.assertTrue(bar.marked_upgrade)

    def test_changer_upgrade_keeps_auto(self):
        """
        An upgrade request should preserve an existing auto flag on the
        upgraded package.
        """
        self._add_system_package(
            "foo", control_fields={"Depends": "bar"})
        self._add_system_package("bar", version="1.0")
        deb_dir = self.makeDir()
        self._add_package_to_deb_dir(deb_dir, "bar", version="2.0")
        self.facade.add_channel_apt_deb(
            "file://%s" % deb_dir, "./", trusted=True)
        self.facade.reload_channels()
        bar_1, bar_2 = sorted(self.facade.get_packages_by_name("bar"))
        bar_1.package.mark_auto()

        self.facade.mark_install(bar_2)
        self.facade.mark_remove(bar_1)
        self.patch_cache_commit()
        self.facade.perform_changes()
        [bar] = self.facade._cache.get_changes()
        self.assertTrue(bar.marked_upgrade)
        self.assertTrue(bar.is_auto_installed)

    def test_changer_upgrade_keeps_manual(self):
        """
        An upgrade request should mark a package as manual if the installed
        version is manual.
        """
        self._add_system_package(
            "foo", control_fields={"Depends": "bar"})
        self._add_system_package("bar", version="1.0")
        deb_dir = self.makeDir()
        self._add_package_to_deb_dir(deb_dir, "bar", version="2.0")
        self.facade.add_channel_apt_deb(
            "file://%s" % deb_dir, "./", trusted=True)
        self.facade.reload_channels()
        bar_1, bar_2 = sorted(self.facade.get_packages_by_name("bar"))

        self.facade.mark_install(bar_2)
        self.facade.mark_remove(bar_1)
        self.patch_cache_commit()
        self.facade.perform_changes()
        [bar] = self.facade._cache.get_changes()
        self.assertTrue(bar.marked_upgrade)
        self.assertFalse(bar.is_auto_installed)

    def test_changer_install_sets_manual(self):
        """
        An installation request should mark the new package as manually
        installed.
        """
        deb_dir = self.makeDir()
        self._add_package_to_deb_dir(deb_dir, "bar", version="2.0")
        self.facade.add_channel_apt_deb(
            "file://%s" % deb_dir, "./", trusted=True)
        self.facade.reload_channels()
        bar_2, = self.facade.get_packages_by_name("bar")

        self.facade.mark_install(bar_2)
        self.patch_cache_commit()
        self.facade.perform_changes()
        [bar] = self.facade._cache.get_changes()
        self.assertTrue(bar.marked_upgrade)
        self.assertFalse(bar.is_auto_installed)

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
        self.facade.add_channel_apt_deb(
            "file://%s" % deb_dir, "./", trusted=True)
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
        self.facade.add_channel_apt_deb(
            "file://%s" % deb_dir, "./", trusted=True)
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
        self.facade.add_channel_apt_deb(
            "file://%s" % deb_dir, "./", trusted=True)
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
        with self.assertRaises(DependencyError) as cm:
            self.facade.perform_changes()

        self.assertEqual(
            sorted(cm.exception.packages, key=self.version_sortkey),
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
        [foo] = self.facade.get_packages_by_name("foo")
        [baz] = self.facade.get_packages_by_name("baz")

        self.assertEqual(
            ["baz", "foo"], sorted(self.facade.get_package_holds()))

    def test_mark_hold_and_perform_hold_changes(self):
        """
        Test that L{perform_hold_changes} holds packages that have previously
        been marked for hold.
        """
        self._add_system_package("foo")
        self.facade.reload_channels()
        [foo] = self.facade.get_packages_by_name("foo")
        self.facade.mark_hold(foo)
        self.assertEqual("Package holds successfully changed.",
                         self.facade._perform_hold_changes())
        self.facade.reload_channels()
        self.assertEqual(["foo"], self.facade.get_package_holds())

    def test_mark_hold(self):
        """
        C{mark_hold} marks a package to be held.
        """
        self._add_system_package("foo")
        self.facade.reload_channels()
        [foo] = self.facade.get_packages_by_name("foo")
        self.facade.mark_hold(foo)
        self.facade.perform_changes()
        self.facade.reload_channels()
        self.assertEqual(["foo"], self.facade.get_package_holds())

    def test_two_holds_with_the_same_version_id(self):
        """
        Test C{mark_hold} can distinguish between two different packages with
        the same version number (the version number is used to make the unique
        hash for the package version).
        """
        self._add_system_package("foo", version="1.0")
        self._add_system_package("bar", version="1.0")
        self.facade.reload_channels()
        [foo] = self.facade.get_packages_by_name("foo")
        [bar] = self.facade.get_packages_by_name("bar")
        self.facade.mark_hold(foo)
        self.facade.mark_hold(bar)
        self.assertEqual(2, len(self.facade._version_hold_creations))

    def test_mark_hold_existing_hold(self):
        """
        If a package is already held, C{mark_hold} and
        C{perform_changes} won't return an error.
        """
        self._add_system_package(
            "foo", control_fields={"Status": "hold ok installed"})
        self.facade.reload_channels()
        [foo] = self.facade.get_packages_by_name("foo")
        self.facade.mark_hold(foo)
        self.facade.perform_changes()
        self.facade.reload_channels()

        self.assertEqual(["foo"], self.facade.get_package_holds())

    def test_mark_remove_hold(self):
        """
        C{mark_remove_hold} marks a package as not held.
        """
        self._add_system_package(
            "foo", control_fields={"Status": "hold ok installed"})
        self.facade.reload_channels()
        [foo] = self.facade.get_packages_by_name("foo")
        self.facade.mark_remove_hold(foo)
        self.facade.perform_changes()
        self.facade.reload_channels()

        self.assertEqual([], self.facade.get_package_holds())

    def test_mark_remove_hold_no_package(self):
        """
        If a package doesn't exist, C{mark_remove_hold} followed by
        C{perform_changes} doesn't return an error. It's up to the caller to
        make sure that the package exist, if it's important.
        """
        self._add_system_package("foo")
        deb_dir = self.makeDir()
        self._add_package_to_deb_dir(deb_dir, "bar")
        self.facade.add_channel_apt_deb(
            "file://%s" % deb_dir, "./", trusted=True)
        self.facade.reload_channels()
        [bar] = self.facade.get_packages_by_name("bar")
        self.facade.mark_remove_hold(bar)
        self.facade.perform_changes()
        self.facade.reload_channels()

        self.assertEqual([], self.facade.get_package_holds())

    def test_mark_remove_hold_no_hold(self):
        """
        If a package isn't held, the existing selection is retained when
        C{mark_remove_hold} and C{perform_changes} are called.
        """
        self._add_system_package(
            "foo", control_fields={"Status": "deinstall ok installed"})
        self.facade.reload_channels()
        [foo] = self.facade.get_packages_by_name("foo")
        self.facade.mark_remove_hold(foo)
        self.facade.perform_changes()
        self.facade.reload_channels()

        self.assertEqual([], self.facade.get_package_holds())
        [foo] = self.facade.get_packages_by_name("foo")
        self.assertEqual(
            apt_pkg.SELSTATE_DEINSTALL, foo.package._pkg.selected_state)

    def test_creation_of_key_ring(self):
        """
        Apt on Trusty requires a keyring exist in its directory structure, so
        we create an empty file to appease it.
        """
        keyring_path = os.path.join(self.facade._root, "etc/apt/trusted.gpg")
        self.assertTrue(os.path.exists(keyring_path))

    if not hasattr(Package, "shortname"):
        # The 'shortname' attribute was added when multi-arch support
        # was added to python-apt. So if it's not there, it means that
        # multi-arch support isn't available.
        skip_message = "multi-arch not supported"
        test_wb_mark_install_upgrade_non_main_arch_dependency_error.skip = (
            skip_message)
        test_wb_mark_install_upgrade_non_main_arch.skip = skip_message

    if apt_pkg.VERSION.startswith("0.7.25"):
        # We must be running on lucid, we want to skip the APT pinning test,
        # see also Bug #1398168.
        skip_message = "test APT pinning settings not working on lucid"
        test_is_package_upgrade_with_apt_preferences.skip = skip_message
