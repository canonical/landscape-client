import mock
import os
import os.path

from twisted.internet.defer import Deferred

from landscape.client.package.changer import PackageChanger
from landscape.client.package.releaseupgrader import ReleaseUpgrader
from landscape.lib.apt.package.store import PackageStore

from landscape.lib.testing import EnvironSaverHelper
from landscape.client.manager.packagemanager import PackageManager
from landscape.client.tests.helpers import LandscapeTest, ManagerHelper


class PackageManagerTest(LandscapeTest):
    """Tests for the package manager plugin."""

    helpers = [EnvironSaverHelper, ManagerHelper]

    def setUp(self):
        """Initialize test helpers and create a sample package store."""
        super(PackageManagerTest, self).setUp()
        self.config = self.broker_service.config
        self.package_store = PackageStore(os.path.join(self.data_path,
                                                       "package/database"))
        self.package_manager = PackageManager()

    def test_create_default_store_upon_message_handling(self):
        """
        If the package sqlite database file doesn't exist yet, it is created
        upon message handling.
        """
        filename = os.path.join(self.config.data_path, "package/database")
        os.unlink(filename)
        self.assertFalse(os.path.isfile(filename))

        self.manager.add(self.package_manager)
        with mock.patch.object(self.package_manager, "spawn_handler"):
            message = {"type": "release-upgrade"}
            self.package_manager.handle_release_upgrade(message)
            self.assertTrue(os.path.isfile(filename))

    def test_dont_spawn_changer_if_message_not_accepted(self):
        """
        The L{PackageManager} spawns a L{PackageChanger} run only if the
        appropriate message type is accepted.
        """
        self.manager.add(self.package_manager)
        with mock.patch.object(self.package_manager, "spawn_handler"):
            self.package_manager.run()
            self.assertNotIn(PackageChanger,
                             self.package_manager.spawn_handler.call_args_list)
            self.assertEqual(0, self.package_manager.spawn_handler.call_count)

    def test_dont_spawn_release_upgrader_if_message_not_accepted(self):
        """
        The L{PackageManager} spawns a L{ReleaseUpgrader} run only if the
        appropriate message type is accepted.
        """
        self.manager.add(self.package_manager)
        with mock.patch.object(self.package_manager, "spawn_handler"):
            self.package_manager.run()
            self.assertNotIn(ReleaseUpgrader,
                             self.package_manager.spawn_handler.call_args_list)
            self.assertEqual(0, self.package_manager.spawn_handler.call_count)

    def test_spawn_handler_on_registration_when_already_accepted(self):
        real_run = self.package_manager.run

        # Slightly tricky as we have to wait for the result of run(),
        # but we don't have its deferred yet.  To handle it, we create
        # our own deferred, and register a callback for when run()
        # returns, chaining both deferreds at that point.
        deferred = Deferred()

        def run_has_run():
            run_result_deferred = real_run()
            return run_result_deferred.chainDeferred(deferred)

        with mock.patch.object(self.package_manager, "spawn_handler"):
            with mock.patch.object(self.package_manager, "run",
                                   side_effect=run_has_run):
                service = self.broker_service
                service.message_store.set_accepted_types(
                    ["change-packages-result"])
                self.manager.add(self.package_manager)
                self.successResultOf(deferred)
                self.package_manager.spawn_handler.assert_called_once_with(
                    PackageChanger)
                self.package_manager.run.assert_called_once_with()

    def test_spawn_changer_on_run_if_message_accepted(self):
        """
        The L{PackageManager} spawns a L{PackageChanger} run if messages
        of type C{"change-packages-result"} are accepted.
        """
        service = self.broker_service
        service.message_store.set_accepted_types(["change-packages-result"])

        with mock.patch.object(self.package_manager, "spawn_handler"):
            self.manager.add(self.package_manager)
            self.package_manager.run()
            self.package_manager.spawn_handler.assert_called_with(
                PackageChanger)
            # Method is called once for registration, then again explicitly.
            self.assertEquals(2, self.package_manager.spawn_handler.call_count)

    def test_run_on_package_data_changed(self):
        """
        The L{PackageManager} spawns a L{PackageChanger} run if an event
        of type C{"package-data-changed"} is fired.
        """

        service = self.broker_service
        service.message_store.set_accepted_types(["change-packages-result"])

        with mock.patch.object(self.package_manager, "spawn_handler"):
            self.manager.add(self.package_manager)
            self.manager.reactor.fire("package-data-changed")[0]
            self.package_manager.spawn_handler.assert_called_with(
                PackageChanger)
            # Method is called once for registration, then again explicitly.
            self.assertEquals(2, self.package_manager.spawn_handler.call_count)

    def test_spawn_release_upgrader_on_run_if_message_accepted(self):
        """
        The L{PackageManager} spawns a L{ReleaseUpgrader} run if messages
        of type C{"operation-result"} are accepted.
        """
        service = self.broker_service
        service.message_store.set_accepted_types(["operation-result"])

        with mock.patch.object(self.package_manager, "spawn_handler"):
            self.manager.add(self.package_manager)
            self.package_manager.run()
            self.package_manager.spawn_handler.assert_called_with(
                ReleaseUpgrader)
            # Method is called once for registration, then again explicitly.
            self.assertEquals(2, self.package_manager.spawn_handler.call_count)

    def test_change_packages_handling(self):
        self.manager.add(self.package_manager)

        with mock.patch.object(self.package_manager, "spawn_handler"):
            message = {"type": "change-packages"}
            self.manager.dispatch_message(message)
            task = self.package_store.get_next_task("changer")
            self.assertTrue(task)
            self.assertEqual(task.data, message)
            self.package_manager.spawn_handler.assert_called_once_with(
                PackageChanger)

    def test_change_packages_handling_with_reboot(self):
        self.manager.add(self.package_manager)

        with mock.patch.object(self.package_manager, "spawn_handler"):
            message = {"type": "change-packages", "reboot-if-necessary": True}
            self.manager.dispatch_message(message)
            task = self.package_store.get_next_task("changer")
            self.assertTrue(task)
            self.assertEqual(task.data, message)
            self.package_manager.spawn_handler.assert_called_once_with(
                PackageChanger)

    def test_release_upgrade_handling(self):
        """
        The L{PackageManager.handle_release_upgrade} method is registered has
        handler for messages of type C{"release-upgrade"}, and queues a task
        in the appropriate queue.
        """
        self.manager.add(self.package_manager)

        with mock.patch.object(self.package_manager, "spawn_handler"):
            message = {"type": "release-upgrade"}
            self.manager.dispatch_message(message)
            task = self.package_store.get_next_task("release-upgrader")
            self.assertTrue(task)
            self.assertEqual(task.data, message)
            self.package_manager.spawn_handler.assert_called_once_with(
                ReleaseUpgrader)

    def test_spawn_changer(self):
        """
        The L{PackageManager.spawn_handler} method executes the correct command
        when passed the L{PackageChanger} class as argument.
        """
        command = self.write_script(
            self.config,
            "landscape-package-changer",
            "#!/bin/sh\necho 'I am the changer!' >&2\n")
        self.manager.config = self.config

        self.package_store.add_task("changer", "Do something!")

        self.manager.add(self.package_manager)
        result = self.package_manager.spawn_handler(PackageChanger)

        def got_result(result):
            log = self.logfile.getvalue()
            self.assertIn("I am the changer!", log)
            self.assertNotIn(command, log)

        return result.addCallback(got_result)

    def test_spawn_release_upgrader(self):
        """
        The L{PackageManager.spawn_handler} method executes the correct command
        when passed the L{ReleaseUpgrader} class as argument.
        """
        command = self.write_script(
            self.config,
            "landscape-release-upgrader",
            "#!/bin/sh\necho 'I am the upgrader!' >&2\n")
        self.manager.config = self.config

        self.package_store.add_task("release-upgrader", "Do something!")
        self.manager.add(self.package_manager)
        result = self.package_manager.spawn_handler(ReleaseUpgrader)

        def got_result(result):
            log = self.logfile.getvalue()
            self.assertIn("I am the upgrader!", log)
            self.assertNotIn(command, log)

        return result.addCallback(got_result)

    def test_spawn_handler_without_output(self):
        self.write_script(
            self.config,
            "landscape-package-changer",
            "#!/bin/sh\n/bin/true")
        self.manager.config = self.config

        self.package_store.add_task("changer", "Do something!")

        self.manager.add(self.package_manager)
        result = self.package_manager.spawn_handler(PackageChanger)

        def got_result(result):
            log = self.logfile.getvalue()
            self.assertNotIn("changer output", log)

        return result.addCallback(got_result)

    def test_spawn_handler_copies_environment(self):
        command = self.write_script(
            self.config,
            "landscape-package-changer",
            "#!/bin/sh\necho VAR: $VAR\n")
        self.manager.config = self.config

        self.manager.add(self.package_manager)
        self.package_store.add_task("changer", "Do something!")

        os.environ["VAR"] = "HI!"
        result = self.package_manager.spawn_handler(PackageChanger)

        def got_result(result):
            log = self.logfile.getvalue()
            self.assertIn("VAR: HI!", log)
            self.assertNotIn(command, log)

        return result.addCallback(got_result)

    def test_spawn_handler_passes_quiet_option(self):
        command = self.write_script(
            self.config,
            "landscape-package-changer",
            "#!/bin/sh\necho OPTIONS: $@\n")
        self.manager.config = self.config

        self.manager.add(self.package_manager)
        self.package_store.add_task("changer", "Do something!")
        result = self.package_manager.spawn_handler(PackageChanger)

        def got_result(result):
            log = self.logfile.getvalue()
            self.assertIn("OPTIONS: --quiet", log)
            self.assertNotIn(command, log)

        return result.addCallback(got_result)

    def test_spawn_handler_wont_run_without_tasks(self):
        command = self.makeFile("#!/bin/sh\necho RUN!\n")
        os.chmod(command, 0o755)

        self.manager.add(self.package_manager)
        result = self.package_manager.spawn_handler(PackageChanger)

        def got_result(result):
            log = self.logfile.getvalue()
            self.assertNotIn("RUN!", log)

        return result.addCallback(got_result)

    def test_spawn_handler_doesnt_chdir(self):
        self.write_script(
            self.config,
            "landscape-package-changer",
            "#!/bin/sh\necho RUN\n")
        self.manager.config = self.config

        cwd = os.getcwd()
        self.addCleanup(os.chdir, cwd)
        dir = self.makeDir()
        os.chdir(dir)
        os.chmod(dir, 0)

        self.manager.add(self.package_manager)
        self.package_store.add_task("changer", "Do something!")
        result = self.package_manager.spawn_handler(PackageChanger)

        def got_result(result):
            log = self.logfile.getvalue()
            self.assertIn("RUN", log)
            # restore permissions to the dir so tearDown can clean it up
            os.chmod(dir, 0o766)

        return result.addCallback(got_result)

    def test_change_package_locks_handling(self):
        """
        The L{PackageManager.handle_change_package_locks} method is registered
        as handler for messages of type C{"change-package-locks"}, and queues
        a package-changer task in the appropriate queue.
        """
        self.manager.add(self.package_manager)

        with mock.patch.object(self.package_manager, "spawn_handler"):
            message = {"type": "change-package-locks"}
            self.manager.dispatch_message(message)
            task = self.package_store.get_next_task("changer")
            self.assertTrue(task)
            self.assertEqual(task.data, message)
            self.package_manager.spawn_handler.assert_called_once_with(
                PackageChanger)
