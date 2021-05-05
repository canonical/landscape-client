# -*- encoding: utf-8 -*-
import time
import sys
import os

from twisted.internet.defer import Deferred
from twisted.python.failure import Failure
from twisted.internet.error import ProcessTerminated, ProcessDone

from mock import patch, Mock, call

from landscape.lib.apt.package.store import PackageStore
from landscape.lib.apt.package.facade import (
    DependencyError, TransactionError)
from landscape.lib.apt.package.testing import (
    HASH1, HASH2, HASH3, PKGDEB1, PKGDEB2,
    AptFacadeHelper, SimpleRepositoryHelper)
from landscape.lib import base64
from landscape.lib.fs import create_text_file, read_text_file, touch_file
from landscape.lib.testing import StubProcessFactory, FakeReactor
from landscape.client.package.changer import (
    PackageChanger, main, UNKNOWN_PACKAGE_DATA_TIMEOUT,
    SUCCESS_RESULT, DEPENDENCY_ERROR_RESULT, POLICY_ALLOW_INSTALLS,
    POLICY_ALLOW_ALL_CHANGES, ERROR_RESULT)
from landscape.client.package.changer import (
    PackageChangerConfiguration, ChangePackagesResult)
from landscape.client.tests.helpers import LandscapeTest, BrokerServiceHelper
from landscape.client.manager.manager import FAILED
from landscape.client.manager.shutdownmanager import ShutdownFailedError


class AptPackageChangerTest(LandscapeTest):

    helpers = [AptFacadeHelper, SimpleRepositoryHelper, BrokerServiceHelper]

    def setUp(self):
        super(AptPackageChangerTest, self).setUp()
        self.store = PackageStore(self.makeFile())
        self.config = PackageChangerConfiguration()
        self.config.data_path = self.makeDir()
        self.process_factory = StubProcessFactory()
        self.landscape_reactor = FakeReactor()
        reboot_required_filename = self.makeFile("reboot required")
        os.mkdir(self.config.package_directory)
        os.mkdir(self.config.binaries_path)
        touch_file(self.config.update_stamp_filename)
        self.changer = PackageChanger(
            self.store, self.facade, self.remote, self.config,
            process_factory=self.process_factory,
            landscape_reactor=self.landscape_reactor,
            reboot_required_filename=reboot_required_filename)
        self.changer.update_notifier_stamp = "/Not/Existing"
        self.changer.get_session_id()
        service = self.broker_service
        service.message_store.set_accepted_types(["change-packages-result",
                                                  "operation-result"])

    def set_pkg1_installed(self):
        """Return the hash of a package that is installed."""
        self._add_system_package("foo")
        self.facade.reload_channels()
        [foo] = self.facade.get_packages_by_name("foo")
        return self.facade.get_package_hash(foo)

    def set_pkg2_satisfied(self):
        """Return the hash of a package that can be installed."""
        self._add_package_to_deb_dir(self.repository_dir, "bar")
        self.facade.reload_channels()
        [bar] = self.facade.get_packages_by_name("bar")
        return self.facade.get_package_hash(bar)

    def set_pkg1_and_pkg2_satisfied(self):
        """Make a package depend on another package.

        Return the hashes of the two packages.
        """
        self._add_package_to_deb_dir(
            self.repository_dir, "foo", control_fields={"Depends": "bar"})
        self._add_package_to_deb_dir(self.repository_dir, "bar")
        self.facade.reload_channels()
        [foo] = self.facade.get_packages_by_name("foo")
        [bar] = self.facade.get_packages_by_name("bar")
        return (
            self.facade.get_package_hash(foo),
            self.facade.get_package_hash(bar))

    def set_pkg2_upgrades_pkg1(self):
        """Make it so that one package upgrades another.

        Return the hashes of the two packages.
        """
        self._add_system_package("foo", version="1.0")
        self._add_package_to_deb_dir(self.repository_dir, "foo", version="2.0")
        self.facade.reload_channels()
        foo_1, foo_2 = sorted(self.facade.get_packages_by_name("foo"))
        return (
            self.facade.get_package_hash(foo_1),
            self.facade.get_package_hash(foo_2))

    def remove_pkg2(self):
        """Remove package name2 from its repository."""
        packages_file = os.path.join(self.repository_dir, "Packages")
        packages_contents = read_text_file(packages_file)
        packages_contents = "\n\n".join(
            [stanza for stanza in packages_contents.split("\n\n")
             if "Package: name2" not in stanza])
        create_text_file(packages_file, packages_contents)

    def get_binaries_channels(self, binaries_path):
        """Return the channels that will be used for the binaries."""
        return [{"baseurl": "file://%s" % binaries_path,
                 "components": "",
                 "distribution": "./",
                 "type": "deb"}]

    def get_package_name(self, version):
        """Return the name of the package."""
        return version.package.name

    def disable_clear_channels(self):
        """Disable clear_channels(), so that it doesn't remove test setup.

        This is useful for change-packages tests, which will call
        facade.clear_channels(). Normally that's safe, but since we used
        the facade to set up channels, we don't want them to be removed.
        """
        self.facade.clear_channels = lambda: None

    def get_pending_messages(self):
        return self.broker_service.message_store.get_pending_messages()

    def replace_perform_changes(self, func):
        old_perform_changes = self.Facade.perform_changes

        def reset_perform_changes(Facade):
            Facade.perform_changes = old_perform_changes

        self.addCleanup(reset_perform_changes, self.Facade)
        self.Facade.perform_changes = func

    def test_unknown_package_id_for_dependency(self):
        hash1, hash2 = self.set_pkg1_and_pkg2_satisfied()

        # Let's request an operation that would require an answer with a
        # must-install field with a package for which the id isn't yet
        # known by the client.
        self.store.add_task("changer",
                            {"type": "change-packages", "install": [1],
                             "operation-id": 123})

        # In our first try, we should get nothing, because the id of the
        # dependency (hash2) isn't known.
        self.store.set_hash_ids({hash1: 1})
        result = self.changer.handle_tasks()
        self.assertEqual(result.called, True)
        self.assertMessages(self.get_pending_messages(), [])

        self.assertIn("Package data not yet synchronized with server (%r)"
                      % hash2, self.logfile.getvalue())

        # So now we'll set it, and advance the reactor to the scheduled
        # change detection.  We'll get a lot of messages, including the
        # result of our previous message, which got *postponed*.
        self.store.set_hash_ids({hash2: 2})
        result = self.changer.handle_tasks()

        def got_result(result):
            self.assertMessages(self.get_pending_messages(),
                                [{"must-install": [2],
                                  "operation-id": 123,
                                  "result-code": 101,
                                  "type": "change-packages-result"}])
        return result.addCallback(got_result)

    def test_install_unknown_id(self):
        self.store.add_task("changer",
                            {"type": "change-packages", "install": [456],
                             "operation-id": 123})

        self.changer.handle_tasks()

        self.assertIn("Package data not yet synchronized with server (456)",
                      self.logfile.getvalue())
        self.assertTrue(self.store.get_next_task("changer"))

    def test_remove_unknown_id(self):
        self.store.add_task("changer",
                            {"type": "change-packages", "remove": [456],
                             "operation-id": 123})

        self.changer.handle_tasks()

        self.assertIn("Package data not yet synchronized with server (456)",
                      self.logfile.getvalue())
        self.assertTrue(self.store.get_next_task("changer"))

    def test_install_unknown_package(self):
        self.store.set_hash_ids({b"hash": 456})
        self.store.add_task("changer",
                            {"type": "change-packages", "install": [456],
                             "operation-id": 123})

        self.changer.handle_tasks()

        self.assertIn("Package data not yet synchronized with server (%r)" %
                      b"hash", self.logfile.getvalue())
        self.assertTrue(self.store.get_next_task("changer"))

    def test_remove_unknown_package(self):
        self.store.set_hash_ids({b"hash": 456})
        self.store.add_task("changer",
                            {"type": "change-packages", "remove": [456],
                             "operation-id": 123})

        self.changer.handle_tasks()

        self.assertIn("Package data not yet synchronized with server (%r)" %
                      b"hash", self.logfile.getvalue())
        self.assertTrue(self.store.get_next_task("changer"))

    def test_unknown_data_timeout(self):
        """After a while, unknown package data is reported as an error.

        In these cases a warning is logged, and the task is removed.
        """
        self.store.add_task("changer",
                            {"type": "change-packages", "remove": [123],
                             "operation-id": 123})

        the_time = time.time() + UNKNOWN_PACKAGE_DATA_TIMEOUT
        with patch("time.time", return_value=the_time) as time_mock:
            result = self.changer.handle_tasks()

        time_mock.assert_called_with()

        self.assertIn("Package data not yet synchronized with server (123)",
                      self.logfile.getvalue())

        def got_result(result):
            message = {"type": "change-packages-result",
                       "operation-id": 123,
                       "result-code": 100,
                       "result-text": "Package data has changed. "
                                      "Please retry the operation."}
            self.assertMessages(self.get_pending_messages(), [message])
            self.assertEqual(self.store.get_next_task("changer"), None)
        return result.addCallback(got_result)

    def test_dependency_error(self):
        """
        In this test we hack the facade to simulate the situation where
        Smart didn't accept to remove the package due to missing
        dependencies that are present in the system but weren't requested
        in the message.

        The client must answer it saying which additional changes are
        needed to perform the requested operation.

        It's a slightly hackish approach, since we're returning
        the full set of packages available as a dependency error, but
        it serves well for testing this specific feature.
        """
        installed_hash = self.set_pkg1_installed()
        # Use ensure_channels_reloaded() to make sure that the package
        # instances we raise below are the same that the facade will
        # use. The changer will use ensure_channels_reloaded() too,
        # which won't actually reload the package data if it's already
        # loaded.
        self.facade.ensure_channels_reloaded()
        self.store.set_hash_ids({installed_hash: 1, HASH2: 2, HASH3: 3})
        self.store.add_task("changer",
                            {"type": "change-packages", "install": [2],
                             "operation-id": 123})

        packages = [
            self.facade.get_package_by_hash(pkg_hash)
            for pkg_hash in [installed_hash, HASH2, HASH3]]

        def raise_dependency_error(self):
            raise DependencyError(set(packages))

        self.replace_perform_changes(raise_dependency_error)

        result = self.changer.handle_tasks()

        def got_result(result):
            self.assertMessages(self.get_pending_messages(),
                                [{"must-install": [2, 3],
                                  "must-remove": [1],
                                  "operation-id": 123,
                                  "result-code": 101,
                                  "type": "change-packages-result"}])
        return result.addCallback(got_result)

    def test_dependency_error_with_binaries(self):
        """
        Simulate a failing operation involving server-generated binary
        packages. The extra changes needed to perform the transaction
        are sent back to the server.
        """
        self.remove_pkg2()
        installed_hash = self.set_pkg1_installed()
        self.store.set_hash_ids({installed_hash: 1, HASH3: 3})
        self.store.add_task("changer",
                            {"type": "change-packages",
                             "install": [2],
                             "binaries": [(HASH2, 2, PKGDEB2)],
                             "operation-id": 123})

        packages = set()

        def raise_dependency_error(self):
            packages.update(
                self.get_package_by_hash(pkg_hash)
                for pkg_hash in [installed_hash, HASH2, HASH3])
            raise DependencyError(set(packages))

        self.replace_perform_changes(raise_dependency_error)
        self.disable_clear_channels()

        result = self.changer.handle_tasks()

        def got_result(result):
            self.assertMessages(self.get_pending_messages(),
                                [{"must-install": [2, 3],
                                  "must-remove": [1],
                                  "operation-id": 123,
                                  "result-code": 101,
                                  "type": "change-packages-result"}])
        return result.addCallback(got_result)

    def test_perform_changes_with_allow_install_policy(self):
        """
        The C{POLICY_ALLOW_INSTALLS} policy the makes the changer mark
        the missing packages for installation.
        """
        self.store.set_hash_ids({HASH1: 1})
        self.facade.reload_channels()
        [package1] = self.facade.get_packages_by_name("name1")

        self.facade.perform_changes = Mock(
            side_effect=[DependencyError([package1]), "success"])

        self.facade.mark_install = Mock()

        result = self.changer.change_packages(POLICY_ALLOW_INSTALLS)

        self.facade.perform_changes.has_calls([call(), call()])
        self.facade.mark_install.assert_called_once_with(package1)

        self.assertEqual(result.code, SUCCESS_RESULT)
        self.assertEqual(result.text, "success")
        self.assertEqual(result.installs, [1])
        self.assertEqual(result.removals, [])

    def test_perform_changes_with_allow_install_policy_and_removals(self):
        """
        The C{POLICY_ALLOW_INSTALLS} policy doesn't allow additional packages
        to be removed.
        """
        installed_hash = self.set_pkg1_installed()
        self.store.set_hash_ids({installed_hash: 1, HASH2: 2})
        self.facade.reload_channels()

        package1 = self.facade.get_package_by_hash(installed_hash)
        [package2] = self.facade.get_packages_by_name("name2")

        self.facade.perform_changes = Mock(
            side_effect=DependencyError([package1, package2]))

        result = self.changer.change_packages(POLICY_ALLOW_INSTALLS)

        self.facade.perform_changes.assert_called_once_with()

        self.assertEqual(result.code, DEPENDENCY_ERROR_RESULT)
        self.assertEqual(result.text, None)
        self.assertEqual(result.installs, [2])
        self.assertEqual(result.removals, [1])

    def test_perform_changes_with_max_retries(self):
        """
        After having complemented the requested changes to handle a dependency
        error, the L{PackageChanger.change_packages} will try to perform the
        requested changes again only once.
        """
        self.store.set_hash_ids({HASH1: 1, HASH2: 2})
        self.facade.reload_channels()

        [package1] = self.facade.get_packages_by_name("name1")
        [package2] = self.facade.get_packages_by_name("name2")

        self.facade.perform_changes = Mock(
            side_effect=[DependencyError([package1]),
                         DependencyError([package2])])

        result = self.changer.change_packages(POLICY_ALLOW_INSTALLS)

        self.facade.perform_changes.has_calls([call(), call()])

        self.assertEqual(result.code, DEPENDENCY_ERROR_RESULT)
        self.assertEqual(result.text, None)
        self.assertEqual(result.installs, [1, 2])
        self.assertEqual(result.removals, [])

    def test_handle_change_packages_with_policy(self):
        """
        The C{change-packages} message can have an optional C{policy}
        field that will be passed to the C{perform_changes} method.
        """
        self.store.set_hash_ids({HASH1: 1})
        self.store.add_task("changer",
                            {"type": "change-packages",
                             "install": [1],
                             "policy": POLICY_ALLOW_INSTALLS,
                             "operation-id": 123})

        result = ChangePackagesResult()
        result.code = SUCCESS_RESULT

        self.changer.change_packages = Mock(return_value=result)

        self.disable_clear_channels()

        self.successResultOf(self.changer.handle_tasks())
        self.changer.change_packages.assert_called_once_with(
            POLICY_ALLOW_INSTALLS)

    def test_perform_changes_with_policy_allow_all_changes(self):
        """
        The C{POLICY_ALLOW_ALL_CHANGES} policy allows any needed additional
        package to be installed or removed.
        """
        installed_hash = self.set_pkg1_installed()
        self.store.set_hash_ids({installed_hash: 1, HASH2: 2})
        self.facade.reload_channels()

        package1 = self.facade.get_package_by_hash(installed_hash)
        [package2] = self.facade.get_packages_by_name("name2")

        self.facade.perform_changes = Mock(
            side_effect=[DependencyError([package1, package2]),
                         "success"])
        self.facade.mark_install = Mock()
        self.facade.mark_remove = Mock()

        result = self.changer.change_packages(POLICY_ALLOW_ALL_CHANGES)

        self.facade.perform_changes.has_calls([call(), call()])
        self.facade.mark_install.assert_called_once_with(package2)
        self.facade.mark_remove.assert_called_once_with(package1)

        self.assertEqual(result.code, SUCCESS_RESULT)
        self.assertEqual(result.text, "success")
        self.assertEqual(result.installs, [2])
        self.assertEqual(result.removals, [1])

    def test_transaction_error(self):
        """
        In this case, the package we're trying to install declared some
        dependencies that can't be satisfied in the client because they
        don't exist at all.  The client must answer the request letting
        the server know about the unsolvable problem.
        """
        self.store.set_hash_ids({HASH1: 1})
        self.store.add_task("changer",
                            {"type": "change-packages", "install": [1],
                             "operation-id": 123})

        self.disable_clear_channels()
        result = self.changer.handle_tasks()

        def got_result(result):
            messages = self.get_pending_messages()
            self.assertEqual(len(messages), 1)
            message = messages[0]
            self.assertEqual(message["operation-id"], 123)
            self.assertEqual(message["result-code"], 100)
            self.assertIn(
                "packages have unmet dependencies", message["result-text"])
            self.assertEqual(message["type"], "change-packages-result")
        return result.addCallback(got_result)

    def test_tasks_are_isolated_marks(self):
        """
        Changes attempted on one task should be reset before the next
        task is run.  In this test, we try to run two different
        operations, first installing package 2, then upgrading
        anything available.  The first installation will fail for lack
        of superuser privileges, and the second one will succeed since
        there's nothing to upgrade.  If tasks are mixed up, the second
        operation will fail too, because the installation of package 2
        is still marked in the facade.
        """
        self.log_helper.ignore_errors(".*dpkg")

        installable_hash = self.set_pkg2_satisfied()
        installed_hash = self.set_pkg1_installed()
        self.store.set_hash_ids({installed_hash: 1, installable_hash: 2})

        self.store.add_task("changer",
                            {"type": "change-packages", "install": [2],
                             "operation-id": 123})
        self.store.add_task("changer",
                            {"type": "change-packages", "upgrade-all": True,
                             "operation-id": 124})

        result = self.changer.handle_tasks()

        def got_result(result):
            message = self.get_pending_messages()[1]
            self.assertEqual(124, message["operation-id"])
            self.assertEqual("change-packages-result", message["type"])
            self.assertNotEqual(0, message["result-code"])

        return result.addCallback(got_result)

    def test_tasks_are_isolated_cache(self):
        """
        The package (APT) cache should be reset between task runs.
        In this test, we try to run two different operations, first
        installing package 2, then removing package 1.  Both tasks will
        fail for lack of superuser privileges.  If the package cache
        isn't reset between tasks, the second operation will fail with a
        dependency error, since it will be marked for installation, but
        we haven't explicitly marked it so.
        """
        self.log_helper.ignore_errors(".*dpkg")

        installable_hash = self.set_pkg2_satisfied()
        installed_hash = self.set_pkg1_installed()
        self.store.set_hash_ids({installed_hash: 1, installable_hash: 2})

        self.store.add_task("changer",
                            {"type": "change-packages", "install": [2],
                             "operation-id": 123})
        self.store.add_task("changer",
                            {"type": "change-packages", "remove": [1],
                             "operation-id": 124})

        result = self.changer.handle_tasks()

        def got_result(result):
            message1, message2 = self.get_pending_messages()
            self.assertEqual(123, message1["operation-id"])
            self.assertEqual("change-packages-result", message1["type"])
            self.assertEqual(ERROR_RESULT, message1["result-code"])
            self.assertEqual(124, message2["operation-id"])
            self.assertEqual("change-packages-result", message2["type"])
            self.assertEqual(ERROR_RESULT, message2["result-code"])

        return result.addCallback(got_result)

    def test_successful_operation(self):
        """Simulate a *very* successful operation.

        We'll do that by hacking perform_changes(), and returning our
        *very* successful operation result.
        """
        installed_hash = self.set_pkg1_installed()
        self.store.set_hash_ids({installed_hash: 1, HASH2: 2, HASH3: 3})
        self.store.add_task("changer",
                            {"type": "change-packages", "install": [2],
                             "operation-id": 123})

        def return_good_result(self):
            return "Yeah, I did whatever you've asked for!"
        self.replace_perform_changes(return_good_result)

        result = self.changer.handle_tasks()

        def got_result(result):
            self.assertMessages(self.get_pending_messages(),
                                [{"operation-id": 123,
                                  "result-code": 1,
                                  "result-text": "Yeah, I did whatever you've "
                                                 "asked for!",
                                  "type": "change-packages-result"}])
        return result.addCallback(got_result)

    def test_successful_operation_with_binaries(self):
        """
        Simulate a successful operation involving server-generated binary
        packages.
        """
        self.store.set_hash_ids({HASH3: 3})
        self.store.add_task("changer",
                            {"type": "change-packages", "install": [2, 3],
                             "binaries": [(HASH2, 2, PKGDEB2)],
                             "operation-id": 123})

        def return_good_result(self):
            return "Yeah, I did whatever you've asked for!"
        self.replace_perform_changes(return_good_result)
        self.disable_clear_channels()

        result = self.changer.handle_tasks()

        def got_result(result):
            self.assertMessages(self.get_pending_messages(),
                                [{"operation-id": 123,
                                  "result-code": 1,
                                  "result-text": "Yeah, I did whatever you've "
                                                 "asked for!",
                                  "type": "change-packages-result"}])
        return result.addCallback(got_result)

    def test_global_upgrade(self):
        """
        Besides asking for individual changes, the server may also request
        the client to perform a global upgrade.  This would be the equivalent
        of a "apt-get upgrade" command being executed in the command line.
        """
        hash1, hash2 = self.set_pkg2_upgrades_pkg1()
        self.store.set_hash_ids({hash1: 1, hash2: 2})

        self.store.add_task("changer",
                            {"type": "change-packages", "upgrade-all": True,
                             "operation-id": 123})

        result = self.changer.handle_tasks()

        def got_result(result):
            self.assertMessages(self.get_pending_messages(),
                                [{"operation-id": 123,
                                  "must-install": [2],
                                  "must-remove": [1],
                                  "result-code": 101,
                                  "type": "change-packages-result"}])

        return result.addCallback(got_result)

    def test_global_upgrade_with_nothing_to_do(self):

        self.store.add_task("changer",
                            {"type": "change-packages", "upgrade-all": True,
                             "operation-id": 123})

        result = self.changer.handle_tasks()

        def got_result(result):
            self.assertMessages(self.get_pending_messages(),
                                [{"operation-id": 123,
                                  "result-code": 1,
                                  "result-text":
                                      u"No changes required; all changes "
                                      u"already performed",
                                  "type": "change-packages-result"}])

        return result.addCallback(got_result)

    def test_run_with_no_update_stamp(self):
        """
        If the update-stamp file is not there yet, the package changer
        just exists.
        """
        os.remove(self.config.update_stamp_filename)

        def assert_log(ignored):
            self.assertIn("The package-reporter hasn't run yet, exiting.",
                          self.logfile.getvalue())

        result = self.changer.run()
        return result.addCallback(assert_log)

    @patch("os.system")
    def test_spawn_reporter_after_running(self, system_mock):
        self.config.bindir = "/fake/bin"
        # Add a task that will do nothing besides producing an
        # answer.  The reporter is only spawned if at least one
        # task was handled.
        self.store.add_task("changer", {"type": "change-packages",
                                        "operation-id": 123})

        self.successResultOf(self.changer.run())

        system_mock.assert_called_once_with(
            "/fake/bin/landscape-package-reporter")

    @patch("os.system")
    def test_spawn_reporter_after_running_with_config(self, system_mock):
        """The changer passes the config to the reporter when running it."""
        self.config.config = "test.conf"
        self.config.bindir = "/fake/bin"

        # Add a task that will do nothing besides producing an
        # answer.  The reporter is only spawned if at least one
        # task was handled.
        self.store.add_task("changer", {"type": "change-packages",
                                        "operation-id": 123})
        self.successResultOf(self.changer.run())

        system_mock.assert_called_once_with(
            "/fake/bin/landscape-package-reporter -c test.conf")

    @patch("os.getuid", return_value=0)
    @patch("os.setgid")
    @patch("os.setuid")
    @patch("os.system")
    def test_set_effective_uid_and_gid_when_running_as_root(
            self, system_mock, setuid_mock, setgid_mock, getuid_mock):
        """
        After the package changer has run, we want the package-reporter to run
        to report the recent changes.  If we're running as root, we want to
        change to the "landscape" user and "landscape" group.
        """
        self.config.bindir = "/fake/bin"

        class FakeGroup(object):
            gr_gid = 199

        class FakeUser(object):
            pw_uid = 199

        # We are running as root
        with patch("grp.getgrnam", return_value=FakeGroup()) as grnam_mock:
            with patch("pwd.getpwnam", return_value=FakeUser()) as pwnam_mock:
                # Add a task that will do nothing besides producing an
                # answer.  The reporter is only spawned if at least
                # one task was handled.
                self.store.add_task("changer", {"type": "change-packages",
                                                "operation-id": 123})
                self.successResultOf(self.changer.run())

        grnam_mock.assert_called_once_with("landscape")
        setgid_mock.assert_called_once_with(199)
        pwnam_mock.assert_called_once_with("landscape")
        setuid_mock.assert_called_once_with(199)
        system_mock.assert_called_once_with(
            "/fake/bin/landscape-package-reporter")

    def test_run(self):
        changer_mock = patch.object(self, "changer")

        results = [Deferred() for i in range(2)]

        changer_mock.use_hash_id_db = Mock(return_value=results[0])
        changer_mock.handle_tasks = Mock(return_value=results[1])

        self.changer.run()

        changer_mock.use_hash_id_db.assert_not_called()
        changer_mock.handle_tasks.assert_not_called()

        for deferred in reversed(results):
            deferred.callback(None)

    @patch("os.system")
    def test_dont_spawn_reporter_after_running_if_nothing_done(
            self, system_mock):
        self.successResultOf(self.changer.run())
        system_mock.assert_not_called()

    def test_main(self):
        pid = os.getpid() + 1
        with patch("os.getpgrp", return_value=pid) as getpgrp_mock:
            with patch("os.setsid") as setsid_mock:
                with patch("landscape.client.package.changer.run_task_handler",
                           return_value="RESULT") as run_task_handler_mock:
                    self.assertEqual(main(["ARGS"]), "RESULT")

        getpgrp_mock.assert_called_once_with()
        setsid_mock.assert_called_once_with()
        run_task_handler_mock.assert_called_once_with(PackageChanger, ["ARGS"])

    def test_main_run_from_shell(self):
        """
        We want the getpid and getpgrp to return the same process id
        this simulates the case where the process is already the process
        session leader, in this case the os.setsid would fail.
        """
        pid = os.getpid()
        with patch("os.getpgrp", return_value=pid) as pgrp:
            mocktarget = "landscape.client.package.changer.run_task_handler"
            with patch(mocktarget) as task:
                main(["ARGS"])

        pgrp.assert_called_once_with()
        task.assert_called_once_with(PackageChanger, ["ARGS"])

    def test_find_command_with_bindir(self):
        self.config.bindir = "/spam/eggs"
        command = PackageChanger.find_command(self.config)

        self.assertEqual("/spam/eggs/landscape-package-changer", command)

    def test_find_command_default(self):
        expected = os.path.join(
            os.path.dirname(os.path.abspath(sys.argv[0])),
            "landscape-package-changer")
        command = PackageChanger.find_command()

        self.assertEqual(expected, command)

    def test_transaction_error_with_unicode_data(self):
        self.store.set_hash_ids({HASH1: 1})
        self.store.add_task("changer",
                            {"type": "change-packages", "install": [1],
                             "operation-id": 123})

        def raise_error(self):
            raise TransactionError(u"áéíóú")
        self.replace_perform_changes(raise_error)
        self.disable_clear_channels()

        result = self.changer.handle_tasks()

        def got_result(result):
            self.assertMessages(self.get_pending_messages(),
                                [{"operation-id": 123,
                                  "result-code": 100,
                                  "result-text": u"áéíóú",
                                  "type": "change-packages-result"}])
        return result.addCallback(got_result)

    def test_update_stamp_exists(self):
        """
        L{PackageChanger.update_stamp_exists} returns C{True} if the
        update-stamp file is there, C{False} otherwise.
        """
        self.assertTrue(self.changer.update_stamp_exists())
        os.remove(self.config.update_stamp_filename)
        self.assertFalse(self.changer.update_stamp_exists())

    def test_update_stamp_exists_notifier(self):
        """
        L{PackageChanger.update_stamp_exists} also checks the existence of the
        C{update_notifier_stamp} file.
        """
        self.assertTrue(self.changer.update_stamp_exists())
        os.remove(self.config.update_stamp_filename)
        self.assertFalse(self.changer.update_stamp_exists())
        self.changer.update_notifier_stamp = self.makeFile("")
        self.assertTrue(self.changer.update_stamp_exists())

    def test_binaries_path(self):
        self.assertEqual(
            self.config.binaries_path,
            os.path.join(self.config.data_path, "package", "binaries"))

    def test_init_channels(self):
        """
        The L{PackageChanger.init_channels} method makes the given
        Debian packages available in a facade channel.
        """
        binaries = [(HASH1, 111, PKGDEB1), (HASH2, 222, PKGDEB2)]

        self.facade.reset_channels()
        self.changer.init_channels(binaries)

        binaries_path = self.config.binaries_path
        self.assertFileContent(os.path.join(binaries_path, "111.deb"),
                               base64.decodebytes(PKGDEB1))
        self.assertFileContent(os.path.join(binaries_path, "222.deb"),
                               base64.decodebytes(PKGDEB2))
        self.assertEqual(
            self.facade.get_channels(),
            self.get_binaries_channels(binaries_path))

        self.assertEqual(self.store.get_hash_ids(), {HASH1: 111, HASH2: 222})

        self.facade.ensure_channels_reloaded()
        [pkg1, pkg2] = sorted(self.facade.get_packages(),
                              key=self.get_package_name)
        self.assertEqual(self.facade.get_package_hash(pkg1), HASH1)
        self.assertEqual(self.facade.get_package_hash(pkg2), HASH2)

    def test_init_channels_with_existing_hash_id_map(self):
        """
        The L{PackageChanger.init_channels} behaves well even if the
        hash->id mapping for a given deb is already in the L{PackageStore}.
        """
        self.store.set_hash_ids({HASH1: 111})
        self.changer.init_channels([(HASH1, 111, PKGDEB1)])
        self.assertEqual(self.store.get_hash_ids(), {HASH1: 111})

    def test_init_channels_with_existing_binaries(self):
        """
        The L{PackageChanger.init_channels} removes Debian packages
        from previous runs.
        """
        existing_deb_path = os.path.join(self.config.binaries_path, "123.deb")
        self.makeFile(path=existing_deb_path, content="foo")
        self.changer.init_channels([])
        self.assertFalse(os.path.exists(existing_deb_path))

    def test_binaries_available_in_cache(self):
        """
        If binaries are included in the changes-packages message, those
        will be added to the facade's cache.
        """
        # Make sure to turn off automatic rereading of Packages file,
        # like it is by default.
        self.facade.refetch_package_index = False
        self.assertEqual(None, self.facade.get_package_by_hash(HASH2))
        self.store.add_task("changer",
                            {"type": "change-packages", "install": [2],
                             "binaries": [(HASH2, 2, PKGDEB2)],
                             "operation-id": 123})

        def return_good_result(self):
            return "Yeah, I did whatever you've asked for!"
        self.replace_perform_changes(return_good_result)

        result = self.changer.handle_tasks()

        def got_result(result):
            self.assertNotEqual(None, self.facade.get_package_by_hash(HASH2))
            self.assertFalse(self.facade.refetch_package_index)

        return result.addCallback(got_result)

    def test_change_package_holds(self):
        """
        The L{PackageChanger.handle_tasks} method appropriately creates and
        deletes package holds as requested by the C{change-packages}
        message.
        """
        self._add_system_package("foo")
        self._add_system_package("baz")
        self.facade.reload_channels()
        self._hash_packages_by_name(self.facade, self.store, "foo")
        self._hash_packages_by_name(self.facade, self.store, "baz")
        [foo] = self.facade.get_packages_by_name("foo")
        [baz] = self.facade.get_packages_by_name("baz")
        self.facade.set_package_hold(baz)
        # Make sure that the mtime of the dpkg status file is old when
        # apt loads it, so that it will be reloaded when asserting the
        # test result.
        old_mtime = time.time() - 10
        os.utime(self.facade._dpkg_status, (old_mtime, old_mtime))
        self.facade.reload_channels()
        self.store.add_task("changer", {"type": "change-packages",
                                        "hold": [foo.package.id],
                                        "remove-hold": [baz.package.id],
                                        "operation-id": 123})

        def assert_result(result):
            self.facade.reload_channels()
            self.assertEqual(["foo"], self.facade.get_package_holds())
            self.assertIn("Queuing response with change package results "
                          "to exchange urgently.", self.logfile.getvalue())
            self.assertMessages(
                self.get_pending_messages(),
                [{"type": "change-packages-result",
                  "operation-id": 123,
                  "result-text": "Package holds successfully changed.",
                  "result-code": 1}])

        result = self.changer.handle_tasks()
        return result.addCallback(assert_result)

    def test_create_package_holds_with_identical_version(self):
        """
        The L{PackageChanger.handle_tasks} method appropriately creates
        holds as requested by the C{change-packages} message even
        when versions from two different packages are the same.
        """
        self._add_system_package("foo", version="1.1")
        self._add_system_package("bar", version="1.1")
        self.facade.reload_channels()
        self._hash_packages_by_name(self.facade, self.store, "foo")
        self._hash_packages_by_name(self.facade, self.store, "bar")
        [foo] = self.facade.get_packages_by_name("foo")
        [bar] = self.facade.get_packages_by_name("bar")
        self.facade.reload_channels()
        self.store.add_task("changer", {"type": "change-packages",
                                        "hold": [foo.package.id,
                                                 bar.package.id],
                                        "operation-id": 123})

        def assert_result(result):
            self.facade.reload_channels()
            self.assertEqual(["bar", "foo"], self.facade.get_package_holds())

        result = self.changer.handle_tasks()
        return result.addCallback(assert_result)

    def test_delete_package_holds_with_identical_version(self):
        """
        The L{PackageChanger.handle_tasks} method appropriately deletes
        holds as requested by the C{change-packages} message even
        when versions from two different packages are the same.
        """
        self._add_system_package("foo", version="1.1")
        self._add_system_package("bar", version="1.1")
        self.facade.reload_channels()
        self._hash_packages_by_name(self.facade, self.store, "foo")
        self._hash_packages_by_name(self.facade, self.store, "bar")
        [foo] = self.facade.get_packages_by_name("foo")
        [bar] = self.facade.get_packages_by_name("bar")
        self.facade.set_package_hold(foo)
        self.facade.set_package_hold(bar)
        self.facade.reload_channels()
        self.store.add_task("changer", {"type": "change-packages",
                                        "remove-hold": [foo.package.id,
                                                        bar.package.id],
                                        "operation-id": 123})

        def assert_result(result):
            self.facade.reload_channels()
            self.assertEqual([], self.facade.get_package_holds())

        result = self.changer.handle_tasks()
        return result.addCallback(assert_result)

    def test_change_package_holds_create_already_held(self):
        """
        If the C{change-packages} message requests to add holds for
        packages that are already held, the activity succeeds, since the
        end result is that the requested package holds are there.
        """
        self._add_system_package("foo")
        self.facade.reload_channels()
        self._hash_packages_by_name(self.facade, self.store, "foo")
        [foo] = self.facade.get_packages_by_name("foo")
        self.facade.set_package_hold(foo)
        self.facade.reload_channels()
        self.store.add_task("changer", {"type": "change-packages",
                                        "hold": [foo.package.id],
                                        "operation-id": 123})

        def assert_result(result):
            self.facade.reload_channels()
            self.assertEqual(["foo"], self.facade.get_package_holds())
            self.assertIn("Queuing response with change package results "
                          "to exchange urgently.", self.logfile.getvalue())
            self.assertMessages(
                self.get_pending_messages(),
                [{"type": "change-packages-result",
                  "operation-id": 123,
                  "result-text": "Package holds successfully changed.",
                  "result-code": 1}])

        result = self.changer.handle_tasks()
        return result.addCallback(assert_result)

    def test_change_package_holds_create_other_version_installed(self):
        """
        If the C{change-packages} message requests to add holds for
        packages that have a different version installed than the one
        being requested to hold, the activity fails.

        The whole activity is failed, meaning that other valid hold
        requests won't get processed.
        """
        self._add_system_package("foo", version="1.0")
        self._add_package_to_deb_dir(
            self.repository_dir, "foo", version="2.0")
        self._add_system_package("bar", version="1.0")
        self._add_package_to_deb_dir(
            self.repository_dir, "bar", version="2.0")
        self.facade.reload_channels()
        [foo1, foo2] = sorted(self.facade.get_packages_by_name("foo"))
        [bar1, bar2] = sorted(self.facade.get_packages_by_name("bar"))
        self.store.set_hash_ids({self.facade.get_package_hash(foo1): 1,
                                 self.facade.get_package_hash(foo2): 2,
                                 self.facade.get_package_hash(bar1): 3,
                                 self.facade.get_package_hash(bar2): 4})
        self.facade.reload_channels()
        self.store.add_task("changer", {"type": "change-packages",
                                        "hold": [2, 3],
                                        "operation-id": 123})

        def assert_result(result):
            self.facade.reload_channels()
            self.assertEqual([], self.facade.get_package_holds())
            self.assertIn("Queuing response with change package results "
                          "to exchange urgently.", self.logfile.getvalue())
            self.assertMessages(
                self.get_pending_messages(),
                [{"type": "change-packages-result",
                  "operation-id": 123,
                  "result-text": "Cannot perform the changes, since the" +
                                 " following packages are not installed: foo",
                  "result-code": 100}])

        result = self.changer.handle_tasks()
        return result.addCallback(assert_result)

    def test_change_package_holds_create_not_installed(self):
        """
        If the C{change-packages} message requests to add holds for
        packages that aren't installed, the whole activity is failed. If
        multiple holds are specified, those won't be added. There's no
        difference between a package that is available in some
        repository and a package that the facade doesn't know about at
        all.
        """
        self._add_system_package("foo")
        self._add_package_to_deb_dir(self.repository_dir, "bar")
        self._add_package_to_deb_dir(self.repository_dir, "baz")
        self.facade.reload_channels()
        self._hash_packages_by_name(self.facade, self.store, "foo")
        self._hash_packages_by_name(self.facade, self.store, "bar")
        self._hash_packages_by_name(self.facade, self.store, "baz")
        [foo] = self.facade.get_packages_by_name("foo")
        [bar] = self.facade.get_packages_by_name("bar")
        [baz] = self.facade.get_packages_by_name("baz")
        self.store.add_task("changer", {"type": "change-packages",
                                        "hold": [foo.package.id,
                                                 bar.package.id,
                                                 baz.package.id],
                                        "operation-id": 123})

        def assert_result(result):
            self.facade.reload_channels()
            self.assertEqual([], self.facade.get_package_holds())
            self.assertIn("Queuing response with change package results "
                          "to exchange urgently.", self.logfile.getvalue())
            self.assertMessages(
                self.get_pending_messages(),
                [{"type": "change-packages-result",
                  "operation-id": 123,
                  "result-text": "Cannot perform the changes, since the "
                  "following packages are not installed: "
                  "%s, %s" % tuple(sorted([bar.package.name,
                                           baz.package.name])),
                  "result-code": 100}])

        result = self.changer.handle_tasks()
        return result.addCallback(assert_result)

    def test_change_package_holds_create_unknown_hash(self):
        """
        If the C{change-packages} message requests to add holds for
        packages that the client doesn't know about results in a not yet
        synchronized message and a failure of the operation.
        """

        self.store.add_task("changer",
                            {"type": "change-packages",
                             "hold": [123],
                             "operation-id": 123})

        thetime = time.time()
        with patch("time.time") as time_mock:
            time_mock.return_value = thetime + UNKNOWN_PACKAGE_DATA_TIMEOUT
            result = self.changer.handle_tasks()
        time_mock.assert_any_call()

        self.assertIn("Package data not yet synchronized with server (123)",
                      self.logfile.getvalue())

        def got_result(result):
            message = {"type": "change-packages-result",
                       "operation-id": 123,
                       "result-code": 100,
                       "result-text": "Package data has changed. "
                                      "Please retry the operation."}
            self.assertMessages(self.get_pending_messages(), [message])
            self.assertEqual(self.store.get_next_task("changer"), None)
        return result.addCallback(got_result)

    def test_change_package_holds_delete_not_held(self):
        """
        If the C{change-packages} message requests to remove holds
        for packages that aren't held, the activity succeeds if the
        right version is installed, since the end result is that the
        hold is removed.
        """
        self._add_package_to_deb_dir(self.repository_dir, "foo")
        self.facade.reload_channels()
        self._hash_packages_by_name(self.facade, self.store, "foo")
        [foo] = self.facade.get_packages_by_name("foo")
        self.store.add_task("changer", {"type": "change-packages",
                                        "remove-hold": [foo.package.id],
                                        "operation-id": 123})

        def assert_result(result):
            self.facade.reload_channels()
            self.assertEqual([], self.facade.get_package_holds())
            self.assertIn("Queuing response with change package results "
                          "to exchange urgently.", self.logfile.getvalue())
            self.assertMessages(
                self.get_pending_messages(),
                [{"type": "change-packages-result",
                  "operation-id": 123,
                  "result-text": "Package holds successfully changed.",
                  "result-code": 1}])

        result = self.changer.handle_tasks()
        return result.addCallback(assert_result)

    def test_change_package_holds_delete_different_version_held(self):
        """
        If the C{change-packages} message requests to remove holds
        for packages that aren't held, the activity succeeds if the
        right version is installed, since the end result is that the
        hold is removed.
        """
        self._add_system_package("foo", version="1.0")
        self._add_package_to_deb_dir(
            self.repository_dir, "foo", version="2.0")
        self.facade.reload_channels()
        [foo1, foo2] = sorted(self.facade.get_packages_by_name("foo"))
        self.store.set_hash_ids({self.facade.get_package_hash(foo1): 1,
                                 self.facade.get_package_hash(foo2): 2})
        self.facade.mark_install(foo1)
        self.facade.mark_hold(foo1)
        self.facade.perform_changes()
        self.facade.reload_channels()
        self.store.add_task("changer", {"type": "change-packages",
                                        "remove-hold": [2],
                                        "operation-id": 123})

        def assert_result(result):
            self.facade.reload_channels()
            self.assertEqual(["foo"], self.facade.get_package_holds())
            self.assertIn("Queuing response with change package results "
                          "to exchange urgently.", self.logfile.getvalue())
            self.assertMessages(
                self.get_pending_messages(),
                [{"type": "change-packages-result",
                  "operation-id": 123,
                  "result-text": "Package holds successfully changed.",
                  "result-code": 1}])

        result = self.changer.handle_tasks()
        return result.addCallback(assert_result)

    def test_change_package_holds_delete_not_installed(self):
        """
        If the C{change-packages} message requests to remove holds
        for packages that aren't installed, the activity succeeds, since
        the end result is still that the package isn't held at the
        requested version.
        """
        self._add_system_package("foo")
        self.facade.reload_channels()
        self._hash_packages_by_name(self.facade, self.store, "foo")
        [foo] = self.facade.get_packages_by_name("foo")
        self.store.add_task("changer", {"type": "change-packages",
                                        "remove-hold": [foo.package.id],
                                        "operation-id": 123})

        def assert_result(result):
            self.facade.reload_channels()
            self.assertEqual([], self.facade.get_package_holds())
            self.assertIn("Queuing response with change package results "
                          "to exchange urgently.", self.logfile.getvalue())
            self.assertMessages(
                self.get_pending_messages(),
                [{"type": "change-packages-result",
                  "operation-id": 123,
                  "result-text": "Package holds successfully changed.",
                  "result-code": 1}])

        result = self.changer.handle_tasks()
        return result.addCallback(assert_result)

    def test_change_package_locks(self):
        """
        The L{PackageChanger.handle_tasks} method fails
        change-package-locks activities, since it can't add or remove
        locks because apt doesn't support this.
        """
        self.store.add_task("changer", {"type": "change-package-locks",
                                        "create": [("foo", ">=", "1.0")],
                                        "delete": [("bar", None, None)],
                                        "operation-id": 123})

        def assert_result(result):
            self.assertMessages(
                self.get_pending_messages(),
                [{"type": "operation-result",
                  "operation-id": 123,
                  "status": FAILED,
                  "result-text": "This client doesn't support package locks.",
                  "result-code": 1}])

        result = self.changer.handle_tasks()
        return result.addCallback(assert_result)

    def test_change_packages_with_binaries_removes_binaries(self):
        """
        After the C{change-packages} handler has installed the binaries,
        the binaries and the internal facade deb source is removed.
        """
        self.store.add_task("changer",
                            {"type": "change-packages", "install": [2],
                             "binaries": [(HASH2, 2, PKGDEB2)],
                             "operation-id": 123})

        def return_good_result(self):
            return "Yeah, I did whatever you've asked for!"
        self.replace_perform_changes(return_good_result)

        result = self.changer.handle_tasks()

        def got_result(result):
            self.assertMessages(self.get_pending_messages(),
                                [{"operation-id": 123,
                                  "result-code": 1,
                                  "result-text": "Yeah, I did whatever you've "
                                                 "asked for!",
                                  "type": "change-packages-result"}])
            self.assertEqual([], os.listdir(self.config.binaries_path))
            self.assertFalse(
                os.path.exists(self.facade._get_internal_sources_list()))

        return result.addCallback(got_result)

    def test_change_packages_with_reboot_flag(self):
        """
        When a C{reboot-if-necessary} flag is passed in the C{change-packages},
        A C{ShutdownProtocolProcess} is created and the package result change
        is returned.
        """
        self.store.add_task("changer",
                            {"type": "change-packages", "install": [2],
                             "binaries": [(HASH2, 2, PKGDEB2)],
                             "operation-id": 123,
                             "reboot-if-necessary": True})

        def return_good_result(self):
            return "Yeah, I did whatever you've asked for!"
        self.replace_perform_changes(return_good_result)

        result = self.changer.handle_tasks()

        def got_result(result):
            self.assertIn("Landscape is rebooting the system",
                          self.logfile.getvalue())
            self.assertMessages(self.get_pending_messages(),
                                [{"operation-id": 123,
                                  "result-code": 1,
                                  "result-text": "Yeah, I did whatever you've "
                                                 "asked for!",
                                  "type": "change-packages-result"}])

        self.landscape_reactor.advance(5)
        [arguments] = self.process_factory.spawns
        protocol = arguments[0]
        protocol.processEnded(Failure(ProcessDone(status=0)))
        self.broker_service.reactor.advance(100)
        self.landscape_reactor.advance(10)
        return result.addCallback(got_result)

    def test_change_packages_with_failed_reboot(self):
        """
        When a C{reboot-if-necessary} flag is passed in the C{change-packages},
        A C{ShutdownProtocol} is created and the package result change is
        returned, even if the reboot fails.
        """
        self.store.add_task("changer",
                            {"type": "change-packages", "install": [2],
                             "binaries": [(HASH2, 2, PKGDEB2)],
                             "operation-id": 123,
                             "reboot-if-necessary": True})

        def return_good_result(self):
            return "Yeah, I did whatever you've asked for!"
        self.replace_perform_changes(return_good_result)

        result = self.changer.handle_tasks()

        def got_result(result):
            self.assertMessages(self.get_pending_messages(),
                                [{"operation-id": 123,
                                  "result-code": 1,
                                  "result-text": "Yeah, I did whatever you've "
                                                 "asked for!",
                                  "type": "change-packages-result"}])
            self.log_helper.ignore_errors(ShutdownFailedError)

        self.landscape_reactor.advance(5)
        [arguments] = self.process_factory.spawns
        protocol = arguments[0]
        protocol.processEnded(Failure(ProcessTerminated(exitCode=1)))
        self.landscape_reactor.advance(10)
        return result.addCallback(got_result)

    def test_no_exchange_after_reboot(self):
        """
        After initiating a reboot process, no more messages are exchanged.
        """
        self.store.add_task("changer",
                            {"type": "change-packages", "install": [2],
                             "binaries": [(HASH2, 2, PKGDEB2)],
                             "operation-id": 123,
                             "reboot-if-necessary": True})

        def return_good_result(self):
            return "Yeah, I did whatever you've asked for!"
        self.replace_perform_changes(return_good_result)

        result = self.changer.handle_tasks()

        def got_result(result):
            # Advance both reactors so the pending messages are exchanged.
            self.broker_service.reactor.advance(100)
            self.landscape_reactor.advance(10)
            payloads = self.broker_service.exchanger._transport.payloads
            self.assertEqual(0, len(payloads))

        self.landscape_reactor.advance(5)

        [arguments] = self.process_factory.spawns
        protocol = arguments[0]
        protocol.processEnded(Failure(ProcessDone(status=0)))
        self.broker_service.reactor.advance(100)
        self.landscape_reactor.advance(10)
        return result.addCallback(got_result)

    def test_run_gets_session_id(self):
        """
        Invoking L{PackageChanger.run} results in the session ID being fetched.
        """
        def assert_session_id(ignored):
            self.assertTrue(self.changer._session_id is not None)

        self.changer._session_id = None
        result = self.changer.run()
        return result.addCallback(assert_session_id)
