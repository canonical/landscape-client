import unittest

from landscape.tests.helpers import LandscapeTest

from landscape.lib.process import calculate_pcpu, ProcessInformation


class ProcessInfoTest(LandscapeTest):

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

            def readline(self):
                return self._response

            def __iter__(self):
                if self._response is None:
                    raise IOError("Fake file error")
                else:
                    yield self._response

            def close(self):
                pass

        open_mock = self.mocker.replace("__builtin__.open")
        open_mock("/proc/12345/cmdline", "r")
        self.mocker.result(FakeFile("test-binary"))

        open_mock("/proc/12345/status", "r")
        self.mocker.result(FakeFile(None))

        self.mocker.replay()

        process_info = ProcessInformation("/proc")
        processes = list(process_info.get_all_process_info())


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
        self.assertEquals(
            calculate_pcpu(51286, 5000, 19000.07, 9281.0, 100), 3.0)

    def test_calculate_pcpu(self):
        """
        This calculates the pcpu based on 10000 jiffies allocated to a process
        over 50000 jiffies.

        This should be cpu utilisation of 20%
        """
        self.assertEquals(calculate_pcpu(8000, 2000, 1000, 50000, 100),
                          20.0)

    def test_calculate_pcpu_capped(self):
        """
        This calculates the pcpu based on 100000 jiffies allocated to a process
        over 50000 jiffies.

        This should be cpu utilisation of 200% but capped at 99% CPU
        utilisation.
        """
        self.assertEquals(calculate_pcpu(98000, 2000, 1000, 50000, 100),
                          99.0)

    def test_calculate_pcpu_floored(self):
        """
        This calculates the pcpu based on 1 jiffies allocated to a process
        over 80 jiffies this should be negative, but floored to 0.0.
        """
        self.assertEquals(calculate_pcpu(1, 0, 50, 800, 10), 0.0)
