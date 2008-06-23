import unittest

from landscape.tests.helpers import LandscapeTest

from landscape.lib.process import calculate_pcpu


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
