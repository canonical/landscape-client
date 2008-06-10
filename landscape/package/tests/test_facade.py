import gdbm
import time
import os

from smart.control import Control
from smart.cache import Provides

import smart

from landscape.package.facade import (
    SmartFacade, TransactionError, DependencyError, SmartError)

from landscape.tests.helpers import LandscapeTest
from landscape.package.tests.helpers import (
    SmartFacadeHelper, HASH1, HASH2, HASH3, PKGNAME1)


class SmartFacadeTest(LandscapeTest):

    helpers = [SmartFacadeHelper]

    def test_get_packages(self):
        self.facade.reload_channels()
        pkgs = self.facade.get_packages()
        self.assertEquals(sorted(pkg.name for pkg in pkgs),
                          ["name1", "name2", "name3"])

    def test_get_packages_wont_return_non_debian_packages(self):
        self.facade.reload_channels()
        ctrl_mock = self.mocker.patch(Control)
        class StubPackage(object): pass
        cache_mock = ctrl_mock.getCache()
        cache_mock.getPackages()
        self.mocker.result([StubPackage(), StubPackage()])
        self.mocker.replay()
        self.assertEquals(self.facade.get_packages(), [])

    def test_get_packages_by_name(self):
        self.facade.reload_channels()
        pkgs = self.facade.get_packages_by_name("name1")
        self.assertEquals([pkg.name for pkg in pkgs], ["name1"])
        pkgs = self.facade.get_packages_by_name("name2")
        self.assertEquals([pkg.name for pkg in pkgs], ["name2"])

    def test_get_packages_by_name_wont_return_non_debian_packages(self):
        self.facade.reload_channels()
        ctrl_mock = self.mocker.patch(Control)
        class StubPackage(object): pass
        cache_mock = ctrl_mock.getCache()
        cache_mock.getPackages("name")
        self.mocker.result([StubPackage(), StubPackage()])
        self.mocker.replay()
        self.assertEquals(self.facade.get_packages_by_name("name"), [])

    def test_get_package_skeleton(self):
        self.facade.reload_channels()
        pkg1 = self.facade.get_packages_by_name("name1")[0]
        pkg2 = self.facade.get_packages_by_name("name2")[0]
        skeleton1 = self.facade.get_package_skeleton(pkg1)
        skeleton2 = self.facade.get_package_skeleton(pkg2)
        self.assertEquals(skeleton1.get_hash(), HASH1)
        self.assertEquals(skeleton2.get_hash(), HASH2)

    def test_build_skeleton_with_info(self):
        self.facade.reload_channels()
        pkg = self.facade.get_packages_by_name("name1")[0]
        skeleton = self.facade.get_package_skeleton(pkg, True)
        self.assertEquals(skeleton.section, "Group1")
        self.assertEquals(skeleton.summary, "Summary1")
        self.assertEquals(skeleton.description, "Description1")
        self.assertEquals(skeleton.size, 1038)
        self.assertEquals(skeleton.installed_size, 28672)

    def test_get_package_hash(self):
        self.facade.reload_channels()
        pkg = self.facade.get_packages_by_name("name1")[0]
        self.assertEquals(self.facade.get_package_hash(pkg), HASH1)
        pkg = self.facade.get_packages_by_name("name2")[0]
        self.assertEquals(self.facade.get_package_hash(pkg), HASH2)

    def test_get_package_by_hash(self):
        self.facade.reload_channels()
        pkg = self.facade.get_package_by_hash(HASH1)
        self.assertEquals(pkg.name, "name1")
        pkg = self.facade.get_package_by_hash(HASH2)
        self.assertEquals(pkg.name, "name2")
        pkg = self.facade.get_package_by_hash("none")
        self.assertEquals(pkg, None)

    def test_reload_channels_clears_hash_cache(self):
        # Load hashes.
        self.facade.reload_channels()
        start = time.time()

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
        mtime = int(time.time()+1)
        os.utime(self.repository_dir, (mtime, mtime))

        # Reload channels.
        self.facade.reload_channels()

        # Only packages with name2 and name3 should be loaded, and they're
        # not the same objects anymore.
        self.assertEquals(
            sorted([pkg.name for pkg in self.facade.get_packages()]),
            ["name2", "name3"])
        self.assertNotEquals(set(self.facade.get_packages()),
                             set([pkg2, pkg3]))

        # The hash cache shouldn't include either of the old packages.
        self.assertEquals(self.facade.get_package_hash(pkg1), None)
        self.assertEquals(self.facade.get_package_hash(pkg2), None)
        self.assertEquals(self.facade.get_package_hash(pkg3), None)

        # Also, the hash for package1 shouldn't be present at all.
        self.assertEquals(self.facade.get_package_by_hash(HASH1), None)

        # While HASH2 and HASH3 should point to the new packages.
        new_pkgs = self.facade.get_packages()
        self.assertTrue(self.facade.get_package_by_hash(HASH2)
                        in new_pkgs)
        self.assertTrue(self.facade.get_package_by_hash(HASH3)
                        in new_pkgs)

        # Which are not the old packages.
        self.assertFalse(pkg2 in new_pkgs)
        self.assertFalse(pkg3 in new_pkgs)

    def test_perform_changes_with_nothing_to_do(self):
        """perform_changes() should return None when there's nothing to do.
        """
        self.facade.reload_channels()
        self.assertEquals(self.facade.perform_changes(), None)

    def test_reset_marks(self):
        """perform_changes() should return None when there's nothing to do.
        """
        self.facade.reload_channels()
        pkg = self.facade.get_packages_by_name("name1")[0]
        self.facade.mark_install(pkg)
        self.facade.reset_marks()
        self.assertEquals(self.facade.perform_changes(), None)

    def test_mark_install_transaction_error(self):
        """
        Mark package 'name1' for installation, and try to perform changes.
        It should fail because 'name1' depends on 'requirename1'.
        """
        self.facade.reload_channels()

        pkg = self.facade.get_packages_by_name("name1")[0]
        self.facade.mark_install(pkg)
        try:
            self.facade.perform_changes()
        except TransactionError, exception:
            pass
        else:
            exception = None
        self.assertTrue(exception, "TransactionError not raised")
        self.assertTrue("requirename" in str(exception))

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

        self.assertEquals(pkg1.requires[0].providedby[0].packages[0], pkg2)
        self.assertEquals(pkg1.requires[1].providedby[0].packages[0], pkg2)

        self.facade.mark_install(pkg1)
        try:
            self.facade.perform_changes()
        except DependencyError, exception:
            pass
        else:
            exception = None
        self.assertTrue(exception, "DependencyError not raised")
        self.assertEquals(exception.packages, [pkg2])

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

        self.assertEquals(pkg1.requires[0].providedby[0].packages[0], pkg2)
        self.assertEquals(pkg1.requires[1].providedby[0].packages[0], pkg2)

        self.facade.mark_remove(pkg2)
        try:
            output = self.facade.perform_changes()
        except DependencyError, exception:
            output = ""
        else:
            exception = None
        self.assertTrue(exception, "DependencyError not raised. Output: %s"
                                   % repr(output))
        self.assertEquals(exception.packages, [pkg1])

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
        self.assertEquals(pkg2.upgrades[0].providedby[0].packages[0], pkg1)

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
        self.assertEquals(set(exception.packages), set([pkg1, pkg2]))

    def test_perform_changes_with_logged_error(self):
        self.log_helper.ignore_errors(".*Sub-process dpkg returned an error.*")

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

        self.assertEquals(str(exception),
                          "\n[unpack] name1_version1-release1\n"
                          "dpkg: requested operation requires "
                          "superuser privilege\n"
                          "ERROR: Sub-process dpkg returned an "
                          "error code (2)\n")

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

        self.assertEquals(environ, ["noninteractive", "none",
                                    "noninteractive", "none"])

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
        class StubPackage(object): pass
        pkg = StubPackage()

        ctrl_mock = self.mocker.patch(Control)
        cache_mock = ctrl_mock.getCache()
        cache_mock.getPackages()
        self.mocker.result([pkg])
        self.mocker.replay()

        self.facade.reload_channels()
        self.assertEquals(self.facade.get_package_hash(pkg), None)
