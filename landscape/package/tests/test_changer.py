# -*- encoding: utf-8 -*-
import time
import sys
import os

from twisted.internet.defer import Deferred

from smart.cache import Provides

from landscape.package.changer import (
    PackageChanger, main, find_changer_command, UNKNOWN_PACKAGE_DATA_TIMEOUT)
from landscape.package.store import PackageStore
from landscape.package.facade import (
    DependencyError, TransactionError, SmartError)
from landscape.deployment import Configuration

from landscape.tests.mocker import ANY
from landscape.tests.helpers import (
    LandscapeIsolatedTest, RemoteBrokerHelper)
from landscape.package.tests.helpers import (
    SmartFacadeHelper, HASH1, HASH2, HASH3)


class PackageChangerTest(LandscapeIsolatedTest):

    helpers = [SmartFacadeHelper, RemoteBrokerHelper]

    def setUp(self):
        super(PackageChangerTest, self).setUp()

        self.store = PackageStore(self.makeFile())
        self.config = Configuration()
        self.changer = PackageChanger(self.store, self.facade, self.remote, self.config)

        service = self.broker_service
        service.message_store.set_accepted_types(["change-packages-result"])

    def get_pending_messages(self):
        return self.broker_service.message_store.get_pending_messages()

    def set_pkg1_installed(self):
        previous = self.Facade.channels_reloaded
        def callback(self):
            previous(self)
            self.get_packages_by_name("name1")[0].installed = True
        self.Facade.channels_reloaded = callback

    def set_pkg2_upgrades_pkg1(self):
        previous = self.Facade.channels_reloaded
        def callback(self):
            from smart.backends.deb.base import DebUpgrades
            previous(self)
            pkg2 = self.get_packages_by_name("name2")[0]
            pkg2.upgrades += (DebUpgrades("name1", "=", "version1-release1"),)
            self.reload_cache() # Relink relations.
        self.Facade.channels_reloaded = callback

    def set_pkg2_satisfied(self):
        previous = self.Facade.channels_reloaded
        def callback(self):
            previous(self)
            pkg2 = self.get_packages_by_name("name2")[0]
            pkg2.requires = ()
            self.reload_cache() # Relink relations.
        self.Facade.channels_reloaded = callback

    def set_pkg1_and_pkg2_satisfied(self):
        previous = self.Facade.channels_reloaded
        def callback(self):
            previous(self)

            provide1 = Provides("prerequirename1", "prerequireversion1")
            provide2 = Provides("requirename1", "requireversion1")
            pkg2 = self.get_packages_by_name("name2")[0]
            pkg2.provides += (provide1, provide2)

            provide1 = Provides("prerequirename2", "prerequireversion2")
            provide2 = Provides("requirename2", "requireversion2")
            pkg1 = self.get_packages_by_name("name1")[0]
            pkg1.provides += (provide1, provide2)

            # Ask Smart to reprocess relationships.
            self.reload_cache()
        self.Facade.channels_reloaded = callback

    def test_unknown_package_id_for_dependency(self):
        self.set_pkg1_and_pkg2_satisfied()

        # Let's request an operation that would require an answer with a
        # must-install field with a package for which the id isn't yet
        # known by the client.
        self.store.add_task("changer",
                            {"type": "change-packages", "install": [1],
                             "operation-id": 123})

        # In our first try, we should get nothing, because the id of the
        # dependency (HASH2) isn't known.
        self.store.set_hash_ids({HASH1: 1})
        result = self.changer.handle_tasks()
        self.assertEquals(result.called, True)
        self.assertMessages(self.get_pending_messages(), [])

        self.assertIn("Package data not yet synchronized with server (%r)"
                      % HASH2, self.logfile.getvalue())

        # So now we'll set it, and advance the reactor to the scheduled
        # change detection.  We'll get a lot of messages, including the
        # result of our previous message, which got *postponed*.
        self.store.set_hash_ids({HASH2: 2})
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
            self.assertEquals(self.store.get_next_task("changer"), None)
        return result.addCallback(got_result)

    def test_dpkg_error(self):
        """
        Verify that errors emitted by dpkg are correctly reported to
        the server as problems.
        """
        self.log_helper.ignore_errors(".*dpkg")

        self.store.set_hash_ids({HASH1: 1})
        self.store.add_task("changer",
                            {"type": "change-packages", "remove": [1],
                             "operation-id": 123})

        self.set_pkg1_installed()

        result = self.changer.handle_tasks()

        def got_result(result):
            messages = self.get_pending_messages()
            self.assertEquals(len(messages), 1, "Too many messages")
            message = messages[0]
            self.assertEquals(message["operation-id"], 123)
            self.assertEquals(message["result-code"], 100)
            self.assertEquals(message["type"], "change-packages-result")
            text = message["result-text"]
            # We can't test the actual content of the message because the dpkg
            # error can be localized
            self.assertIn("\n[remove] name1_version1-release1\ndpkg: ", text)
            self.assertIn("ERROR", text)
            self.assertIn("(2)", text)
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
        self.store.set_hash_ids({HASH1: 1, HASH2: 2, HASH3: 3})
        self.store.add_task("changer",
                            {"type": "change-packages", "install": [2],
                             "operation-id": 123})

        self.set_pkg1_installed()

        def raise_dependency_error(self):
            raise DependencyError(self.get_packages())
        self.Facade.perform_changes = raise_dependency_error

        result = self.changer.handle_tasks()

        def got_result(result):
            self.assertMessages(self.get_pending_messages(),
                                [{"must-install": [2, 3],
                                  "must-remove": [1],
                                  "operation-id": 123,
                                  "result-code": 101,
                                  "type": "change-packages-result"}])
        return result.addCallback(got_result)

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

        result = self.changer.handle_tasks()

        def got_result(result):
            result_text = ("requirename1 = requireversion1")
            messages = self.get_pending_messages()
            self.assertEquals(len(messages), 1)
            message = messages[0]
            self.assertEquals(message["operation-id"], 123)
            self.assertEquals(message["result-code"], 100)
            self.assertIn(result_text, message["result-text"])
            self.assertEquals(message["type"], "change-packages-result")
        return result.addCallback(got_result)

    def test_tasks_are_isolated(self):
        """
        Changes attempted on one task should be reset before the next
        task is run.  In this test, we try to run two different
        operations, first installing package 2, then upgrading
        anything available.  The first installation will fail for lack
        of superuser privileges, and the second one will succeed since
        there's nothing to upgrade.  If tasks are mixed up, the second
        operation will fail too, because the installation of package 2
        is still queued.
        """
        self.log_helper.ignore_errors(".*dpkg")

        self.store.set_hash_ids({HASH1: 1, HASH2: 2})

        self.store.add_task("changer",
                            {"type": "change-packages", "install": [2],
                             "operation-id": 123})
        self.store.add_task("changer",
                            {"type": "change-packages", "upgrade-all": True,
                             "operation-id": 124})

        self.set_pkg2_satisfied()
        self.set_pkg1_installed()

        result = self.changer.handle_tasks()

        def got_result(result):
            self.assertMessage(self.get_pending_messages()[1],
                               {"operation-id": 124,
                                "result-code": 1,
                                "type": "change-packages-result"})

        return result.addCallback(got_result)

    def test_successful_operation(self):
        """Simulate a *very* successful operation.
        
        We'll do that by hacking perform_changes(), and returning our
        *very* successful operation result.
        """
        self.store.set_hash_ids({HASH1: 1, HASH2: 2, HASH3: 3})
        self.store.add_task("changer",
                            {"type": "change-packages", "install": [2],
                             "operation-id": 123})

        self.set_pkg1_installed()

        def return_good_result(self):
            return "Yeah, I did whatever you've asked for!"
        self.Facade.perform_changes = return_good_result

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
        self.store.set_hash_ids({HASH1: 1, HASH2: 2})

        self.store.add_task("changer",
                            {"type": "change-packages", "upgrade-all": True,
                             "operation-id": 123})

        self.set_pkg2_upgrades_pkg1()
        self.set_pkg2_satisfied()
        self.set_pkg1_installed()

        result = self.changer.handle_tasks()

        def got_result(result):
            self.assertMessages(self.get_pending_messages(),
                                [{"operation-id": 123,
                                  "must-install": [2],
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
            self.assertEquals(open(output_filename).read().strip(),
                              "REPORTER RUN")
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
            self.assertEquals(open(output_filename).read().strip(),
                              "REPORTER NOT RUN")
        return result.addCallback(got_result)

    def test_main(self):
        self.mocker.order()
        
        run_task_handler = self.mocker.replace("landscape.package.taskhandler"
                                               ".run_task_handler",
                                               passthrough=False)
        setsid = self.mocker.replace("os.setsid")
        
        setsid()
        run_task_handler(PackageChanger, ["ARGS"])
        self.mocker.result("RESULT")

        self.mocker.replay()

        self.assertEquals(main(["ARGS"]), "RESULT")

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

            self.assertEquals(command, filename)
        finally:
            sys.argv = saved_argv

    def test_transaction_error_with_unicode_data(self):
        self.store.set_hash_ids({HASH1: 1})
        self.store.add_task("changer",
                            {"type": "change-packages", "install": [1],
                             "operation-id": 123})

        def raise_error(self):
            raise TransactionError(u"áéíóú")
        self.Facade.perform_changes = raise_error

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
        self.Facade.perform_changes = raise_error

        result = self.changer.handle_tasks()

        def got_result(result):
            self.assertMessages(self.get_pending_messages(),
                                [{"operation-id": 123,
                                  "result-code": 100,
                                  "result-text": u"áéíóú",
                                  "type": "change-packages-result"}])
        return result.addCallback(got_result)
