import mock
import os
import unittest

from landscape.lib import testing
from landscape.lib.process import calculate_pcpu, ProcessInformation
from landscape.lib.fs import create_text_file


class ProcessInfoTest(testing.FSTestCase, unittest.TestCase):

    def setUp(self):
        super(ProcessInfoTest, self).setUp()
        self.proc_dir = self.makeDir()

    def _add_process_info(self, process_id, state="R (running)"):
        """Add information about a process.

        The cmdline, status and stat files will be created in the
        process directory, so that get_process_info can get the required
        information.
        """
        process_dir = os.path.join(self.proc_dir, str(process_id))
        os.mkdir(process_dir)

        cmd_line = "/usr/bin/foo"
        create_text_file(os.path.join(process_dir, "cmdline"), cmd_line)

        status = "\n".join([
            "Name: foo",
            "State: %s" % state,
            "Uid: 1000",
            "Gid: 2000",
            "VmSize: 3000",
            "Ignored: value"])
        create_text_file(os.path.join(process_dir, "status"), status)

        stat_array = [str(index) for index in range(44)]
        stat = " ".join(stat_array)
        create_text_file(os.path.join(process_dir, "stat"), stat)

    @mock.patch("landscape.lib.process.detect_jiffies", return_value=1)
    @mock.patch("os.listdir")
    @mock.patch("landscape.lib.sysstats.get_uptime")
    def test_missing_process_race(self, get_uptime_mock, list_dir_mock,
                                  jiffies_mock):
        """
        We use os.listdir("/proc") to get the list of active processes, if a
        process ends before we attempt to read the process' information, then
        this should not trigger an error.
        """

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

        list_dir_mock.return_value = ["12345"]
        get_uptime_mock.return_value = 1.0
        fakefile1 = FakeFile("test-binary")
        fakefile2 = FakeFile(None)
        with mock.patch(
                "landscape.lib.process.open", mock.mock_open(), create=True,
                ) as open_mock:
            # This means "return fakefile1, then fakefile2"
            open_mock.side_effect = [fakefile1, fakefile2]
            process_info = ProcessInformation("/proc")
            processes = list(process_info.get_all_process_info())
            calls = [
                mock.call("/proc/12345/cmdline", "r"),
                mock.call("/proc/12345/status", "r")]
            open_mock.assert_has_calls(calls)
        self.assertEqual(processes, [])
        list_dir_mock.assert_called_with("/proc")
        self.assertTrue(fakefile1.closed)
        self.assertTrue(fakefile2.closed)

    def test_get_process_info_state(self):
        """
        C{get_process_info} reads the process state from the status file
        and uses the first character to represent the process state.
        """
        self._add_process_info(12, state="A (some state)")
        process_info = ProcessInformation(self.proc_dir)
        info = process_info.get_process_info(12)
        self.assertEqual(b"A", info["state"])

    def test_get_process_info_state_preserves_case(self):
        """
        C{get_process_info} retains the case of the process state, since
        for example both x and X can be different states.
        """
        self._add_process_info(12, state="a (some state)")
        process_info = ProcessInformation(self.proc_dir)
        info = process_info.get_process_info(12)
        self.assertEqual(b"a", info["state"])

    def test_get_process_info_state_tracing_stop_lucid(self):
        """
        In Lucid, capital T was used for both stopped and tracing stop.
        From Natty and onwards lowercase t is used for tracing stop, so
        we special-case that state and always return lowercase t for
        tracing stop.
        """
        self._add_process_info(12, state="T (tracing stop)")
        self._add_process_info(13, state="t (tracing stop)")
        process_info = ProcessInformation(self.proc_dir)
        info1 = process_info.get_process_info(12)
        info2 = process_info.get_process_info(12)
        self.assertEqual(b"t", info1["state"])
        self.assertEqual(b"t", info2["state"])


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
