import os
import mock

from twisted.internet.defer import Deferred

from landscape.lib.apt.package.store import PackageStore

from landscape.lib.testing import EnvironSaverHelper
from landscape.client.monitor.packagemonitor import PackageMonitor
from landscape.client.tests.helpers import LandscapeTest, MonitorHelper


class PackageMonitorTest(LandscapeTest):
    """Tests for the temperature plugin."""

    helpers = [EnvironSaverHelper, MonitorHelper]

    def setUp(self):
        """Initialize test helpers and create a sample thermal zone."""
        super(PackageMonitorTest, self).setUp()
        self.package_store_filename = self.makeFile()
        self.package_store = PackageStore(self.package_store_filename)

        self.package_monitor = PackageMonitor(self.package_store_filename)

    def createReporterTask(self):
        """
        Put a task for the package reported into the package store.
        """
        message = {"type": "package-ids", "ids": [None], "request-id": 1}
        return self.package_store.add_task("reporter", message)

    def assertSingleReporterTask(self, data, task_id):
        """
        Check that we have exactly one task, that it contains the right data
        and that it's ID matches our expectation.
        """
        # The next task should contain the passed data.
        task = self.package_store.get_next_task("reporter")
        self.assertEqual(task.data, data)

        # We want to make sure it has the correct id of 2 so that we
        # know it's not a new task that the reporter could possibly
        # remove by accident.
        self.assertEqual(task.id, task_id)

        # Let's remove that task and make sure there are no more tasks
        # in the queue.
        task.remove()
        task = self.package_store.get_next_task("reporter")
        self.assertEqual(task, None)

    def test_create_default_store_upon_message_handling(self):
        """
        If the package sqlite database file doesn't exist yet, it is created
        upon message handling.
        """
        filename = os.path.join(self.broker_service.config.data_path,
                                "package/database")
        package_monitor = PackageMonitor()
        os.unlink(filename)
        self.assertFalse(os.path.isfile(filename))

        self.monitor.add(package_monitor)
        with mock.patch.object(package_monitor, 'spawn_reporter') as mocked:
            message = {"type": "package-ids"}
            self.monitor.dispatch_message(message)

        self.assertTrue(os.path.isfile(filename))
        mocked.assert_called_once_with()

    def test_run_interval(self):
        """
        The C{run_interval} of L{PackageMonitor} can be customized via the
        C{package_monitor_interval} configuration parameter.
        """
        self.monitor.config.package_monitor_interval = 1234
        self.package_monitor.register(self.monitor)
        self.assertEqual(1234, self.package_monitor.run_interval)

    def test_do_not_spawn_reporter_if_message_not_accepted(self):
        self.monitor.add(self.package_monitor)
        with mock.patch.object(self.package_monitor, 'spawn_reporter') as mkd:
            self.successResultOf(self.package_monitor.run())
            self.assertEqual(mkd.mock_calls, [])

    def test_spawn_reporter_on_registration_when_already_accepted(self):
        real_run = self.package_monitor.run

        # Slightly tricky as we have to wait for the result of run(),
        # but we don't have its deferred yet.  To handle it, we create
        # our own deferred, and register a callback for when run()
        # returns, chaining both deferreds at that point.
        deferred = Deferred()

        def run_has_run():
            run_result_deferred = real_run()
            return run_result_deferred.chainDeferred(deferred)

        with (mock.patch.object(self.package_monitor, 'spawn_reporter')
              ) as mock_spawn_reporter:
            with mock.patch.object(self.package_monitor, 'run',
                                   side_effect=run_has_run):
                (self.broker_service.message_store
                 ).set_accepted_types(["packages"])
                self.monitor.add(self.package_monitor)
                self.successResultOf(deferred)

        mock_spawn_reporter.assert_called_once_with()

    def test_spawn_reporter_on_run_if_message_accepted(self):
        self.broker_service.message_store.set_accepted_types(["packages"])
        with mock.patch.object(self.package_monitor, 'spawn_reporter') as mkd:
            self.monitor.add(self.package_monitor)
            # We want to ignore calls made as a result of the above line.
            mkd.reset_mock()
            self.successResultOf(self.package_monitor.run())

        self.assertEqual(mkd.call_count, 1)

    def test_package_ids_handling(self):
        self.monitor.add(self.package_monitor)

        with mock.patch.object(self.package_monitor, 'spawn_reporter'):
            message = {"type": "package-ids", "ids": [None], "request-id": 1}
            self.monitor.dispatch_message(message)
            task = self.package_store.get_next_task("reporter")

        self.assertTrue(task)
        self.assertEqual(task.data, message)

    def test_spawn_reporter(self):
        command = self.write_script(
            self.config,
            "landscape-package-reporter",
            "#!/bin/sh\necho 'I am the reporter!' >&2\n")

        package_monitor = PackageMonitor(self.package_store_filename)
        self.monitor.add(package_monitor)
        result = package_monitor.spawn_reporter()

        def got_result(result):
            log = self.logfile.getvalue()
            self.assertIn("I am the reporter!", log)
            self.assertNotIn(command, log)

        return result.addCallback(got_result)

    def test_spawn_reporter_without_output(self):
        self.write_script(
            self.config,
            "landscape-package-reporter",
            "#!/bin/sh\n/bin/true")

        package_monitor = PackageMonitor(self.package_store_filename)
        self.monitor.add(package_monitor)
        result = package_monitor.spawn_reporter()

        def got_result(result):
            log = self.logfile.getvalue()
            self.assertNotIn("reporter output", log)

        return result.addCallback(got_result)

    def test_spawn_reporter_copies_environment(self):
        command = self.write_script(
            self.config,
            "landscape-package-reporter",
            "#!/bin/sh\necho VAR: $VAR\n")

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
        command = self.write_script(
            self.config,
            "landscape-package-reporter",
            "#!/bin/sh\necho OPTIONS: $@\n")

        package_monitor = PackageMonitor(self.package_store_filename)
        self.monitor.add(package_monitor)

        result = package_monitor.spawn_reporter()

        def got_result(result):
            log = self.logfile.getvalue()
            self.assertIn("OPTIONS: --quiet", log)
            self.assertNotIn(command, log)

        return result.addCallback(got_result)

    def test_call_on_accepted(self):
        with mock.patch.object(self.package_monitor, 'spawn_reporter') as mkd:
            self.monitor.add(self.package_monitor)
            self.monitor.reactor.fire(
                ("message-type-acceptance-changed", "packages"), True)

        mkd.assert_called_once_with()

    def test_resynchronize(self):
        """
        If a 'resynchronize' reactor event is fired with 'package' scope, the
        package monitor should clear all queued tasks and queue a task that
        tells the report to clear out the rest of the package data.
        """
        self.monitor.add(self.package_monitor)
        self.createReporterTask()

        # The server doesn't currently send 'package' scope, but we should
        # support it in case we change that in the future.
        package_scope = ["package"]
        self.monitor.reactor.fire("resynchronize", package_scope)

        self.assertSingleReporterTask({"type": "resynchronize"}, 2)

    def test_resynchronize_gets_new_session_id(self):
        """
        When a 'resynchronize' reactor event is fired, the C{PackageMonitor}
        acquires a new session ID (as the old one will be blocked).
        """
        self.monitor.add(self.package_monitor)
        session_id = self.package_monitor._session_id
        self.createReporterTask()

        self.package_monitor.client.broker.message_store.drop_session_ids()
        self.monitor.reactor.fire("resynchronize")
        self.assertNotEqual(session_id, self.package_monitor._session_id)

    def test_resynchronize_on_global_scope(self):
        """
        If a 'resynchronize' reactor event is fired with global scope (the
        empty list) , the package monitor should act as if it were an event
        with 'package' scope.
        """
        self.monitor.add(self.package_monitor)
        self.createReporterTask()

        self.monitor.reactor.fire("resynchronize")

        # The next task should be the resynchronize message.
        self.assertSingleReporterTask({"type": "resynchronize"}, 2)

    def test_not_resynchronize_with_other_scope(self):
        """
        If a 'resynchronize' reactor event is fired with an irrelevant scope,
        the package monitor should not respond to this.
        """
        self.monitor.add(self.package_monitor)
        task = self.createReporterTask()

        disk_scope = ["disk"]
        self.monitor.reactor.fire("resynchronize", disk_scope)

        # The next task should *not* be the resynchronize message, but instead
        # the original task we created.
        self.assertSingleReporterTask(task.data, task.id)

    def test_spawn_reporter_doesnt_chdir(self):
        self.write_script(
            self.config,
            "landscape-package-reporter",
            "#!/bin/sh\necho RUN\n")
        cwd = os.getcwd()
        self.addCleanup(os.chdir, cwd)
        dir = self.makeDir()
        os.chdir(dir)
        os.chmod(dir, 0)

        package_monitor = PackageMonitor(self.package_store_filename)
        self.monitor.add(package_monitor)

        result = package_monitor.spawn_reporter()

        def got_result(result):
            log = self.logfile.getvalue()
            self.assertIn("RUN", log)
            # restore permissions to the dir so tearDown can clean it up
            os.chmod(dir, 0o766)

        return result.addCallback(got_result)

    def test_changing_server_uuid_clears_hash_ids(self):
        """
        The package hash=>id map is server-specific, so when we change
        servers, we should reset this map.
        """
        self.package_store.set_hash_ids({b"hash1": 1, b"hash2": 2})
        self.monitor.add(self.package_monitor)
        self.monitor.reactor.fire("server-uuid-changed", "old", "new")

        self.assertEqual(self.package_store.get_hash_id(b"hash1"), None)
        self.assertEqual(self.package_store.get_hash_id(b"hash2"), None)

    def test_changing_server_uuid_wont_clear_hash_ids_with_old_uuid_none(self):
        """
        If the old UUID is unknown, that means the client just started
        talking to a server that knows how to communicate its UUID, so we
        don't want to clear the old hashes in this case.
        """
        self.package_store.set_hash_ids({b"hash1": 1, b"hash2": 2})
        self.monitor.add(self.package_monitor)
        self.monitor.reactor.fire("server-uuid-changed", None, "new-uuid")
        self.assertEqual(self.package_store.get_hash_id(b"hash1"), 1)
        self.assertEqual(self.package_store.get_hash_id(b"hash2"), 2)
