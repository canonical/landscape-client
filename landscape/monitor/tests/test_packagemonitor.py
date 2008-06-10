import os

from twisted.internet.defer import Deferred

from landscape.lib.persist import Persist

from landscape.package.reporter import find_reporter_command
from landscape.package.store import PackageStore

from landscape.monitor.packagemonitor import PackageMonitor
from landscape.monitor.monitor import MonitorPluginRegistry
from landscape.tests.helpers import (
    LandscapeIsolatedTest, RemoteBrokerHelper, EnvironSaverHelper)


class PackageMonitorTest(LandscapeIsolatedTest):
    """Tests for the temperature plugin."""

    helpers = [RemoteBrokerHelper, EnvironSaverHelper]

    def setUp(self):
        """Initialize test helpers and create a sample thermal zone."""
        super(PackageMonitorTest, self).setUp()
        self.monitor = MonitorPluginRegistry(self.broker_service.reactor,
                                            self.remote,
                                            self.broker_service.config,
                                            Persist(), self.makeFile())

        self.package_store_filename = self.makeFile()
        self.package_store = PackageStore(self.package_store_filename)

        self.package_monitor = PackageMonitor(self.package_store_filename)

    def test_create_default_store_on_registration(self):
        filename = os.path.join(self.broker_service.config.data_path,
                                "package/database")
        package_monitor = PackageMonitor()
        os.unlink(filename)
        self.assertFalse(os.path.isfile(filename))
        self.monitor.add(package_monitor)
        self.assertTrue(os.path.isfile(filename))

    def test_dont_spawn_reporter_if_message_not_accepted(self):
        self.monitor.add(self.package_monitor)

        package_monitor_mock = self.mocker.patch(self.package_monitor)
        package_monitor_mock.spawn_reporter()
        self.mocker.count(0)

        self.mocker.replay()

        return self.package_monitor.run()

    def test_spawn_reporter_on_registration_when_already_accepted(self):
        package_monitor_mock = self.mocker.patch(self.package_monitor)
        package_monitor_mock.spawn_reporter()

        # Slightly tricky as we have to wait for the result of run(),
        # but we don't have its deferred yet.  To handle it, we create
        # our own deferred, and register a callback for when run()
        # returns, chaining both deferreds at that point.
        deferred = Deferred()
        def run_has_run(run_result_deferred):
            return run_result_deferred.chainDeferred(deferred)

        package_monitor_mock.run()
        self.mocker.passthrough(run_has_run)

        self.mocker.replay()

        self.broker_service.message_store.set_accepted_types(["packages"])
        self.monitor.add(self.package_monitor)

        return deferred

    def test_spawn_reporter_on_run_if_message_accepted(self):
        self.monitor.add(self.package_monitor)

        self.broker_service.message_store.set_accepted_types(["packages"])

        package_monitor_mock = self.mocker.patch(self.package_monitor)
        package_monitor_mock.spawn_reporter()
        self.mocker.count(2) # Once for registration, then again explicitly.

        self.mocker.replay()

        return self.package_monitor.run()

    def test_package_ids_handling(self):
        self.monitor.add(self.package_monitor)

        package_monitor_mock = self.mocker.patch(self.package_monitor)
        package_monitor_mock.spawn_reporter()
        self.mocker.replay()

        message = {"type": "package-ids", "ids": [None], "request-id": 1}
        self.broker_service.reactor.fire(("message", "package-ids"), message)
        task = self.package_store.get_next_task("reporter")
        self.assertTrue(task)
        self.assertEquals(task.data, message)

    def test_spawn_reporter(self):
        command = self.makeFile("#!/bin/sh\necho 'I am the reporter!' >&2\n")
        os.chmod(command, 0755)
        find_command_mock = self.mocker.replace(find_reporter_command)
        find_command_mock()
        self.mocker.result(command)
        self.mocker.replay()

        package_monitor = PackageMonitor(self.package_store_filename)
        self.monitor.add(package_monitor)
        result = package_monitor.spawn_reporter()

        def got_result(result):
            log = self.logfile.getvalue()
            self.assertIn("I am the reporter!", log)
            self.assertNotIn(command, log)

        return result.addCallback(got_result)

    def test_spawn_reporter_without_output(self):
        find_command_mock = self.mocker.replace(find_reporter_command)
        find_command_mock()
        self.mocker.result("/bin/true")
        self.mocker.replay()

        package_monitor = PackageMonitor(self.package_store_filename)
        self.monitor.add(package_monitor)
        result = package_monitor.spawn_reporter()

        def got_result(result):
            log = self.logfile.getvalue()
            self.assertNotIn("reporter output", log)

        return result.addCallback(got_result)

    def test_spawn_reporter_copies_environment(self):
        command = self.makeFile("#!/bin/sh\necho VAR: $VAR\n")
        os.chmod(command, 0755)
        find_command_mock = self.mocker.replace(find_reporter_command)
        find_command_mock()
        self.mocker.result(command)
        self.mocker.replay()

        package_monitor = PackageMonitor(self.package_store_filename)
        self.monitor.add(package_monitor)

        os.environ["VAR"] = "HI!"

        result = package_monitor.spawn_reporter()

        def got_result(result):
            log = self.logfile.getvalue()
            self.assertIn("VAR: HI!", log)
            self.assertNotIn(command, log)

        return result.addCallback(got_result)

    def test_spawn_reporter_passes_quiet_option(self):
        command = self.makeFile("#!/bin/sh\necho OPTIONS: $@\n")
        os.chmod(command, 0755)
        find_command_mock = self.mocker.replace(find_reporter_command)
        find_command_mock()
        self.mocker.result(command)
        self.mocker.replay()

        package_monitor = PackageMonitor(self.package_store_filename)
        self.monitor.add(package_monitor)

        result = package_monitor.spawn_reporter()

        def got_result(result):
            log = self.logfile.getvalue()
            self.assertIn("OPTIONS: --quiet", log)
            self.assertNotIn(command, log)

        return result.addCallback(got_result)

    def test_call_on_accepted(self):
        package_monitor_mock = self.mocker.patch(self.package_monitor)
        package_monitor_mock.spawn_reporter()

        self.mocker.replay()

        self.monitor.add(self.package_monitor)
        self.monitor.reactor.fire(
            ("message-type-acceptance-changed", "packages"), True)

    def test_resynchronize(self):
        """
        If a 'resynchronize' reactor event is fired, the package
        monitor should clear all queued tasks and queue a task that
        tells the report to clear out the rest of the package data.
        """
        self.monitor.add(self.package_monitor)
        message = {"type": "package-ids", "ids": [None], "request-id": 1}
        self.package_store.add_task("reporter", message)

        self.broker_service.reactor.fire("resynchronize")

        # The next task should be the resynchronize message.
        task = self.package_store.get_next_task("reporter")
        self.assertEquals(task.data, {"type" : "resynchronize"})

        # We want to make sure it has the correct id of 2 so that we
        # know it's not a new task that the reporter could possibly
        # remove by accident.
        self.assertEquals(task.id, 2)

        # Let's remove that task and make sure there are no more tasks
        # in the queue.
        task.remove()
        task = self.package_store.get_next_task("reporter")
        self.assertEquals(task, None)

    def test_spawn_reporter_doesnt_chdir(self):
        command = self.makeFile("#!/bin/sh\necho RUN\n")
        os.chmod(command, 0755)
        dir = self.make_dir()
        cwd = os.getcwd()
        os.chdir(dir)
        os.chmod(dir, 0)
        
        find_command_mock = self.mocker.replace(find_reporter_command)
        find_command_mock()
        self.mocker.result(command)
        self.mocker.replay()

        package_monitor = PackageMonitor(self.package_store_filename)
        self.monitor.add(package_monitor)

        result = package_monitor.spawn_reporter()

        def got_result(result):
            log = self.logfile.getvalue()
            self.assertIn("RUN", log)
            # restore permissions to the dir so tearDown can clean it up
            os.chmod(dir, 0766)

        return result.addCallback(got_result)
