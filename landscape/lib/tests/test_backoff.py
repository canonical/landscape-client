from landscape.client.tests.helpers import LandscapeTest
from landscape.lib.backoff import ExponentialBackoff


class TestBackoff(LandscapeTest):
    def test_increase(self):
        """Test the delay values start correctly and double"""
        backoff_counter = ExponentialBackoff(5, 10)
        backoff_counter.increase()
        self.assertEqual(backoff_counter.get_delay(), 5)
        backoff_counter.increase()
        self.assertEqual(backoff_counter.get_delay(), 10)

    def test_min(self):
        """Test the count and the delay never go below zero"""
        backoff_counter = ExponentialBackoff(1, 5)
        for _ in range(10):
            backoff_counter.decrease()
        self.assertEqual(backoff_counter.get_delay(), 0)
        self.assertEqual(backoff_counter.get_random_delay(), 0)
        self.assertEqual(backoff_counter._error_count, 0)

    def test_max(self):
        """Test the delay never goes above max"""
        backoff_counter = ExponentialBackoff(1, 5)
        for _ in range(10):
            backoff_counter.increase()
        self.assertEqual(backoff_counter.get_delay(), 5)

    def test_decreased_when_maxed(self):
        """Test the delay goes down one step when maxed"""
        backoff_counter = ExponentialBackoff(1, 5)
        for _ in range(10):
            backoff_counter.increase()
        backoff_counter.decrease()
        self.assertTrue(backoff_counter.get_delay() < 5)
