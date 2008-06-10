import os

from twisted.internet.defer import Deferred

from landscape.package.changer import find_changer_command
from landscape.package.store import PackageStore

from landscape.manager.packagemanager import PackageManager
from landscape.manager.manager import ManagerPluginRegistry
from landscape.tests.helpers import (
    LandscapeIsolatedTest, RemoteBrokerHelper, EnvironSaverHelper)


class PackageManagerTest(LandscapeIsolatedTest):
    """Tests for the temperature plugin."""

    helpers = [RemoteBrokerHelper, EnvironSaverHelper]

    def setUp(self):
        """Initialize test helpers and create a sample thermal zone."""
        LandscapeIsolatedTest.setUp(self)

        self.manager = ManagerPluginRegistry(self.broker_service.reactor,
                                             self.remote,
                                             self.broker_service.config)

        self.package_store_filename = self.makeFile()
        self.package_store = PackageStore(self.package_store_filename)
        self.package_manager = PackageManager(self.package_store_filename)

    def test_create_default_store_on_registration(self):
        filename = os.path.join(self.broker_service.config.data_path,
                                "package/database")
        package_manager = PackageManager()
        os.unlink(filename)
        self.assertFalse(os.path.isfile(filename))
        self.manager.add(package_manager)
        self.assertTrue(os.path.isfile(filename))

    def test_dont_spawn_changer_if_message_not_accepted(self):
        self.manager.add(self.package_manager)

        package_manager_mock = self.mocker.patch(self.package_manager)
        package_manager_mock.spawn_changer()
        self.mocker.count(0)

        self.mocker.replay()

        return self.package_manager.run()

    def test_spawn_changer_on_registration_when_already_accepted(self):
        package_manager_mock = self.mocker.patch(self.package_manager)
        package_manager_mock.spawn_changer()

        # Slightly tricky as we have to wait for the result of run(),
        # but we don't have its deferred yet.  To handle it, we create
        # our own deferred, and register a callback for when run()
        # returns, chaining both deferreds at that point.
        deferred = Deferred()
        def run_has_run(run_result_deferred):
            return run_result_deferred.chainDeferred(deferred)

        package_manager_mock.run()
        self.mocker.passthrough(run_has_run)

        self.mocker.replay()

        service = self.broker_service
        service.message_store.set_accepted_types(["change-packages-result"])
        self.manager.add(self.package_manager)

        return deferred

    def test_spawn_changer_on_run_if_message_accepted(self):
        self.manager.add(self.package_manager)

        service = self.broker_service
        service.message_store.set_accepted_types(["change-packages-result"])

        package_manager_mock = self.mocker.patch(self.package_manager)
        package_manager_mock.spawn_changer()
        self.mocker.count(2) # Once for registration, then again explicitly.

        self.mocker.replay()

        return self.package_manager.run()

    def test_change_packages_handling(self):
        self.manager.add(self.package_manager)

        package_manager_mock = self.mocker.patch(self.package_manager)
        package_manager_mock.spawn_changer()
        self.mocker.replay()

        message = {"type": "change-packages"}
        service = self.broker_service
        self.manager.dispatch_message(message)
        task = self.package_store.get_next_task("changer")
        self.assertTrue(task)
        self.assertEquals(task.data, message)

    def test_spawn_changer(self):
        command = self.makeFile("#!/bin/sh\necho 'I am the changer!' >&2\n")
        os.chmod(command, 0755)
        find_command_mock = self.mocker.replace(find_changer_command)
        find_command_mock()
        self.mocker.result(command)
        self.mocker.replay()

        self.package_store.add_task("changer", "Do something!")

        package_manager = PackageManager(self.package_store_filename)
        self.manager.add(package_manager)
        result = package_manager.spawn_changer()

        def got_result(result):
            log = self.logfile.getvalue()
            self.assertIn("I am the changer!", log)
            self.assertNotIn(command, log)

        return result.addCallback(got_result)

    def test_spawn_changer_without_output(self):
        find_command_mock = self.mocker.replace(find_changer_command)
        find_command_mock()
        self.mocker.result("/bin/true")
        self.mocker.replay()

        self.package_store.add_task("changer", "Do something!")

        package_manager = PackageManager(self.package_store_filename)
        self.manager.add(package_manager)
        result = package_manager.spawn_changer()

        def got_result(result):
            log = self.logfile.getvalue()
            self.assertNotIn("changer output", log)

        return result.addCallback(got_result)

    def test_spawn_changer_copies_environment(self):
        command = self.makeFile("#!/bin/sh\necho VAR: $VAR\n")
        os.chmod(command, 0755)
        find_command_mock = self.mocker.replace(find_changer_command)
        find_command_mock()
        self.mocker.result(command)
        self.mocker.replay()

        package_manager = PackageManager(self.package_store_filename)
        self.manager.add(package_manager)

        self.package_store.add_task("changer", "Do something!")

        os.environ["VAR"] = "HI!"

        result = package_manager.spawn_changer()

        def got_result(result):
            log = self.logfile.getvalue()
            self.assertIn("VAR: HI!", log)
            self.assertNotIn(command, log)

        return result.addCallback(got_result)

    def test_spawn_changer_passes_quiet_option(self):
        command = self.makeFile("#!/bin/sh\necho OPTIONS: $@\n")
        os.chmod(command, 0755)
        find_command_mock = self.mocker.replace(find_changer_command)
        find_command_mock()
        self.mocker.result(command)
        self.mocker.replay()

        package_manager = PackageManager(self.package_store_filename)
        self.manager.add(package_manager)

        self.package_store.add_task("changer", "Do something!")

        result = package_manager.spawn_changer()

        def got_result(result):
            log = self.logfile.getvalue()
            self.assertIn("OPTIONS: --quiet", log)
            self.assertNotIn(command, log)

        return result.addCallback(got_result)

    def test_spawn_changer_wont_run_without_tasks(self):
        command = self.makeFile("#!/bin/sh\necho RUN!\n")
        os.chmod(command, 0755)
        find_command_mock = self.mocker.replace(find_changer_command)
        find_command_mock()
        self.mocker.result(command)
        self.mocker.replay()

        package_manager = PackageManager(self.package_store_filename)
        self.manager.add(package_manager)

        result = package_manager.spawn_changer()

        def got_result(result):
            log = self.logfile.getvalue()
            self.assertNotIn("RUN!", log)

        return result.addCallback(got_result)

    def test_spawn_changer_doesnt_chdir(self):
        command = self.makeFile("#!/bin/sh\necho RUN\n")
        os.chmod(command, 0755)
        dir = self.make_dir()
        os.chdir(dir)
        os.chmod(dir, 0)
        
        find_command_mock = self.mocker.replace(find_changer_command)
        find_command_mock()
        self.mocker.result(command)
        self.mocker.replay()

        package_manager = PackageManager(self.package_store_filename)
        self.manager.add(package_manager)

        self.package_store.add_task("changer", "Do something!")

        result = package_manager.spawn_changer()

        def got_result(result):
            log = self.logfile.getvalue()
            self.assertIn("RUN", log)
            # restore permissions to the dir so tearDown can clean it up
            os.chmod(dir, 0766)

        return result.addCallback(got_result)
