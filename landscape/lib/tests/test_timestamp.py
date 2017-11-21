from datetime import datetime
import unittest

from landscape.lib.timestamp import to_timestamp


class TimestampTest(unittest.TestCase):
    """Test for timestamp conversion function."""

    def test_conversion(self):
        """Test ensures that the conversion returns an int, not a float."""
        date = datetime.utcfromtimestamp(1000)
        timestamp = to_timestamp(date)
        self.assertTrue(isinstance(timestamp, int))
        self.assertEqual(timestamp, 1000)

    def test_before_epoch_conversion(self):
        """Test converting a date before the epoch."""
        date = datetime.utcfromtimestamp(-1000)
        self.assertEqual(to_timestamp(date), -1000)
