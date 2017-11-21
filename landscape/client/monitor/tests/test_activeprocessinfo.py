import operator
import os
import shutil
import tempfile
import subprocess

from twisted.internet.defer import fail

from landscape.lib.testing import ProcessDataBuilder
from landscape.client.monitor.activeprocessinfo import ActiveProcessInfo
from landscape.client.tests.helpers import LandscapeTest, MonitorHelper
from mock import ANY, Mock, patch


class ActiveProcessInfoTest(LandscapeTest):
    """Active process info plugin tests."""

    helpers = [MonitorHelper]

    def setUp(self):
        """Initialize helpers and sample data builder."""
        LandscapeTest.setUp(self)
        self.sample_dir = tempfile.mkdtemp()
        self.builder = ProcessDataBuilder(self.sample_dir)
        self.mstore.set_accepted_types(["active-process-info"])

    def tearDown(self):
        """Clean up sample data artifacts."""
        shutil.rmtree(self.sample_dir)
        LandscapeTest.tearDown(self)

    def test_first_run_includes_kill_message(self):
        """Test ensures that the first run queues a kill-processes message."""
        plugin = ActiveProcessInfo(uptime=10)
        self.monitor.add(plugin)
        plugin.exchange()
        message = self.mstore.get_pending_messages()[0]
        self.assertEqual(message["type"], "active-process-info")
        self.assertTrue("kill-all-processes" in message)
        self.assertEqual(message["kill-all-processes"], True)
        self.assertTrue("add-processes" in message)

    def test_only_first_run_includes_kill_message(self):
        """Test ensures that only the first run queues a kill message."""
        self.builder.create_data(672, self.builder.TRACING_STOP,
                                 uid=1000, gid=1000, started_after_boot=10,
                                 process_name="blarpy")

        plugin = ActiveProcessInfo(proc_dir=self.sample_dir, uptime=10)
        self.monitor.add(plugin)
        self.monitor.exchange()

        self.builder.create_data(671, self.builder.STOPPED, uid=1000,
                                 gid=1000, started_after_boot=15,
                                 process_name="blargh")
        self.monitor.exchange()
        messages = self.mstore.get_pending_messages()
        self.assertEqual(len(messages), 2)
        message = messages[0]
        self.assertEqual(message["type"], "active-process-info")
        self.assertTrue("kill-all-processes" in message)
        self.assertTrue("add-processes" in message)

        message = messages[1]
        self.assertEqual(message["type"], "active-process-info")
        self.assertTrue("add-processes" in message)

    def test_terminating_process_race(self):
        """Test that the plugin handles process termination races.

        There is a potential race in the time between getting a list
        of process directories in C{/proc} and reading
        C{/proc/<process-id>/status} or C{/proc/<process-id>/stat}.
        The process with C{<process-id>} may terminate and causing
        status (or stat) to be removed in this window, resulting in an
        file-not-found IOError.

        This test simulates race behaviour by creating a directory for
        a process without a C{status} or C{stat} file.
        """
        directory = tempfile.mkdtemp()
        try:
            os.mkdir(os.path.join(directory, "42"))
            plugin = ActiveProcessInfo(proc_dir=directory, uptime=10)
            self.monitor.add(plugin)
            plugin.exchange()
        finally:
            shutil.rmtree(directory)

    def test_read_proc(self):
        """Test reading from /proc."""
        plugin = ActiveProcessInfo(uptime=10)
        self.monitor.add(plugin)
        plugin.exchange()
        messages = self.mstore.get_pending_messages()
        self.assertTrue(len(messages) > 0)
        self.assertTrue("add-processes" in messages[0])

    def test_read_sample_data(self):
        """Test reading a sample set of process data."""
        self.builder.create_data(1, self.builder.RUNNING, uid=0, gid=0,
                                 started_after_boot=1030, process_name="init")
        self.builder.create_data(671, self.builder.STOPPED, uid=1000,
                                 gid=1000, started_after_boot=1110,
                                 process_name="blargh")
        self.builder.create_data(672, self.builder.TRACING_STOP,
                                 uid=1000, gid=1000, started_after_boot=1120,
                                 process_name="blarpy")

        plugin = ActiveProcessInfo(proc_dir=self.sample_dir, uptime=100,
                                   jiffies=10, boot_time=0)
        self.monitor.add(plugin)
        plugin.exchange()
        message = self.mstore.get_pending_messages()[0]
        self.assertEqual(message["type"], "active-process-info")
        self.assertTrue("kill-all-processes" in message)
        self.assertTrue("add-processes" in message)
        expected_process_0 = {"state": b"R", "gid": 0, "pid": 1,
                              "vm-size": 11676, "name": "init", "uid": 0,
                              "start-time": 103, "percent-cpu": 0.0}
        expected_process_1 = {"state": b"T", "gid": 1000, "pid": 671,
                              "vm-size": 11676, "name": "blargh", "uid": 1000,
                              "start-time": 111, "percent-cpu": 0.0}
        expected_process_2 = {"state": b"t", "gid": 1000, "pid": 672,
                              "vm-size": 11676, "name": "blarpy", "uid": 1000,
                              "start-time": 112, "percent-cpu": 0.0}
        processes = message["add-processes"]
        processes.sort(key=operator.itemgetter("pid"))
        self.assertEqual(processes, [expected_process_0, expected_process_1,
                                     expected_process_2])

    def test_skip_non_numeric_subdirs(self):
        """Test ensures the plugin doesn't touch non-process dirs in /proc."""
        self.builder.create_data(1, self.builder.RUNNING, uid=0, gid=0,
                                 started_after_boot=1120, process_name="init")

        directory = os.path.join(self.sample_dir, "acpi")
        os.mkdir(directory)
        self.assertTrue(os.path.isdir(directory))

        plugin = ActiveProcessInfo(proc_dir=self.sample_dir, uptime=100,
                                   jiffies=10, boot_time=0)
        self.monitor.add(plugin)
        plugin.exchange()
        message = self.mstore.get_pending_messages()[0]
        self.assertEqual(message["type"], "active-process-info")
        self.assertTrue("kill-all-processes" in message)
        self.assertTrue("add-processes" in message)

        expected_process = {"pid": 1, "state": b"R", "name": "init",
                            "vm-size": 11676, "uid": 0, "gid": 0,
                            "start-time": 112, "percent-cpu": 0.0}
        self.assertEqual(message["add-processes"], [expected_process])

    def test_plugin_manager(self):
        """Test plugin manager integration."""
        self.builder.create_data(1, self.builder.RUNNING, uid=0, gid=0,
                                 started_after_boot=1100, process_name="init")

        plugin = ActiveProcessInfo(proc_dir=self.sample_dir, uptime=100,
                                   jiffies=10, boot_time=0)
        self.monitor.add(plugin)
        self.monitor.exchange()

        self.assertMessages(
            self.mstore.get_pending_messages(),
            [{"type": "active-process-info",
              "kill-all-processes": True,
              "add-processes": [{"pid": 1, "state": b"R", "name": "init",
                                 "vm-size": 11676, "uid": 0, "gid": 0,
                                 "start-time": 110, "percent-cpu": 0.0}]}])

    def test_process_terminated(self):
        """Test that the plugin handles process changes in a diff-like way."""
        # This test is *too big*
        self.builder.create_data(1, self.builder.RUNNING, uid=0, gid=0,
                                 started_after_boot=1010, process_name="init")
        self.builder.create_data(671, self.builder.STOPPED, uid=1000,
                                 gid=1000, started_after_boot=1020,
                                 process_name="blargh")
        self.builder.create_data(672, self.builder.TRACING_STOP,
                                 uid=1000, gid=1000, started_after_boot=1040,
                                 process_name="blarpy")

        plugin = ActiveProcessInfo(proc_dir=self.sample_dir, uptime=100,
                                   jiffies=10, boot_time=0)
        self.monitor.add(plugin)
        plugin.exchange()

        # Terminate a process and start another.
        self.builder.remove_data(671)
        self.builder.create_data(12753, self.builder.RUNNING,
                                 uid=0, gid=0, started_after_boot=1070,
                                 process_name="wubble")

        plugin.exchange()
        messages = self.mstore.get_pending_messages()
        self.assertEqual(len(messages), 2)

        # The first time the plugin runs we expect all known processes
        # to be killed.
        message = messages[0]
        self.assertEqual(message["type"], "active-process-info")
        self.assertTrue("kill-all-processes" in message)
        self.assertEqual(message["kill-all-processes"], True)
        self.assertTrue("add-processes" in message)
        expected_process_0 = {"state": b"R", "gid": 0, "pid": 1,
                              "vm-size": 11676, "name": "init",
                              "uid": 0, "start-time": 101,
                              "percent-cpu": 0.0}
        expected_process_1 = {"state": b"T", "gid": 1000, "pid": 671,
                              "vm-size": 11676, "name": "blargh",
                              "uid": 1000, "start-time": 102,
                              "percent-cpu": 0.0}
        expected_process_2 = {"state": b"t", "gid": 1000, "pid": 672,
                              "vm-size": 11676, "name": "blarpy",
                              "uid": 1000, "start-time": 104,
                              "percent-cpu": 0.0}
        processes = message["add-processes"]
        processes.sort(key=operator.itemgetter("pid"))
        self.assertEqual(processes, [expected_process_0, expected_process_1,
                                     expected_process_2])

        # Report diff-like changes to processes, such as terminated
        # processes and new processes.
        message = messages[1]
        self.assertEqual(message["type"], "active-process-info")

        self.assertTrue("add-processes" in message)
        self.assertEqual(len(message["add-processes"]), 1)
        expected_process = {"state": b"R", "gid": 0, "pid": 12753,
                            "vm-size": 11676, "name": "wubble",
                            "uid": 0, "start-time": 107,
                            "percent-cpu": 0.0}
        self.assertEqual(message["add-processes"], [expected_process])

        self.assertTrue("kill-processes" in message)
        self.assertEqual(len(message["kill-processes"]), 1)
        self.assertEqual(message["kill-processes"], [671])

    def test_only_queue_message_when_process_data_is_available(self):
        """Test ensures that messages are only queued when data changes."""
        self.builder.create_data(672, self.builder.TRACING_STOP,
                                 uid=1000, gid=1000, started_after_boot=10,
                                 process_name="blarpy")

        plugin = ActiveProcessInfo(proc_dir=self.sample_dir, uptime=10)
        self.monitor.add(plugin)

        plugin.exchange()
        self.assertEqual(len(self.mstore.get_pending_messages()), 1)

        plugin.exchange()
        self.assertEqual(len(self.mstore.get_pending_messages()), 1)

    def test_only_report_active_processes(self):
        """Test ensures the plugin only reports active processes."""
        self.builder.create_data(672, self.builder.DEAD,
                                 uid=1000, gid=1000, started_after_boot=10,
                                 process_name="blarpy")
        self.builder.create_data(673, self.builder.ZOMBIE,
                                 uid=1000, gid=1000, started_after_boot=12,
                                 process_name="blarpitty")
        self.builder.create_data(674, self.builder.RUNNING,
                                 uid=1000, gid=1000, started_after_boot=13,
                                 process_name="blarpie")
        self.builder.create_data(675, self.builder.STOPPED,
                                 uid=1000, gid=1000, started_after_boot=14,
                                 process_name="blarping")
        self.builder.create_data(676, self.builder.TRACING_STOP,
                                 uid=1000, gid=1000, started_after_boot=15,
                                 process_name="floerp")
        self.builder.create_data(677, self.builder.DISK_SLEEP,
                                 uid=1000, gid=1000, started_after_boot=18,
                                 process_name="floerpidity")
        self.builder.create_data(678, self.builder.SLEEPING,
                                 uid=1000, gid=1000, started_after_boot=21,
                                 process_name="floerpiditting")

        plugin = ActiveProcessInfo(proc_dir=self.sample_dir, uptime=10)
        self.monitor.add(plugin)

        plugin.exchange()
        messages = self.mstore.get_pending_messages()
        self.assertEqual(len(messages), 1)

        message = messages[0]
        self.assertTrue("kill-all-processes" in message)
        self.assertTrue("kill-processes" not in message)
        self.assertTrue("add-processes" in message)

        pids = [process["pid"] for process in message["add-processes"]]
        pids.sort()
        self.assertEqual(pids, [673, 674, 675, 676, 677, 678])

    def test_report_interesting_state_changes(self):
        """Test ensures that interesting state changes are reported."""
        self.builder.create_data(672, self.builder.RUNNING,
                                 uid=1000, gid=1000, started_after_boot=10,
                                 process_name="blarpy")

        # Report a running process.
        plugin = ActiveProcessInfo(proc_dir=self.sample_dir, uptime=10)
        self.monitor.add(plugin)

        plugin.exchange()

        messages = self.mstore.get_pending_messages()
        self.assertEqual(len(messages), 1)
        message = messages[0]

        self.assertTrue("kill-all-processes" in message)
        self.assertTrue("kill-processes" not in message)
        self.assertTrue("add-processes" in message)
        self.assertEqual(message["add-processes"][0]["pid"], 672)
        self.assertEqual(message["add-processes"][0]["state"], b"R")

        # Convert the process to a zombie and ensure it gets reported.
        self.builder.remove_data(672)
        self.builder.create_data(672, self.builder.ZOMBIE,
                                 uid=1000, gid=1000, started_after_boot=10,
                                 process_name="blarpy")

        plugin.exchange()

        messages = self.mstore.get_pending_messages()
        self.assertEqual(len(messages), 2)
        message = messages[1]

        self.assertTrue("kill-all-processes" not in message)
        self.assertTrue("update-processes" in message)
        self.assertEqual(message["update-processes"][0]["state"], b"Z")

    def test_call_on_accepted(self):
        """
        L{MonitorPlugin}-based plugins can provide a callable to call
        when a message type becomes accepted.
        """
        plugin = ActiveProcessInfo(proc_dir=self.sample_dir, uptime=100,
                                   jiffies=10)
        self.monitor.add(plugin)
        self.assertEqual(len(self.mstore.get_pending_messages()), 0)
        result = self.monitor.fire_event(
            "message-type-acceptance-changed", "active-process-info", True)

        def assert_messages(ignored):
            self.assertEqual(len(self.mstore.get_pending_messages()), 1)

        result.addCallback(assert_messages)
        return result

    def test_resynchronize_event(self):
        """
        When a C{resynchronize} event occurs, with 'process' scope, we should
        clear the information held in memory by the activeprocess monitor.
        """
        self.builder.create_data(1, self.builder.RUNNING, uid=0, gid=0,
                                 started_after_boot=1030, process_name="init")
        self.builder.create_data(671, self.builder.STOPPED, uid=1000,
                                 gid=1000, started_after_boot=1110,
                                 process_name="blargh")
        self.builder.create_data(672, self.builder.TRACING_STOP,
                                 uid=1000, gid=1000, started_after_boot=1120,
                                 process_name="blarpy")

        plugin = ActiveProcessInfo(proc_dir=self.sample_dir, uptime=100,
                                   jiffies=10, boot_time=0)
        self.monitor.add(plugin)

        plugin.exchange()
        messages = self.mstore.get_pending_messages()

        expected_messages = [{"add-processes": [
                               {"gid": 1000,
                                "name": u"blarpy",
                                "pid": 672,
                                "start-time": 112,
                                "state": b"t",
                                "uid": 1000,
                                "vm-size": 11676,
                                "percent-cpu": 0.0},
                               {"gid": 0,
                                "name": u"init",
                                "pid": 1,
                                "start-time": 103,
                                "state": b"R",
                                "uid": 0,
                                "vm-size": 11676,
                                "percent-cpu": 0.0},
                               {"gid": 1000,
                                "name": u"blargh",
                                "pid": 671,
                                "start-time": 111,
                                "state": b"T",
                                "uid": 1000,
                                "vm-size": 11676,
                                "percent-cpu": 0.0}],
                              "kill-all-processes": True,
                              "type": "active-process-info"}]

        self.assertMessages(messages, expected_messages)

        plugin.exchange()
        messages = self.mstore.get_pending_messages()
        # No new messages should be pending
        self.assertMessages(messages, expected_messages)

        process_scope = ["process"]
        self.reactor.fire("resynchronize", process_scope)
        plugin.exchange()
        messages = self.mstore.get_pending_messages()
        # The resynchronisation should cause the same messages to be generated
        # again.
        expected_messages.extend(expected_messages)
        self.assertMessages(messages, expected_messages)

    def test_resynchronize_event_resets_session_id(self):
        """
        When a C{resynchronize} event occurs a new session id is acquired so
        that future messages can be sent.
        """
        plugin = ActiveProcessInfo(proc_dir=self.sample_dir, uptime=100,
                                   jiffies=10, boot_time=0)
        self.monitor.add(plugin)
        session_id = plugin._session_id
        plugin.client.broker.message_store.drop_session_ids()
        self.reactor.fire("resynchronize")
        plugin.exchange()
        self.assertNotEqual(session_id, plugin._session_id)

    def test_resynchronize_event_with_global_scope(self):
        """
        When a C{resynchronize} event occurs the L{_reset} method should be
        called on L{ActiveProcessInfo}.
        """
        self.builder.create_data(672, self.builder.TRACING_STOP,
                                 uid=1000, gid=1000, started_after_boot=1120,
                                 process_name="blarpy")

        plugin = ActiveProcessInfo(proc_dir=self.sample_dir, uptime=100,
                                   jiffies=10, boot_time=0)
        self.monitor.add(plugin)

        plugin.exchange()
        messages = self.mstore.get_pending_messages()

        expected_messages = [{"add-processes": [
                               {"gid": 1000,
                                "name": u"blarpy",
                                "pid": 672,
                                "start-time": 112,
                                "state": b"t",
                                "uid": 1000,
                                "vm-size": 11676,
                                "percent-cpu": 0.0}],
                              "kill-all-processes": True,
                              "type": "active-process-info"}]

        self.assertMessages(messages, expected_messages)

        plugin.exchange()
        messages = self.mstore.get_pending_messages()
        # No new messages should be pending
        self.assertMessages(messages, expected_messages)

        self.reactor.fire("resynchronize")
        plugin.exchange()
        messages = self.mstore.get_pending_messages()
        # The resynchronisation should cause the same messages to be generated
        # again.
        expected_messages.extend(expected_messages)
        self.assertMessages(messages, expected_messages)

    def test_do_not_resynchronize_with_other_scope(self):
        """
        When a C{resynchronize} event occurs, with an irrelevant scope, we
        should do nothing.
        """
        self.builder.create_data(672, self.builder.TRACING_STOP,
                                 uid=1000, gid=1000, started_after_boot=1120,
                                 process_name="blarpy")

        plugin = ActiveProcessInfo(proc_dir=self.sample_dir, uptime=100,
                                   jiffies=10, boot_time=0)
        self.monitor.add(plugin)

        plugin.exchange()
        messages = self.mstore.get_pending_messages()

        expected_messages = [{"add-processes": [
                               {"gid": 1000,
                                "name": u"blarpy",
                                "pid": 672,
                                "start-time": 112,
                                "state": b"t",
                                "uid": 1000,
                                "vm-size": 11676,
                                "percent-cpu": 0.0}],
                              "kill-all-processes": True,
                              "type": "active-process-info"}]

        self.assertMessages(messages, expected_messages)

        plugin.exchange()
        messages = self.mstore.get_pending_messages()
        # No new messages should be pending
        self.assertMessages(messages, expected_messages)

        disk_scope = ["disk"]
        self.reactor.fire("resynchronize", disk_scope)
        plugin.exchange()
        messages = self.mstore.get_pending_messages()
        # The resynchronisation should not have fired, so we won't see any
        # additional messages here.
        self.assertMessages(messages, expected_messages)

    def test_do_not_persist_changes_when_send_message_fails(self):
        """
        When the plugin is run it persists data that it uses on
        subsequent checks to calculate the delta to send.  It should
        only persist data when the broker confirms that the message
        sent by the plugin has been sent.
        """

        class MyException(Exception):
            pass

        self.log_helper.ignore_errors(MyException)

        self.builder.create_data(672, self.builder.RUNNING,
                                 uid=1000, gid=1000, started_after_boot=10,
                                 process_name="python")
        plugin = ActiveProcessInfo(proc_dir=self.sample_dir, uptime=10)
        self.monitor.add(plugin)

        self.monitor.broker.send_message = Mock(
            return_value=fail(MyException()))

        message = plugin.get_message()

        def assert_message(message_id):
            self.assertEqual(message, plugin.get_message())

        result = plugin.exchange()
        result.addCallback(assert_message)
        self.monitor.broker.send_message.assert_called_once_with(
            ANY, ANY, urgent=ANY)
        return result

    def test_process_updates(self):
        """Test updates to processes are successfully reported."""
        self.builder.create_data(1, self.builder.RUNNING, uid=0, gid=0,
                                 started_after_boot=1100, process_name="init",)

        plugin = ActiveProcessInfo(proc_dir=self.sample_dir, uptime=100,
                                   jiffies=10, boot_time=0)
        self.monitor.add(plugin)

        with patch.object(plugin.registry, 'flush') as flush_mock:
            plugin.exchange()
            flush_mock.assert_called_once_with()

            flush_mock.reset_mock()

            messages = self.mstore.get_pending_messages()
            self.assertEqual(len(messages), 1)

            self.builder.remove_data(1)
            self.builder.create_data(1, self.builder.RUNNING, uid=0, gid=0,
                                     started_after_boot=1100,
                                     process_name="init", vmsize=20000)
            plugin.exchange()
            flush_mock.assert_called_once_with()

        messages = self.mstore.get_pending_messages()
        self.assertEqual(len(messages), 2)
        self.assertMessages(messages, [{"timestamp": 0,
                                        "api": b"3.2",
                                        "type": "active-process-info",
                                        "kill-all-processes": True,
                                        "add-processes": [{"start-time": 110,
                                                           "name": u"init",
                                                           "pid": 1,
                                                           "percent-cpu": 0.0,
                                                           "state": b"R",
                                                           "gid": 0,
                                                           "vm-size": 11676,
                                                           "uid": 0}]},
                                       {"timestamp": 0,
                                        "api": b"3.2",
                                        "type": "active-process-info",
                                        "update-processes": [
                                            {"start-time": 110,
                                             "name": u"init",
                                             "pid": 1,
                                             "percent-cpu": 0.0,
                                             "state": b"R",
                                             "gid": 0,
                                             "vm-size": 20000,
                                             "uid": 0}]}])


class PluginManagerIntegrationTest(LandscapeTest):

    helpers = [MonitorHelper]

    def setUp(self):
        LandscapeTest.setUp(self)
        self.sample_dir = self.makeDir()
        self.builder = ProcessDataBuilder(self.sample_dir)
        self.mstore.set_accepted_types(["active-process-info",
                                        "operation-result"])

    def get_missing_pid(self):
        popen = subprocess.Popen(["hostname"], stdout=subprocess.PIPE)
        popen.wait()
        return popen.pid

    def get_active_process(self):
        return subprocess.Popen(["python", "-c", "raw_input()"],
                                stdin=subprocess.PIPE,
                                stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE)

    def test_read_long_process_name(self):
        """Test reading a process with a long name."""
        self.builder.create_data(1, self.builder.RUNNING, uid=0, gid=0,
                                 started_after_boot=1030,
                                 process_name="NetworkManagerDaemon")

        plugin = ActiveProcessInfo(proc_dir=self.sample_dir, uptime=2000,
                                   jiffies=10, boot_time=0)
        self.monitor.add(plugin)
        plugin.exchange()
        message = self.mstore.get_pending_messages()[0]
        self.assertEqual(message["type"], "active-process-info")
        self.assertTrue("kill-all-processes" in message)
        self.assertTrue("add-processes" in message)
        expected_process_0 = {"state": b"R", "gid": 0, "pid": 1,
                              "vm-size": 11676, "name": "NetworkManagerDaemon",
                              "uid": 0, "start-time": 103, "percent-cpu": 0.0}
        processes = message["add-processes"]
        self.assertEqual(processes, [expected_process_0])

    def test_strip_command_line_name_whitespace(self):
        """Whitespace should be stripped from command-line names."""
        self.builder.create_data(1, self.builder.RUNNING, uid=0, gid=0,
                                 started_after_boot=30,
                                 process_name=" postgres: writer process     ")
        plugin = ActiveProcessInfo(proc_dir=self.sample_dir, uptime=100,
                                   jiffies=10)
        self.monitor.add(plugin)
        plugin.exchange()
        message = self.mstore.get_pending_messages()[0]
        self.assertEqual(message["add-processes"][0]["name"],
                         u"postgres: writer process")

    def test_read_process_with_no_cmdline(self):
        """Test reading a process without a cmdline file."""
        self.builder.create_data(1, self.builder.RUNNING, uid=0, gid=0,
                                 started_after_boot=1030,
                                 process_name="ProcessWithLongName",
                                 generate_cmd_line=False)

        plugin = ActiveProcessInfo(proc_dir=self.sample_dir, uptime=100,
                                   jiffies=10, boot_time=0)
        self.monitor.add(plugin)
        plugin.exchange()
        message = self.mstore.get_pending_messages()[0]
        self.assertEqual(message["type"], "active-process-info")
        self.assertTrue("kill-all-processes" in message)
        self.assertTrue("add-processes" in message)
        expected_process_0 = {"state": b"R", "gid": 0, "pid": 1,
                              "vm-size": 11676, "name": "ProcessWithLong",
                              "uid": 0, "start-time": 103, "percent-cpu": 0.0}
        processes = message["add-processes"]
        self.assertEqual(processes, [expected_process_0])

    def test_generate_cpu_usage(self):
        """
        Test that we can calculate the CPU usage from system information and
        the /proc/<pid>/stat file.
        """
        stat_data = "1 Process S 1 0 0 0 0 0 0 0 " \
                    "0 0 20 20 0 0 0 0 0 0 3000 0 " \
                    "0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0"

        self.builder.create_data(1, self.builder.RUNNING, uid=0, gid=0,
                                 started_after_boot=None,
                                 process_name="Process",
                                 generate_cmd_line=False,
                                 stat_data=stat_data)
        plugin = ActiveProcessInfo(proc_dir=self.sample_dir, uptime=400,
                                   jiffies=10, boot_time=0)
        self.monitor.add(plugin)
        plugin.exchange()
        message = self.mstore.get_pending_messages()[0]
        self.assertEqual(message["type"], "active-process-info")
        self.assertTrue("kill-all-processes" in message)
        self.assertTrue("add-processes" in message)
        processes = message["add-processes"]
        expected_process_0 = {"state": b"R", "gid": 0, "pid": 1,
                              "vm-size": 11676, "name": u"Process",
                              "uid": 0, "start-time": 300,
                              "percent-cpu": 4.00}
        processes = message["add-processes"]
        self.assertEqual(processes, [expected_process_0])

    def test_generate_cpu_usage_capped(self):
        """
        Test that we can calculate the CPU usage from system information and
        the /proc/<pid>/stat file, the CPU usage should be capped at 99%.
        """

        stat_data = "1 Process S 1 0 0 0 0 0 0 0 " \
                    "0 0 500 500 0 0 0 0 0 0 3000 0 " \
                    "0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0"

        self.builder.create_data(1, self.builder.RUNNING, uid=0, gid=0,
                                 started_after_boot=None,
                                 process_name="Process",
                                 generate_cmd_line=False,
                                 stat_data=stat_data)
        plugin = ActiveProcessInfo(proc_dir=self.sample_dir, uptime=400,
                                   jiffies=10, boot_time=0)
        self.monitor.add(plugin)
        plugin.exchange()
        message = self.mstore.get_pending_messages()[0]
        self.assertEqual(message["type"], "active-process-info")
        self.assertTrue("kill-all-processes" in message)
        self.assertTrue("add-processes" in message)
        processes = message["add-processes"]
        expected_process_0 = {"state": b"R", "gid": 0, "pid": 1,
                              "vm-size": 11676, "name": u"Process",
                              "uid": 0, "start-time": 300,
                              "percent-cpu": 99.00}
        processes = message["add-processes"]
        self.assertEqual(processes, [expected_process_0])
