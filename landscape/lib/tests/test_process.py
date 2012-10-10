import unittest
import os

from landscape.tests.helpers import LandscapeTest

from landscape.lib.process import calculate_pcpu, ProcessInformation
from landscape.lib.fs import create_file


class ProcessInfoTest(LandscapeTest):

    def setUp(self):
        super(ProcessInfoTest, self).setUp()
        self.proc_dir = self.makeDir()

    def _add_process_info(self, process_id, state="R (running)"):
        process_dir = os.path.join(self.proc_dir, str(process_id))
        os.mkdir(process_dir)

        cmd_line = "/usr/bin/foo"
        create_file(os.path.join(process_dir, "cmdline"), cmd_line)

        status = "\n".join([
            "Name: foo",
            "State: %s" % state,
            "Uid: 1000",
            "Gid: 2000",
            "VmSize: 3000",
            "Ignored: value"])
        create_file(os.path.join(process_dir, "status"), status)

        stat_array = [str(index) for index in range(44)]
        stat = " ".join(stat_array)
        create_file(os.path.join(process_dir, "stat"), stat)

    def test_missing_process_race(self):
        """
        We use os.listdir("/proc") to get the list of active processes, if a
        process ends before we attempt to read the process' information, then
        this should not trigger an error.
        """
        listdir_mock = self.mocker.replace("os.listdir")
        listdir_mock("/proc")
        self.mocker.result(["12345"])

        class FakeFile(object):

            def __init__(self, response=""):
                self._response = response
                self.closed = False

            def readline(self):
                return self._response

            def __iter__(self):
                if self._response is None:
                    raise IOError("Fake file error")
                else:
                    yield self._response

            def close(self):
                self.closed = True

        open_mock = self.mocker.replace("__builtin__.open")
        open_mock("/proc/12345/cmdline", "r")
        fakefile1 = FakeFile("test-binary")
        self.mocker.result(fakefile1)

        open_mock("/proc/12345/status", "r")
        fakefile2 = FakeFile(None)
        self.mocker.result(fakefile2)

        self.mocker.replay()

        process_info = ProcessInformation("/proc")
        processes = list(process_info.get_all_process_info())
        self.assertEqual(processes, [])
        self.assertTrue(fakefile1.closed)
        self.assertTrue(fakefile2.closed)

    def test_get_process_info_state_running(self):
        self._add_process_info(12, state="R (running)")
        process_info = ProcessInformation(self.proc_dir)
        info = process_info.get_process_info(12)
        self.assertEqual("R", info["state"])

    def test_get_process_info_state_disk_sleep(self):
        self._add_process_info(12, state="D (disk sleep)")
        process_info = ProcessInformation(self.proc_dir)
        info = process_info.get_process_info(12)
        self.assertEqual("D", info["state"])

    def test_get_process_info_state_sleeping(self):
        self._add_process_info(12, state="S (sleeping)")
        process_info = ProcessInformation(self.proc_dir)
        info = process_info.get_process_info(12)
        self.assertEqual("S", info["state"])

    def test_get_process_info_state_stopped(self):
        self._add_process_info(12, state="T (stopped)")
        process_info = ProcessInformation(self.proc_dir)
        info = process_info.get_process_info(12)
        self.assertEqual("T", info["state"])

    def test_get_process_info_state_tracing_stop_lucid(self):
        self._add_process_info(12, state="T (tracing stop)")
        process_info = ProcessInformation(self.proc_dir)
        info = process_info.get_process_info(12)
        self.assertEqual("t", info["state"])

    def test_get_process_info_state_tracing_stop(self):
        self._add_process_info(12, state="t (tracing stop)")
        process_info = ProcessInformation(self.proc_dir)
        info = process_info.get_process_info(12)
        self.assertEqual("t", info["state"])

    def test_get_process_info_state_dead(self):
        self._add_process_info(12, state="X (dead)")
        process_info = ProcessInformation(self.proc_dir)
        info = process_info.get_process_info(12)
        self.assertEqual("X", info["state"])

    def test_get_process_info_state_zombie(self):
        self._add_process_info(12, state="Z (zombie)")
        process_info = ProcessInformation(self.proc_dir)
        info = process_info.get_process_info(12)
        self.assertEqual("Z", info["state"])

    def test_get_process_info_state_new(self):
        self._add_process_info(12, state="N (new state)")
        process_info = ProcessInformation(self.proc_dir)
        info = process_info.get_process_info(12)
        self.assertEqual("N", info["state"])


class CalculatePCPUTest(unittest.TestCase):

    """
    calculate_pcpu is lifted directly from procps/ps/output.c (it's called
    "pcpu" in there).

    What it actually does is...

    The result is "number of jiffies allocated to the process / number of
    jiffies the process has been running".

    How the jiffies are allocated to the process is CPU agnostic, and my
    reading of the percentage capping is to prevent something like...

    jiffies allocated on CPU #1 600, jiffies allocated on CPU #2 600 = 1200
    Jiffies allocated to a process that's only been running for 1000 jiffies

    So, that would look wrong, but is entirely plausible.
    """

    def test_calculate_pcpu_real_data(self):
        self.assertEqual(
            calculate_pcpu(51286, 5000, 19000.07, 9281.0, 100), 3.0)

    def test_calculate_pcpu(self):
        """
        This calculates the pcpu based on 10000 jiffies allocated to a process
        over 50000 jiffies.

        This should be cpu utilisation of 20%
        """
        self.assertEqual(calculate_pcpu(8000, 2000, 1000, 50000, 100),
                         20.0)

    def test_calculate_pcpu_capped(self):
        """
        This calculates the pcpu based on 100000 jiffies allocated to a process
        over 50000 jiffies.

        This should be cpu utilisation of 200% but capped at 99% CPU
        utilisation.
        """
        self.assertEqual(calculate_pcpu(98000, 2000, 1000, 50000, 100),
                         99.0)

    def test_calculate_pcpu_floored(self):
        """
        This calculates the pcpu based on 1 jiffies allocated to a process
        over 80 jiffies this should be negative, but floored to 0.0.
        """
        self.assertEqual(calculate_pcpu(1, 0, 50, 800, 10), 0.0)
