# -*- encoding: utf-8 -*-
import base64
import time
import sys
import os

from twisted.internet.defer import Deferred

try:
    from smart.cache import Provides
except ImportError:
    # Smart is optional if AptFacade is being used.
    pass

from landscape.lib.fs import create_file, read_file, touch_file
from landscape.package.changer import (
    PackageChanger, main, find_changer_command, UNKNOWN_PACKAGE_DATA_TIMEOUT,
    SUCCESS_RESULT, DEPENDENCY_ERROR_RESULT, POLICY_ALLOW_INSTALLS,
    POLICY_ALLOW_ALL_CHANGES, ERROR_RESULT)
from landscape.package.store import PackageStore
from landscape.package.facade import (
    DependencyError, TransactionError, SmartError, has_new_enough_apt)
from landscape.package.changer import (
    PackageChangerConfiguration, ChangePackagesResult)
from landscape.tests.mocker import ANY
from landscape.tests.helpers import (
    LandscapeTest, BrokerServiceHelper)
from landscape.package.tests.helpers import (
    SmartFacadeHelper, HASH1, HASH2, HASH3, PKGDEB1, PKGDEB2, PKGNAME2,
    AptFacadeHelper, SimpleRepositoryHelper)
from landscape.manager.manager import FAILED, SUCCEEDED


class PackageChangerTestMixin(object):

    def disable_clear_channels(self):
        """Disable clear_channels(), so that it doesn't remove test setup.

        This is useful for change-packages tests, which will call
        facade.clear_channels(). Normally that's safe, but since we used
        the facade to set up channels, we don't want them to be removed.
        """
        self._facade.clear_channels = lambda: None

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
        self.store.set_hash_ids({"hash": 456})
        self.store.add_task("changer",
                            {"type": "change-packages", "install": [456],
                             "operation-id": 123})

        self.changer.handle_tasks()

        self.assertIn("Package data not yet synchronized with server ('hash')",
                      self.logfile.getvalue())
        self.assertTrue(self.store.get_next_task("changer"))

    def test_remove_unknown_package(self):
        self.store.set_hash_ids({"hash": 456})
        self.store.add_task("changer",
                            {"type": "change-packages", "remove": [456],
                             "operation-id": 123})

        self.changer.handle_tasks()

        self.assertIn("Package data not yet synchronized with server ('hash')",
                      self.logfile.getvalue())
        self.assertTrue(self.store.get_next_task("changer"))

    def test_unknown_data_timeout(self):
        """After a while, unknown package data is reported as an error.

        In these cases a warning is logged, and the task is removed.
        """
        self.store.add_task("changer",
                            {"type": "change-packages", "remove": [123],
                             "operation-id": 123})

        time_mock = self.mocker.replace("time.time")
        time_mock()
        self.mocker.result(time.time() + UNKNOWN_PACKAGE_DATA_TIMEOUT)
        self.mocker.count(1, None)
        self.mocker.replay()

        try:
            result = self.changer.handle_tasks()
            self.mocker.verify()
        finally:
            # Reset it earlier so that Twisted has the true time function.
            self.mocker.reset()

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

        self.facade.clear_channels = lambda : None
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

        self.mocker.order()
        self.facade.perform_changes = self.mocker.mock()
        self.facade.perform_changes()
        self.mocker.throw(DependencyError([package1]))

        self.facade.mark_install = self.mocker.mock()
        self.facade.mark_install(package1)
        self.facade.perform_changes()
        self.mocker.result("success")
        self.mocker.replay()

        result = self.changer.change_packages(POLICY_ALLOW_INSTALLS)

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
        self.facade.perform_changes = self.mocker.mock()
        self.facade.perform_changes()
        self.mocker.throw(DependencyError([package1, package2]))
        self.mocker.replay()

        result = self.changer.change_packages(POLICY_ALLOW_INSTALLS)

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

        self.facade.perform_changes = self.mocker.mock()
        self.facade.perform_changes()
        self.mocker.throw(DependencyError([package1]))
        self.facade.perform_changes()
        self.mocker.throw(DependencyError([package2]))
        self.mocker.replay()

        result = self.changer.change_packages(POLICY_ALLOW_INSTALLS)

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
        self.changer.change_packages = self.mocker.mock()
        self.changer.change_packages(POLICY_ALLOW_INSTALLS)
        result = ChangePackagesResult()
        result.code = SUCCESS_RESULT
        self.mocker.result(result)
        self.mocker.replay()
        self.facade.clear_channels = lambda : None
        return self.changer.handle_tasks()

    def test_perform_changes_with_policy_allow_all_changes(self):
        """
        The C{POLICY_ALLOW_ALL_CHANGES} policy allows any needed additional
        package to be installed or removed.
        """
        installed_hash = self.set_pkg1_installed()
        self.store.set_hash_ids({installed_hash: 1, HASH2: 2})
        self.facade.reload_channels()

        self.mocker.order()
        package1 = self.facade.get_package_by_hash(installed_hash)
        [package2] = self.facade.get_packages_by_name("name2")
        self.facade.perform_changes = self.mocker.mock()
        self.facade.perform_changes()
        self.mocker.throw(DependencyError([package1, package2]))
        self.facade.mark_install = self.mocker.mock()
        self.facade.mark_remove = self.mocker.mock()
        self.facade.mark_install(package2)
        self.facade.mark_remove(package1)
        self.facade.perform_changes()
        self.mocker.result("success")
        self.mocker.replay()

        result = self.changer.change_packages(POLICY_ALLOW_ALL_CHANGES)

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
            result_text = self.get_transaction_error_message()
            messages = self.get_pending_messages()
            self.assertEqual(len(messages), 1)
            message = messages[0]
            self.assertEqual(message["operation-id"], 123)
            self.assertEqual(message["result-code"], 100)
            self.assertIn(result_text, message["result-text"])
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
        The package (apt/smart) cache should be reset between task runs.
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
        of a "smart upgrade" command being executed in the command line.
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

    def test_spawn_reporter_after_running(self):
        output_filename = self.makeFile("REPORTER NOT RUN")
        reporter_filename = self.makeFile("#!/bin/sh\necho REPORTER RUN > %s" %
                                          output_filename)
        os.chmod(reporter_filename, 0755)

        find_command_mock = self.mocker.replace(
            "landscape.package.reporter.find_reporter_command")
        find_command_mock()
        self.mocker.result(reporter_filename)
        self.mocker.replay()

        # Add a task that will do nothing besides producing an answer.
        # The reporter is only spawned if at least one task was handled.
        self.store.add_task("changer", {"type": "change-packages",
                                        "operation-id": 123})

        result = self.changer.run()

        def got_result(result):
            self.assertEqual(open(output_filename).read().strip(),
                             "REPORTER RUN")
        return result.addCallback(got_result)

    def test_spawn_reporter_after_running_with_config(self):
        """The changer passes the config to the reporter when running it."""
        self.config.config = "test.conf"
        output_filename = self.makeFile("REPORTER NOT RUN")
        reporter_filename = self.makeFile("#!/bin/sh\necho ARGS $@ > %s" %
                                          output_filename)
        os.chmod(reporter_filename, 0755)

        find_command_mock = self.mocker.replace(
            "landscape.package.reporter.find_reporter_command")
        find_command_mock()
        self.mocker.result(reporter_filename)
        self.mocker.replay()

        # Add a task that will do nothing besides producing an answer.
        # The reporter is only spawned if at least one task was handled.
        self.store.add_task("changer", {"type": "change-packages",
                                        "operation-id": 123})

        result = self.changer.run()

        def got_result(result):
            self.assertEqual(open(output_filename).read().strip(),
                             "ARGS -c test.conf")
        return result.addCallback(got_result)

    def test_set_effective_uid_and_gid_when_running_as_root(self):
        """
        After the package changer has run, we want the package-reporter to run
        to report the recent changes.  If we're running as root, we want to
        change to the "landscape" user and "landscape" group. We also want to
        deinitialize Smart to let the reporter run smart-update cleanly.
        """

        # We are running as root
        getuid_mock = self.mocker.replace("os.getuid")
        getuid_mock()
        self.mocker.result(0)

        # The order matters (first smart then gid and finally uid)
        self.mocker.order()

        # Deinitialize smart
        facade_mock = self.mocker.patch(self.facade)
        facade_mock.deinit()

        # We want to return a known gid
        grnam_mock = self.mocker.replace("grp.getgrnam")
        grnam_mock("landscape")

        class FakeGroup(object):
            gr_gid = 199

        self.mocker.result(FakeGroup())

        # First the changer should change the group
        setgid_mock = self.mocker.replace("os.setgid")
        setgid_mock(199)

        # And a known uid as well
        pwnam_mock = self.mocker.replace("pwd.getpwnam")
        pwnam_mock("landscape")

        class FakeUser(object):
            pw_uid = 199

        self.mocker.result(FakeUser())

        # And now the user as well
        setuid_mock = self.mocker.replace("os.setuid")
        setuid_mock(199)

        # Finally, we don't really want the package reporter to run.
        system_mock = self.mocker.replace("os.system")
        system_mock(ANY)

        self.mocker.replay()

        # Add a task that will do nothing besides producing an answer.
        # The reporter is only spawned if at least one task was handled.
        self.store.add_task("changer", {"type": "change-packages",
                                        "operation-id": 123})
        return self.changer.run()

    def test_run(self):
        changer_mock = self.mocker.patch(self.changer)

        self.mocker.order()

        results = [Deferred() for i in range(2)]

        changer_mock.use_hash_id_db()
        self.mocker.result(results[0])

        changer_mock.handle_tasks()
        self.mocker.result(results[1])

        self.mocker.replay()

        self.changer.run()

        # It must raise an error because deferreds weren't yet fired.
        self.assertRaises(AssertionError, self.mocker.verify)

        for deferred in reversed(results):
            deferred.callback(None)

    def test_dont_spawn_reporter_after_running_if_nothing_done(self):
        output_filename = self.makeFile("REPORTER NOT RUN")
        reporter_filename = self.makeFile("#!/bin/sh\necho REPORTER RUN > %s" %
                                          output_filename)
        os.chmod(reporter_filename, 0755)

        find_command_mock = self.mocker.replace(
            "landscape.package.reporter.find_reporter_command")
        find_command_mock()
        self.mocker.result(reporter_filename)
        self.mocker.count(0, None)
        self.mocker.replay()

        result = self.changer.run()

        def got_result(result):
            self.assertEqual(open(output_filename).read().strip(),
                             "REPORTER NOT RUN")
        return result.addCallback(got_result)

    def test_main(self):
        self.mocker.order()

        run_task_handler = self.mocker.replace("landscape.package.taskhandler"
                                               ".run_task_handler",
                                               passthrough=False)
        getpgrp = self.mocker.replace("os.getpgrp")
        self.expect(getpgrp()).result(os.getpid() + 1)
        setsid = self.mocker.replace("os.setsid")
        setsid()
        run_task_handler(PackageChanger, ["ARGS"])
        self.mocker.result("RESULT")

        self.mocker.replay()

        self.assertEqual(main(["ARGS"]), "RESULT")

    def test_main_run_from_shell(self):
        """
        We want the getpid and getpgrp to return the same process id
        this simulates the case where the process is already the process
        session leader, in this case the os.setsid would fail.
        """
        getpgrp = self.mocker.replace("os.getpgrp")
        getpgrp()
        self.mocker.result(os.getpid())

        setsid = self.mocker.replace("os.setsid")
        setsid()
        self.mocker.count(0, 0)

        run_task_handler = self.mocker.replace("landscape.package.taskhandler"
                                               ".run_task_handler",
                                               passthrough=False)
        run_task_handler(PackageChanger, ["ARGS"])
        self.mocker.replay()

        main(["ARGS"])

    def test_find_changer_command(self):
        dirname = self.makeDir()
        filename = self.makeFile("", dirname=dirname,
                                 basename="landscape-package-changer")

        saved_argv = sys.argv
        try:
            sys.argv = [os.path.join(dirname, "landscape-monitor")]

            command = find_changer_command()

            self.assertEqual(command, filename)
        finally:
            sys.argv = saved_argv

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

    def test_smart_error_with_unicode_data(self):
        self.store.set_hash_ids({HASH1: 1})
        self.store.add_task("changer",
                            {"type": "change-packages", "install": [1],
                             "operation-id": 123})

        def raise_error(self):
            raise SmartError(u"áéíóú")
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
        L{PackageChanger.update_exists} returns C{True} if the
        update-stamp file is there, C{False} otherwise.
        """
        self.assertTrue(self.changer.update_stamp_exists())
        os.remove(self.config.update_stamp_filename)
        self.assertFalse(self.changer.update_stamp_exists())

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
                               base64.decodestring(PKGDEB1))
        self.assertFileContent(os.path.join(binaries_path, "222.deb"),
                               base64.decodestring(PKGDEB2))
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
        self.makeFile(basename=existing_deb_path, content="foo")
        self.changer.init_channels([])
        self.assertFalse(os.path.exists(existing_deb_path))


class SmartPackageChangerTest(LandscapeTest, PackageChangerTestMixin):

    helpers = [SmartFacadeHelper, BrokerServiceHelper]

    def setUp(self):

        def set_up(ignored):

            self.store = PackageStore(self.makeFile())
            self.config = PackageChangerConfiguration()
            self.config.data_path = self.makeDir()
            os.mkdir(self.config.package_directory)
            os.mkdir(self.config.binaries_path)
            touch_file(self.config.update_stamp_filename)
            self.changer = PackageChanger(
                self.store, self.facade, self.remote, self.config)
            service = self.broker_service
            service.message_store.set_accepted_types(["change-packages-result",
                                                      "operation-result"])

        result = super(SmartPackageChangerTest, self).setUp()
        return result.addCallback(set_up)

    def set_pkg1_installed(self):
        previous = self.Facade.channels_reloaded

        def callback(self):
            previous(self)
            self.get_packages_by_name("name1")[0].installed = True
        self.Facade.channels_reloaded = callback
        return HASH1

    def set_pkg2_upgrades_pkg1(self):
        previous = self.Facade.channels_reloaded

        def callback(self):
            from smart.backends.deb.base import DebUpgrades
            previous(self)
            [pkg2] = self.get_packages_by_name("name2")
            pkg2.upgrades += (DebUpgrades("name1", "=", "version1-release1"),)
            self.reload_cache()  # Relink relations.
        self.Facade.channels_reloaded = callback
        self.set_pkg2_satisfied()
        self.set_pkg1_installed()
        return HASH1, HASH2

    def set_pkg2_satisfied(self):
        previous = self.Facade.channels_reloaded

        def callback(self):
            previous(self)
            [pkg2] = self.get_packages_by_name("name2")
            pkg2.requires = ()
            self.reload_cache()  # Relink relations.
        self.Facade.channels_reloaded = callback
        return HASH2

    def set_pkg1_and_pkg2_satisfied(self):
        previous = self.Facade.channels_reloaded

        def callback(self):
            previous(self)

            provide1 = Provides("prerequirename1", "prerequireversion1")
            provide2 = Provides("requirename1", "requireversion1")
            [pkg2] = self.get_packages_by_name("name2")
            pkg2.provides += (provide1, provide2)

            provide1 = Provides("prerequirename2", "prerequireversion2")
            provide2 = Provides("requirename2", "requireversion2")
            [pkg1] = self.get_packages_by_name("name1")
            pkg1.provides += (provide1, provide2)

            # Ask Smart to reprocess relationships.
            self.reload_cache()
        self.Facade.channels_reloaded = callback
        return HASH1, HASH2

    def remove_pkg2(self):
        os.remove(os.path.join(self.repository_dir, PKGNAME2))

    def get_transaction_error_message(self):
        return "requirename1 = requireversion1"

    def get_binaries_channels(self, binaries_path):
        return {binaries_path: {"type": "deb-dir",
                                "path": binaries_path}}

    def get_package_name(self, package):
        return package.name

    def test_change_package_locks(self):
        """
        The L{PackageChanger.handle_tasks} method appropriately creates and
        deletes package locks as requested by the C{change-package-locks}
        message.
        """
        self.facade.set_package_lock("bar")
        self.store.add_task("changer", {"type": "change-package-locks",
                                        "create": [("foo", ">=", "1.0")],
                                        "delete": [("bar", None, None)],
                                        "operation-id": 123})

        def assert_result(result):
            self.facade.deinit()
            self.assertEqual(self.facade.get_package_locks(),
                             [("foo", ">=", "1.0")])
            self.assertIn("Queuing message with change package locks results "
                          "to exchange urgently.", self.logfile.getvalue())
            self.assertMessages(self.get_pending_messages(),
                                [{"type": "operation-result",
                                  "operation-id": 123,
                                  "status": SUCCEEDED,
                                  "result-text": "Package locks successfully"
                                                 " changed.",
                                  "result-code": 0}])

        result = self.changer.handle_tasks()
        return result.addCallback(assert_result)

    def test_change_package_locks_create_with_already_existing(self):
        """
        The L{PackageChanger.handle_tasks} method gracefully handles requests
        for creating package locks that already exist.
        """
        self.facade.set_package_lock("foo")
        self.store.add_task("changer", {"type": "change-package-locks",
                                        "create": [("foo", None, None)],
                                        "operation-id": 123})

        def assert_result(result):
            self.facade.deinit()
            self.assertEqual(self.facade.get_package_locks(),
                             [("foo", "", "")])
            self.assertMessages(self.get_pending_messages(),
                                [{"type": "operation-result",
                                  "operation-id": 123,
                                  "status": SUCCEEDED,
                                  "result-text": "Package locks successfully"
                                                 " changed.",
                                  "result-code": 0}])

        result = self.changer.handle_tasks()
        return result.addCallback(assert_result)

    def test_change_package_locks_delete_without_already_existing(self):
        """
        The L{PackageChanger.handle_tasks} method gracefully handles requests
        for deleting package locks that don't exist.
        """
        self.store.add_task("changer", {"type": "change-package-locks",
                                        "delete": [("foo", ">=", "1.0")],
                                        "operation-id": 123})

        def assert_result(result):
            self.facade.deinit()
            self.assertEqual(self.facade.get_package_locks(), [])
            self.assertMessages(self.get_pending_messages(),
                                [{"type": "operation-result",
                                  "operation-id": 123,
                                  "status": SUCCEEDED,
                                  "result-text": "Package locks successfully"
                                                 " changed.",
                                  "result-code": 0}])

        result = self.changer.handle_tasks()
        return result.addCallback(assert_result)

    def test_dpkg_error(self):
        """
        Verify that errors emitted by dpkg are correctly reported to
        the server as problems.

        This test is to make sure that Smart reports the problem
        correctly. It doesn't make sense for AptFacade, since there we
        don't call dpkg.
        """
        self.log_helper.ignore_errors(".*dpkg")

        installed_hash = self.set_pkg1_installed()
        self.store.set_hash_ids({installed_hash: 1})
        self.store.add_task("changer",
                            {"type": "change-packages", "remove": [1],
                             "operation-id": 123})

        result = self.changer.handle_tasks()

        def got_result(result):
            messages = self.get_pending_messages()
            self.assertEqual(len(messages), 1, "Too many messages")
            message = messages[0]
            self.assertEqual(message["operation-id"], 123)
            self.assertEqual(message["result-code"], 100)
            self.assertEqual(message["type"], "change-packages-result")
            text = message["result-text"]
            # We can't test the actual content of the message because the dpkg
            # error can be localized
            self.assertIn("\n[remove] name1_version1-release1\ndpkg: ", text)
            self.assertIn("ERROR", text)
            self.assertIn("(2)", text)
        return result.addCallback(got_result)

    def test_change_package_holds(self):
        """
        If C{SmartFacade} is used, the L{PackageChanger.handle_tasks}
        method fails the activity, since it can't add or remove dpkg holds.
        """
        self.facade.reload_channels()
        self.store.add_task("changer", {"type": "change-package-holds",
                                        "create": [1],
                                        "delete": [2],
                                        "operation-id": 123})

        def assert_result(result):
            self.assertIn("Queuing message with change package holds results "
                          "to exchange urgently.", self.logfile.getvalue())
            self.assertMessages(
                self.get_pending_messages(),
                [{"type": "operation-result",
                  "operation-id": 123,
                  "status": FAILED,
                  "result-text": "This client doesn't support package holds.",
                  "result-code": 1}])

        result = self.changer.handle_tasks()
        return result.addCallback(assert_result)

    def test_global_upgrade(self):
        """
        Besides asking for individual changes, the server may also request
        the client to perform a global upgrade.  This would be the equivalent
        of a "smart upgrade" command being executed in the command line.

        This test should be run for both C{AptFacade} and
        C{SmartFacade}, but due to the smart test setting up that two
        packages with different names upgrade each other, the message
        doesn't correctly report that the old version should be
        uninstalled. The test is still useful, since it shows that the
        message contains the changes that smart says are needed.

        Making the test totally correct is a lot of work, that is not
        worth doing, since we're removing smart soon.
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
                                  "result-code": 101,
                                  "type": "change-packages-result"}])

        return result.addCallback(got_result)


class AptPackageChangerTest(LandscapeTest, PackageChangerTestMixin):

    if not has_new_enough_apt:
        skip = "Can't use AptFacade on hardy"

    helpers = [AptFacadeHelper, SimpleRepositoryHelper, BrokerServiceHelper]

    def setUp(self):

        def set_up(ignored):

            self.store = PackageStore(self.makeFile())
            self.config = PackageChangerConfiguration()
            self.config.data_path = self.makeDir()
            os.mkdir(self.config.package_directory)
            os.mkdir(self.config.binaries_path)
            touch_file(self.config.update_stamp_filename)
            self.changer = PackageChanger(
                self.store, self.facade, self.remote, self.config)
            service = self.broker_service
            service.message_store.set_accepted_types(["change-packages-result",
                                                      "operation-result"])

        result = super(AptPackageChangerTest, self).setUp()
        return result.addCallback(set_up)

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
        packages_contents = read_file(packages_file)
        packages_contents = "\n\n".join(
            [stanza for stanza in packages_contents.split("\n\n")
             if "Package: name2" not in stanza])
        create_file(packages_file, packages_contents)

    def get_transaction_error_message(self):
        """Return part of the apt transaction error message."""
        return "Unable to correct problems"

    def get_binaries_channels(self, binaries_path):
        """Return the channels that will be used for the binaries."""
        return [{"baseurl": "file://%s" % binaries_path,
                 "components": "",
                 "distribution": "./",
                 "type": "deb"}]

    def get_package_name(self, version):
        """Return the name of the package."""
        return version.package.name

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
        deletes package holds as requested by the C{change-package-holds}
        message.
        """
        self._add_system_package("foo")
        self._add_system_package("bar")
        self.facade.reload_channels()
        self._hash_packages_by_name(self.facade, self.store, "foo")
        self._hash_packages_by_name(self.facade, self.store, "bar")
        [foo] = self.facade.get_packages_by_name("foo")
        [bar] = self.facade.get_packages_by_name("bar")
        self.facade.set_package_hold(bar)
        self.facade.reload_channels()
        self.store.add_task("changer", {"type": "change-package-holds",
                                        "create": [foo.package.id],
                                        "delete": [bar.package.id],
                                        "operation-id": 123})

        def assert_result(result):
            self.facade.reload_channels()
            self.assertEqual(["foo"], self.facade.get_package_holds())
            self.assertIn("Queuing message with change package holds results "
                          "to exchange urgently.", self.logfile.getvalue())
            self.assertMessages(
                self.get_pending_messages(),
                [{"type": "operation-result",
                  "operation-id": 123,
                  "status": SUCCEEDED,
                  "result-text": "Package holds successfully changed.",
                  "result-code": 0}])

        result = self.changer.handle_tasks()
        return result.addCallback(assert_result)

    def test_create_package_holds_with_identical_version(self):
        """
        The L{PackageChanger.handle_tasks} method appropriately creates
        holds as requested by the C{change-package-holds} message even
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
        self.store.add_task("changer", {"type": "change-package-holds",
                                        "create": [foo.package.id,
                                                   bar.package.id],
                                        "operation-id": 123})

        def assert_result(result):
            self.assertEqual(["foo", "bar"], self.facade.get_package_holds())

        result = self.changer.handle_tasks()
        return result.addCallback(assert_result)

    def test_delete_package_holds_with_identical_version(self):
        """
        The L{PackageChanger.handle_tasks} method appropriately deletes
        holds as requested by the C{change-package-holds} message even
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
        self.store.add_task("changer", {"type": "change-package-holds",
                                        "delete": [foo.package.id,
                                                   bar.package.id],
                                        "operation-id": 123})

        def assert_result(result):
            self.assertEqual([], self.facade.get_package_holds())

        result = self.changer.handle_tasks()
        return result.addCallback(assert_result)

    def test_change_package_holds_create_already_held(self):
        """
        If the C{change-package-holds} message requests to add holds for
        packages that are already held, the activity succeeds, since the
        end result is that the requested package holds are there.
        """
        self._add_system_package("foo")
        self.facade.reload_channels()
        self._hash_packages_by_name(self.facade, self.store, "foo")
        [foo] = self.facade.get_packages_by_name("foo")
        self.facade.set_package_hold(foo)
        self.facade.reload_channels()
        self.store.add_task("changer", {"type": "change-package-holds",
                                        "create": [foo.package.id],
                                        "operation-id": 123})

        def assert_result(result):
            self.facade.reload_channels()
            self.assertEqual(["foo"], self.facade.get_package_holds())
            self.assertIn("Queuing message with change package holds results "
                          "to exchange urgently.", self.logfile.getvalue())
            self.assertMessages(
                self.get_pending_messages(),
                [{"type": "operation-result",
                  "operation-id": 123,
                  "status": SUCCEEDED,
                  "result-text": "Package holds successfully changed.",
                  "result-code": 0}])

        result = self.changer.handle_tasks()
        return result.addCallback(assert_result)

    def test_change_package_holds_create_other_version_installed(self):
        """
        If the C{change-package-holds} message requests to add holds for
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
        self.store.add_task("changer", {"type": "change-package-holds",
                                        "create": [2, 3],
                                        "operation-id": 123})

        def assert_result(result):
            self.facade.reload_channels()
            self.assertEqual([], self.facade.get_package_holds())
            self.assertIn("Queuing message with change package holds results "
                          "to exchange urgently.", self.logfile.getvalue())
            self.assertMessages(
                self.get_pending_messages(),
                [{"type": "operation-result",
                  "operation-id": 123,
                  "status": FAILED,
                  "result-text": "Package holds not changed, since the" +
                                 " following packages are not installed: 2",
                  "result-code": 1}])

        result = self.changer.handle_tasks()
        return result.addCallback(assert_result)

    def test_change_package_holds_create_not_installed(self):
        """
        If the C{change-package-holds} message requests to add holds for
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
        self.store.add_task("changer", {"type": "change-package-holds",
                                        "create": [foo.package.id,
                                                   bar.package.id,
                                                   baz.package.id],
                                        "operation-id": 123})

        def assert_result(result):
            self.facade.reload_channels()
            self.assertEqual([], self.facade.get_package_holds())
            self.assertIn("Queuing message with change package holds results "
                          "to exchange urgently.", self.logfile.getvalue())
            self.assertMessages(
                self.get_pending_messages(),
                [{"type": "operation-result",
                  "operation-id": 123,
                  "status": FAILED,
                  "result-text": "Package holds not changed, since the "
                  "following packages are not installed: "
                  "%s, %s" % tuple(sorted([bar.package.id,
                                               baz.package.id])),
                  "result-code": 1}])

        result = self.changer.handle_tasks()
        return result.addCallback(assert_result)

    def test_change_package_holds_create_unknown_hash(self):
        """
        If the C{change-package-holds} message requests to add holds for
        packages that the client doesn't know about, it's being treated
        as the packages not being installed.
        """
        self.facade.reload_channels()
        self.store.add_task("changer", {"type": "change-package-holds",
                                        "create": [1],
                                        "operation-id": 123})

        def assert_result(result):
            self.facade.reload_channels()
            self.assertEqual([], self.facade.get_package_holds())
            self.assertIn("Queuing message with change package holds results "
                          "to exchange urgently.", self.logfile.getvalue())
            self.assertMessages(
                self.get_pending_messages(),
                [{"type": "operation-result",
                  "operation-id": 123,
                  "status": FAILED,
                  "result-text": "Package holds not changed, since the" +
                                 " following packages are not installed: 1",
                  "result-code": 1}])

        result = self.changer.handle_tasks()
        return result.addCallback(assert_result)

    def test_change_package_holds_delete_not_held(self):
        """
        If the C{change-package-holds} message requests to remove holds
        for packages that aren't held, the activity succeeds if the
        right version is installed, since the end result is that the
        hold is removed.
        """
        self._add_package_to_deb_dir(self.repository_dir, "foo")
        self.facade.reload_channels()
        self._hash_packages_by_name(self.facade, self.store, "foo")
        [foo] = self.facade.get_packages_by_name("foo")
        self.store.add_task("changer", {"type": "change-package-holds",
                                        "delete": [foo.package.id],
                                        "operation-id": 123})

        def assert_result(result):
            self.facade.reload_channels()
            self.assertEqual([], self.facade.get_package_holds())
            self.assertIn("Queuing message with change package holds results "
                          "to exchange urgently.", self.logfile.getvalue())
            self.assertMessages(
                self.get_pending_messages(),
                [{"type": "operation-result",
                  "operation-id": 123,
                  "status": SUCCEEDED,
                  "result-text": "Package holds successfully changed.",
                  "result-code": 0}])

        result = self.changer.handle_tasks()
        return result.addCallback(assert_result)

    def test_change_package_holds_delete_different_version_held(self):
        """
        If the C{change-package-holds} message requests to remove holds
        for packages that aren't held, the activity succeeds if the
        right version is installed, since the end result is that the
        hold is removed.
        """
        self._add_system_package("foo", version="1.0")
        self._add_package_to_deb_dir(
            self.repository_dir, "foo", version="2.0")
        self.facade.reload_channels()
        [foo1, foo2] = sorted(self.facade.get_packages_by_name("foo"))
        self.facade.set_package_hold(foo1)
        self.store.set_hash_ids({self.facade.get_package_hash(foo1): 1,
                                 self.facade.get_package_hash(foo2): 2})
        self.facade.reload_channels()
        self.store.add_task("changer", {"type": "change-package-holds",
                                        "delete": [2],
                                        "operation-id": 123})

        def assert_result(result):
            self.facade.reload_channels()
            self.assertEqual(["foo"], self.facade.get_package_holds())
            self.assertIn("Queuing message with change package holds results "
                          "to exchange urgently.", self.logfile.getvalue())
            self.assertMessages(
                self.get_pending_messages(),
                [{"type": "operation-result",
                  "operation-id": 123,
                  "status": SUCCEEDED,
                  "result-text": "Package holds successfully changed.",
                  "result-code": 0}])

        result = self.changer.handle_tasks()
        return result.addCallback(assert_result)

    def test_change_package_holds_delete_unknown_hash(self):
        """
        If the C{change-package-holds} message requests to remove holds
        for packages that aren't known by the client, the activity
        succeeds, since the end result is that the package isn't
        held at that version.
        """
        self.store.add_task("changer", {"type": "change-package-holds",
                                        "delete": [1],
                                        "operation-id": 123})

        def assert_result(result):
            self.facade.reload_channels()
            self.assertEqual([], self.facade.get_package_holds())
            self.assertIn("Queuing message with change package holds results "
                          "to exchange urgently.", self.logfile.getvalue())
            self.assertMessages(
                self.get_pending_messages(),
                [{"type": "operation-result",
                  "operation-id": 123,
                  "status": SUCCEEDED,
                  "result-text": "Package holds successfully changed.",
                  "result-code": 0}])

        result = self.changer.handle_tasks()
        return result.addCallback(assert_result)

    def test_change_package_holds_delete_not_installed(self):
        """
        If the C{change-package-holds} message requests to remove holds
        for packages that aren't installed, the activity succeeds, since
        the end result is still that the package isn't held at the
        requested version.
        """
        self._add_system_package("foo")
        self.facade.reload_channels()
        self._hash_packages_by_name(self.facade, self.store, "foo")
        [foo] = self.facade.get_packages_by_name("foo")
        self.store.add_task("changer", {"type": "change-package-holds",
                                        "delete": [foo.package.id],
                                        "operation-id": 123})

        def assert_result(result):
            self.facade.reload_channels()
            self.assertEqual([], self.facade.get_package_holds())
            self.assertIn("Queuing message with change package holds results "
                          "to exchange urgently.", self.logfile.getvalue())
            self.assertMessages(
                self.get_pending_messages(),
                [{"type": "operation-result",
                  "operation-id": 123,
                  "status": SUCCEEDED,
                  "result-text": "Package holds successfully changed.",
                  "result-code": 0}])

        result = self.changer.handle_tasks()
        return result.addCallback(assert_result)

    def test_change_package_locks(self):
        """
        If C{AptFacade} is used, the L{PackageChanger.handle_tasks}
        method fails the activity, since it can't add or remove locks because
        apt doesn't support this.
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
