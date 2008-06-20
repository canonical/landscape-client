import unittest

from landscape.tests.helpers import LandscapeTest

from landscape.lib.process import get_uptime, calculate_pcpu


class UptimeTest(LandscapeTest):
    """Test for parsing /proc/uptime data."""

    def test_valid_uptime_file(self):
        """Test ensures that we can read a valid /proc/uptime file."""
        proc_file = self.make_path("17608.24 16179.25")
        self.assertEquals("%0.2f" % get_uptime(proc_file),
                          "17608.24")

class CalculatePCPUTest(unittest.TestCase):

    def test_calculate_pcpu_real_data(self):
        self.assertEquals(
            calculate_pcpu(51286, 5000, 4, 9, 19000.07, 9281.0, 100), 3.0)

    def test_calculate_pcpu(self):
        """
        This calculates the pcpu based on 10000 jiffies allocated to a process
        over 50000 jiffies.

        This should be cpu utilisation of 20%
        """
        self.assertEquals(calculate_pcpu(8000, 2000, 0, 0, 1000, 50000, 100),
                          20.0)

    def test_calculate_pcpu_capped(self):
        """
        This calculates the pcpu based on 100000 jiffies allocated to a process
        over 50000 jiffies.

        This should be cpu utilisation of 200% but capped at 99% CPU
        utilisation.
        """
        self.assertEquals(calculate_pcpu(98000, 2000, 0, 0, 1000, 50000, 100),
                          99.0)

    def test_calculate_pcpu_floored(self):
        """
        This calculates the pcpu based on 1 jiffies allocated to a process
        over 80 jiffies this should be negative, but floored to 0.0.
        """
        self.assertEquals(calculate_pcpu(1, 0, 0, 0, 50, 800, 10), 0.0)
