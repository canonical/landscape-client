import operator
import os
import shutil
import tempfile
import subprocess

from twisted.internet.defer import fail

from landscape import API
from landscape.monitor.activeprocessinfo import ActiveProcessInfo
from landscape.monitor.computeruptime import BootTimes
from landscape.tests.helpers import (LandscapeTest, MakePathHelper,
                                     MonitorHelper)
from landscape.tests.mocker import ANY
from landscape.monitor.tests.test_computeruptime import append_login_data


class SampleDataBuilder(object):
    """Builder creates sample data for the process info plugin to consume."""

    RUNNING = "R (running)"
    STOPPED = "T (stopped)"
    TRACING_STOP = "T (tracing stop)"
    DISK_SLEEP = "D (disk sleep)"
    SLEEPING = "S (sleeping)"
    DEAD = "X (dead)"
    ZOMBIE = "Z (zombie)"

    def __init__(self, sample_dir):
        """Initialize factory with directory for sample data."""
        self._sample_dir = sample_dir

    def create_data(self, process_id, state, uid, gid,
                    started_after_uptime, process_name=None,
                    generate_cmd_line=True, stat_data=None):
        """Creates sample data for a process.

        @param started_after_uptime: The amount of time, in jiffies,
        between the system uptime and start of the process.
        @param process_name: Used to generate the process name that appears in
        /proc/%(pid)s/status
        @param generate_cmd_line: If true, place the process_name in
        /proc/%(pid)s/cmdline, otherwise leave it empty (this simulates a
        kernel process)
        """
        sample_data = """
Name:   %(process_name)s
State:  %(state)s
SleepAVG:       87%%
Tgid:   24759
Pid:    24759
PPid:   17238
TracerPid:      0
Uid:    %(uid)d    0    0    0
Gid:    %(gid)d    0    0    0
FDSize: 256
Groups: 4 20 24 25 29 30 44 46 106 110 112 1000
VmPeak:    11680 kB
VmSize:    11676 kB
VmLck:         0 kB
VmHWM:      6928 kB
VmRSS:      6924 kB
VmData:     1636 kB
VmStk:       196 kB
VmExe:      1332 kB
VmLib:      4240 kB
VmPTE:        20 kB
Threads:        1
SigQ:   0/4294967295
SigPnd: 0000000000000000
ShdPnd: 0000000000000000
SigBlk: 0000000000000000
SigIgn: 0000000000000000
SigCgt: 0000000059816eff
CapInh: 0000000000000000
CapPrm: 0000000000000000
CapEff: 0000000000000000
""" % ({"process_name": process_name[:15], "state": state, "uid": uid,
        "gid": gid,})
        process_dir = os.path.join(self._sample_dir, str(process_id))
        os.mkdir(process_dir)
        filename = os.path.join(process_dir, "status")

        file = open(filename, "w+")
        try:
            file.write(sample_data)
        finally:
            file.close()
        if stat_data is None:
            stat_data = """\
0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 %d\
""" % (started_after_uptime,)
        filename = os.path.join(process_dir, "stat")

        file = open(filename, "w+")
        try:
            file.write(stat_data)
        finally:
            file.close()

        if generate_cmd_line:
            sample_data = """\
/usr/sbin/%(process_name)s\0--pid-file\0/var/run/%(process_name)s.pid\0
""" % {"process_name": process_name}
        else:
            sample_data = ""
        filename = os.path.join(process_dir, "cmdline")

        file = open(filename, "w+")
        try:
            file.write(sample_data)
        finally:
            file.close()

    def remove_data(self, process_id):
        """Remove sample data for the process that matches C{process_id}."""
        process_dir = os.path.join(self._sample_dir, str(process_id))
        shutil.rmtree(process_dir)


class ActiveProcessInfoTest(LandscapeTest):
    """Active process info plugin tests."""

    helpers = [MonitorHelper, MakePathHelper]

    def setUp(self):
        """Initialize helpers and sample data builder."""
        LandscapeTest.setUp(self)
        self.sample_dir = tempfile.mkdtemp()
        self.builder = SampleDataBuilder(self.sample_dir)
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
        self.assertEquals(message["type"], "active-process-info")
        self.assertTrue("kill-all-processes" in message)
        self.assertEquals(message["kill-all-processes"], True)
        self.assertTrue("add-processes" in message)

    def test_only_first_run_includes_kill_message(self):
        """Test ensures that only the first run queues a kill message."""
        self.builder.create_data(672, self.builder.TRACING_STOP,
                                 uid=1000, gid=1000, started_after_uptime=10,
                                 process_name="blarpy")

        plugin = ActiveProcessInfo(proc_dir=self.sample_dir, uptime=10)
        self.monitor.add(plugin)
        plugin.exchange()

        self.builder.create_data(671, self.builder.STOPPED, uid=1000,
                                 gid=1000, started_after_uptime=15,
                                 process_name="blargh")

        plugin.exchange()
        messages = self.mstore.get_pending_messages()
        self.assertEquals(len(messages), 2)
        message = messages[0]
        self.assertEquals(message["type"], "active-process-info")
        self.assertTrue("kill-all-processes" in message)
        self.assertTrue("add-processes" in message)

        message = messages[1]
        self.assertEquals(message["type"], "active-process-info")
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
                                 started_after_uptime=30, process_name="init")
        self.builder.create_data(671, self.builder.STOPPED, uid=1000,
                                 gid=1000, started_after_uptime=110,
                                 process_name="blargh")
        self.builder.create_data(672, self.builder.TRACING_STOP,
                                 uid=1000, gid=1000, started_after_uptime=120,
                                 process_name="blarpy")

        plugin = ActiveProcessInfo(proc_dir=self.sample_dir, uptime=100,
                                   jiffies=10)
        self.monitor.add(plugin)
        plugin.exchange()
        message = self.mstore.get_pending_messages()[0]
        self.assertEquals(message["type"], "active-process-info")
        self.assertTrue("kill-all-processes" in message)
        self.assertTrue("add-processes" in message)
        expected_process_0 = {"state": "R", "gid": 0, "pid": 1,
                              "vm-size": 11676, "name": "init", "uid": 0,
                              "start-time": 103, "percent-cpu": 0.0}
        expected_process_1 = {"state": "T", "gid": 1000, "pid": 671,
                              "vm-size": 11676, "name": "blargh", "uid": 1000,
                              "start-time": 111, "percent-cpu": 0.0}
        expected_process_2 = {"state": "I", "gid": 1000, "pid": 672,
                              "vm-size": 11676, "name": "blarpy", "uid": 1000,
                              "start-time": 112, "percent-cpu": 0.0}
        processes = message["add-processes"]
        processes.sort(key=operator.itemgetter("pid"))
        self.assertEquals(processes, [expected_process_0, expected_process_1,
                                      expected_process_2])

    def test_skip_non_numeric_subdirs(self):
        """Test ensures the plugin doesn't touch non-process dirs in /proc."""
        self.builder.create_data(1, self.builder.RUNNING, uid=0, gid=0,
                                 started_after_uptime=120, process_name="init")

        directory = os.path.join(self.sample_dir, "acpi")
        os.mkdir(directory)
        self.assertTrue(os.path.isdir(directory))

        plugin = ActiveProcessInfo(proc_dir=self.sample_dir, uptime=100,
                                   jiffies=10)
        self.monitor.add(plugin)
        plugin.exchange()
        message = self.mstore.get_pending_messages()[0]
        self.assertEquals(message["type"], "active-process-info")
        self.assertTrue("kill-all-processes" in message)
        self.assertTrue("add-processes" in message)

        expected_process = {"pid": 1, "state": "R", "name": "init",
                            "vm-size": 11676, "uid": 0, "gid": 0,
                            "start-time": 112, "percent-cpu": 0.0}
        self.assertEquals(message["add-processes"], [expected_process])

    def test_plugin_manager(self):
        """Test plugin manager integration."""
        self.builder.create_data(1, self.builder.RUNNING, uid=0, gid=0,
                                 started_after_uptime=100, process_name="init")

        plugin = ActiveProcessInfo(proc_dir=self.sample_dir, uptime=100,
                                   jiffies=10)
        self.monitor.add(plugin)
        self.monitor.exchange()

        self.assertMessages(
            self.mstore.get_pending_messages(),
            [{"type": "active-process-info",
              "kill-all-processes": True,
              "add-processes": [{"pid": 1, "state": "R", "name": "init",
                                 "vm-size": 11676, "uid": 0, "gid": 0,
                                 "start-time": 110, "percent-cpu": 0.0}]}])


    def test_process_terminated(self):
        """Test that the plugin handles process changes in a diff-like way."""
        # This test is *too big*
        self.builder.create_data(1, self.builder.RUNNING, uid=0, gid=0,
                                 started_after_uptime=10, process_name="init")
        self.builder.create_data(671, self.builder.STOPPED, uid=1000,
                                 gid=1000, started_after_uptime=20,
                                 process_name="blargh")
        self.builder.create_data(672, self.builder.TRACING_STOP,
                                 uid=1000, gid=1000, started_after_uptime=40,
                                 process_name="blarpy")

        plugin = ActiveProcessInfo(proc_dir=self.sample_dir, uptime=100,
                                   jiffies=10)
        self.monitor.add(plugin)
        plugin.exchange()

        # Terminate a process and start another.
        self.builder.remove_data(671)
        self.builder.create_data(12753, self.builder.RUNNING,
                                 uid=0, gid=0, started_after_uptime=70,
                                 process_name="wubble")

        plugin.exchange()
        messages = self.mstore.get_pending_messages()
        self.assertEquals(len(messages), 2)

        # The first time the plugin runs we expect all known processes
        # to be killed.
        message = messages[0]
        self.assertEquals(message["type"], "active-process-info")
        self.assertTrue("kill-all-processes" in message)
        self.assertEquals(message["kill-all-processes"], True)
        self.assertTrue("add-processes" in message)
        expected_process_0 = {"state": "R", "gid": 0, "pid": 1,
                              "vm-size": 11676, "name": "init", 
                              "uid": 0, "start-time": 101,
                              "percent-cpu": 0.0}
        expected_process_1 = {"state": "T", "gid": 1000, "pid": 671,
                              "vm-size": 11676, "name": "blargh", 
                              "uid": 1000, "start-time": 102,
                              "percent-cpu": 0.0}
        expected_process_2 = {"state": "I", "gid": 1000, "pid": 672,
                              "vm-size": 11676, "name": "blarpy", 
                              "uid": 1000, "start-time": 104,
                              "percent-cpu": 0.0}
        processes = message["add-processes"]
        processes.sort(key=operator.itemgetter("pid"))
        self.assertEquals(processes, [expected_process_0, expected_process_1,
                                      expected_process_2])

        # Report diff-like changes to processes, such as terminated
        # processes and new processes.
        message = messages[1]
        self.assertEquals(message["type"], "active-process-info")

        self.assertTrue("add-processes" in message)
        self.assertEquals(len(message["add-processes"]), 1)
        expected_process = {"state": "R", "gid": 0, "pid": 12753,
                            "vm-size": 11676, "name": "wubble",
                            "uid": 0, "start-time": 107,
                            "percent-cpu": 0.0}
        self.assertEquals(message["add-processes"], [expected_process])

        self.assertTrue("kill-processes" in message)
        self.assertEquals(len(message["kill-processes"]), 1)
        self.assertEquals(message["kill-processes"], [671])

    def test_only_queue_message_when_process_data_is_available(self):
        """Test ensures that messages are only queued when data changes."""
        self.builder.create_data(672, self.builder.TRACING_STOP,
                                 uid=1000, gid=1000, started_after_uptime=10,
                                 process_name="blarpy")

        plugin = ActiveProcessInfo(proc_dir=self.sample_dir, uptime=10)
        self.monitor.add(plugin)

        plugin.exchange()
        self.assertEquals(len(self.mstore.get_pending_messages()), 1)

        plugin.exchange()
        self.assertEquals(len(self.mstore.get_pending_messages()), 1)

    def test_only_report_active_processes(self):
        """Test ensures the plugin only reports active processes."""
        self.builder.create_data(672, self.builder.DEAD,
                                 uid=1000, gid=1000, started_after_uptime=10,
                                 process_name="blarpy")
        self.builder.create_data(673, self.builder.ZOMBIE,
                                 uid=1000, gid=1000, started_after_uptime=12,
                                 process_name="blarpitty")
        self.builder.create_data(674, self.builder.RUNNING,
                                 uid=1000, gid=1000, started_after_uptime=13,
                                 process_name="blarpie")
        self.builder.create_data(675, self.builder.STOPPED,
                                 uid=1000, gid=1000, started_after_uptime=14,
                                 process_name="blarping")
        self.builder.create_data(676, self.builder.TRACING_STOP,
                                 uid=1000, gid=1000, started_after_uptime=15,
                                 process_name="floerp")
        self.builder.create_data(677, self.builder.DISK_SLEEP,
                                 uid=1000, gid=1000, started_after_uptime=18,
                                 process_name="floerpidity")
        self.builder.create_data(678, self.builder.SLEEPING,
                                 uid=1000, gid=1000, started_after_uptime=21,
                                 process_name="floerpiditting")

        plugin = ActiveProcessInfo(proc_dir=self.sample_dir, uptime=10)
        self.monitor.add(plugin)

        plugin.exchange()
        messages = self.mstore.get_pending_messages()
        self.assertEquals(len(messages), 1)

        message = messages[0]
        self.assertTrue("kill-all-processes" in message)
        self.assertTrue("kill-processes" not in message)
        self.assertTrue("add-processes" in message)

        pids = [process["pid"] for process in message["add-processes"]]
        pids.sort()
        self.assertEquals(pids, [673, 674, 675, 676, 677, 678])

    def test_report_interesting_state_changes(self):
        """Test ensures that interesting state changes are reported."""
        self.builder.create_data(672, self.builder.RUNNING,
                                 uid=1000, gid=1000, started_after_uptime=10,
                                 process_name="blarpy")

        # Report a running process.
        plugin = ActiveProcessInfo(proc_dir=self.sample_dir, uptime=10)
        self.monitor.add(plugin)

        plugin.exchange()

        messages = self.mstore.get_pending_messages()
        self.assertEquals(len(messages), 1)
        message = messages[0]

        self.assertTrue("kill-all-processes" in message)
        self.assertTrue("kill-processes" not in message)
        self.assertTrue("add-processes" in message)
        self.assertEquals(message["add-processes"][0]["pid"], 672)

        # Convert the process to a zombie and ensure it gets reported.
        self.builder.remove_data(672)
        self.builder.create_data(672, self.builder.ZOMBIE,
                                 uid=1000, gid=1000, started_after_uptime=10,
                                 process_name="blarpy")

        plugin.exchange()

        messages = self.mstore.get_pending_messages()
        self.assertEquals(len(messages), 2)
        message = messages[1]

        self.assertTrue("kill-all-processes" not in message)
        self.assertTrue("kill-processes" in message)
        self.assertTrue("add-processes" in message)
        self.assertEquals(message["kill-processes"], [672])
        self.assertEquals(message["add-processes"][0]["pid"], 672)

    def test_get_last_boot_time_from_computer_uptime_plugin(self):
        """
        The Active process info fetches the real last boot time to calculate
        the start time of a process.
        """
        wtmp_filename = self.make_path("")
        append_login_data(wtmp_filename, tty_device="~", username="reboot",
                          entry_time_seconds=3212)

        self.builder.create_data(672, self.builder.RUNNING,
                                 uid=1000, gid=1000, started_after_uptime=10,
                                 process_name="blarpy")
        plugin = ActiveProcessInfo(proc_dir=self.sample_dir, jiffies=1)
        self.monitor.add(plugin)

        plugin.exchange()

        messages = self.mstore.get_pending_messages()
        self.assertEquals(len(messages), 1)
        message = self.mstore.get_pending_messages()[0]

        boot_time = BootTimes()
        last_boot_time = boot_time.get_last_boot_time()

        self.assertTrue("kill-all-processes" in message)
        self.assertTrue("kill-processes" not in message)
        self.assertTrue("add-processes" in message)
        self.assertEquals(message["add-processes"][0]["pid"], 672)
        self.assertEquals(message["add-processes"][0]["start-time"],
                          last_boot_time + 10)

    def test_no_last_boot_time(self):
        """
        When no boot time is available, the plugin will not report new
        processes.
        """
        wtmp_filename = self.make_path("")
        append_login_data(wtmp_filename, tty_device="~", username="reboot",
                          entry_time_seconds=3212)
        self.builder.create_data(672, self.builder.RUNNING,
                                 uid=1000, gid=1000, started_after_uptime=10,
                                 process_name="blarpy")

        ## Mock out boot times
        boot_times_factory = self.mocker.replace(
            "landscape.monitor.computeruptime.BootTimes", passthrough=False)
        boot_times_factory().get_last_boot_time()
        self.mocker.result(None)
        self.mocker.replay()
        plugin = ActiveProcessInfo(proc_dir=self.sample_dir, jiffies=1)
        self.monitor.add(plugin)

        # We don't expect anything except the standard "kill all known
        # processes" in the first message.
        plugin.exchange()

        messages = self.mstore.get_pending_messages()
        self.assertEquals(messages,
                          [{"api": API, "kill-all-processes": True,
                            "timestamp": 0, "type": "active-process-info"}])
        message = self.mstore.get_pending_messages()[0]

        self.assertEquals(message["type"], "active-process-info")
        self.assertTrue("kill-all-processes" in message)
        self.assertTrue("kill-processes" not in message)
        self.assertTrue("add-processes" not in message)

        # Without an uptime we can't generate start times for
        # processes, so we don't report anything.
        plugin.exchange()
        messages = self.mstore.get_pending_messages()
        self.assertEquals(messages,
                          [{"api": API, "kill-all-processes": True,
                            "timestamp": 0, "type": "active-process-info"}])

    def test_call_on_accepted(self):
        """
        L{MonitorPlugin}-based plugins can provide a callable to call
        when a message type becomes accepted.
        """
        plugin = ActiveProcessInfo(proc_dir=self.sample_dir, uptime=100,
                                   jiffies=10)
        self.monitor.add(plugin)
        self.assertEquals(len(self.mstore.get_pending_messages()), 0)
        self.broker_service.reactor.fire(("message-type-acceptance-changed",
                                          "active-process-info"), True)
        self.assertEquals(len(self.mstore.get_pending_messages()), 1)

    def test_resynchronize_event(self):
        """
        When a C{resynchronize} event occurs we should clear the information
        held in memory by the activeprocess monitor.
        """
        self.builder.create_data(1, self.builder.RUNNING, uid=0, gid=0,
                                 started_after_uptime=30, process_name="init")
        self.builder.create_data(671, self.builder.STOPPED, uid=1000,
                                 gid=1000, started_after_uptime=110,
                                 process_name="blargh")
        self.builder.create_data(672, self.builder.TRACING_STOP,
                                 uid=1000, gid=1000, started_after_uptime=120,
                                 process_name="blarpy")

        plugin = ActiveProcessInfo(proc_dir=self.sample_dir, uptime=100,
                                   jiffies=10)
        self.monitor.add(plugin)

        plugin.exchange()
        messages = self.mstore.get_pending_messages()

        expected_messages = [{"add-processes": [
                               {"gid": 1000,
                                "name": u"blarpy",
                                "pid": 672,
                                "start-time": 112,
                                "state": "I",
                                "uid": 1000,
                                "vm-size": 11676,
                                "percent-cpu": 0.0},
                               {"gid": 0,
                                "name": u"init",
                                "pid": 1,
                                "start-time": 103,
                                "state": "R",
                                "uid": 0,
                                "vm-size": 11676,
                                "percent-cpu": 0.0},
                               {"gid": 1000,
                                "name": u"blargh",
                                "pid": 671,
                                "start-time": 111,
                                "state": "T",
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


    def test_do_not_persist_changes_when_send_message_fails(self):
        """
        When the plugin is run it persists data that it uses on
        subsequent checks to calculate the delta to send.  It should
        only persist data when the broker confirms that the message
        sent by the plugin has been sent.
        """
        class MyException(Exception): pass
        self.log_helper.ignore_errors(MyException)

        self.builder.create_data(672, self.builder.RUNNING,
                                 uid=1000, gid=1000, started_after_uptime=10,
                                 process_name="python")
        plugin = ActiveProcessInfo(proc_dir=self.sample_dir, uptime=10)
        self.monitor.add(plugin)

        broker_mock = self.mocker.replace(self.monitor.broker)
        broker_mock.send_message(ANY, urgent=ANY)
        self.mocker.result(fail(MyException()))
        self.mocker.replay()

        message = plugin.get_message()

        def assert_message(message_id):
            self.assertEquals(message, plugin.get_message())

        result = plugin.exchange()
        result.addCallback(assert_message)
        return result


class PluginManagerIntegrationTest(LandscapeTest):

    helpers = [MonitorHelper, MakePathHelper]

    def setUp(self):
        LandscapeTest.setUp(self)
        self.sample_dir = self.make_dir()
        self.builder = SampleDataBuilder(self.sample_dir)
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
                                 started_after_uptime=30,
                                 process_name="NetworkManagerDaemon")

        plugin = ActiveProcessInfo(proc_dir=self.sample_dir, uptime=100,
                                   jiffies=10)
        self.monitor.add(plugin)
        plugin.exchange()
        message = self.mstore.get_pending_messages()[0]
        self.assertEquals(message["type"], "active-process-info")
        self.assertTrue("kill-all-processes" in message)
        self.assertTrue("add-processes" in message)
        expected_process_0 = {"state": "R", "gid": 0, "pid": 1,
                              "vm-size": 11676, "name": "NetworkManagerDaemon",
                              "uid": 0, "start-time": 103, "percent-cpu": 0.0}
        processes = message["add-processes"]
        self.assertEquals(processes, [expected_process_0])

    def test_strip_command_line_name_whitespace(self):
        """Whitespace should be stripped from command-line names."""
        self.builder.create_data(1, self.builder.RUNNING, uid=0, gid=0,
                                 started_after_uptime=30,
                                 process_name=" postgres: writer process     ")
        plugin = ActiveProcessInfo(proc_dir=self.sample_dir, uptime=100,
                                   jiffies=10)
        self.monitor.add(plugin)
        plugin.exchange()
        message = self.mstore.get_pending_messages()[0]
        self.assertEquals(message["add-processes"][0]["name"],
                          u"postgres: writer process")

    def test_read_process_with_no_cmdline(self):
        """Test reading a process without a cmdline file."""
        self.builder.create_data(1, self.builder.RUNNING, uid=0, gid=0,
                                 started_after_uptime=30,
                                 process_name="ProcessWithLongName",
                                 generate_cmd_line=False)

        plugin = ActiveProcessInfo(proc_dir=self.sample_dir, uptime=100,
                                   jiffies=10)
        self.monitor.add(plugin)
        plugin.exchange()
        message = self.mstore.get_pending_messages()[0]
        self.assertEquals(message["type"], "active-process-info")
        self.assertTrue("kill-all-processes" in message)
        self.assertTrue("add-processes" in message)
        expected_process_0 = {"state": "R", "gid": 0, "pid": 1,
                              "vm-size": 11676, "name": "ProcessWithLong",
                              "uid": 0, "start-time": 103, "percent-cpu": 0.0}
        processes = message["add-processes"]
        self.assertEquals(processes, [expected_process_0])

    def test_generate_cpu_usage(self):
        stat_data = "1 Process S 1 0 0 0 0 0 0 0 " \
                    "0 0 2375 0 0 0 0 0 0 10 0 0 " \
                    "0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0"

        self.builder.create_data(1, self.builder.RUNNING, uid=0, gid=0,
                                 started_after_uptime=30,
                                 process_name="Process",
                                 generate_cmd_line=False,
                                 stat_data=stat_data)
        plugin = ActiveProcessInfo(proc_dir=self.sample_dir, uptime=10,
                                   jiffies=10)
        self.monitor.add(plugin)
        plugin.exchange()
        message = self.mstore.get_pending_messages()[0]
        self.assertEquals(message["type"], "active-process-info")
        self.assertTrue("kill-all-processes" in message)
        self.assertTrue("add-processes" in message)
        processes = message["add-processes"]
        expected_process_0 = {"state": "R", "gid": 0, "pid": 1,
                              "vm-size": 11676, "name": u"Process",
                              "uid": 0, "start-time": 10,
                              "percent-cpu": 1.00}
        processes = message["add-processes"]
        self.assertEquals(processes, [expected_process_0])

    def test_generate_cpu_usage_capped(self):
        stat_data = "1 Process S 1 0 0 0 0 0 0 0 " \
                    "0 0 290000 0 0 0 0 0 0 0 10 0 0 " \
                    "0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0"

        self.builder.create_data(1, self.builder.RUNNING, uid=0, gid=0,
                                 started_after_uptime=30,
                                 process_name="Process",
                                 generate_cmd_line=False,
                                 stat_data=stat_data)
        plugin = ActiveProcessInfo(proc_dir=self.sample_dir, uptime=10,
                                   jiffies=10)
        self.monitor.add(plugin)
        plugin.exchange()
        message = self.mstore.get_pending_messages()[0]
        self.assertEquals(message["type"], "active-process-info")
        self.assertTrue("kill-all-processes" in message)
        self.assertTrue("add-processes" in message)
        processes = message["add-processes"]
        expected_process_0 = {"state": "R", "gid": 0, "pid": 1,
                              "vm-size": 11676, "name": "Process",
                              "uid": 0, "start-time": 11,
                              "percent-cpu": 99.00}
        processes = message["add-processes"]
        self.assertEquals(processes, [expected_process_0])
