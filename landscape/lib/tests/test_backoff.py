from unittest import mock

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

    def test_error_count_cap(self):
        """Test that the internal error count never exceeds the effective max"""
        backoff_counter = ExponentialBackoff(5, 60)

        # Increase well beyond the effective max
        for _ in range(15):
            backoff_counter.increase()

        self.assertEqual(backoff_counter._error_count, 5)
        self.assertEqual(
            backoff_counter._error_count, backoff_counter._max_effective_error_count
        )

    def test_init_edge_cases(self):
        """Test the max_effective_error_count logic handles edge cases properly"""
        # start_delay is 0
        backoff_zero = ExponentialBackoff(0, 60)
        self.assertEqual(backoff_zero._max_effective_error_count, 1)

        # start_delay is greater than max_delay
        backoff_inverted = ExponentialBackoff(20, 5)
        self.assertEqual(backoff_inverted._max_effective_error_count, 1)

        # start_delay is equal to max_delay
        backoff_equal = ExponentialBackoff(5, 5)
        self.assertEqual(backoff_equal._max_effective_error_count, 1)

    @mock.patch("landscape.lib.backoff.random.random")
    def test_get_random_delay(self, mock_random):
        """Test the random delay calculation boundaries"""
        backoff_counter = ExponentialBackoff(100, 1000)
        backoff_counter.increase()  # Delay is now 100

        # Test the lower bound (random() returns 0.0)
        mock_random.return_value = 0.0
        # For a delay of 100 with 25% stagger, non-random part is 75.
        # 75 + (25 * 0.0) = 75
        self.assertEqual(backoff_counter.get_random_delay(stagger_fraction=0.25), 75)

        # Test the upper bound (random() approaches 1.0 but never reaches it)
        mock_random.return_value = 0.9999
        # 75 + (25 * 0.9999) = 99.9975 (truncated to int)
        self.assertEqual(backoff_counter.get_random_delay(stagger_fraction=0.25), 99)

        # Test the median to ensure standard math is applied correctly
        mock_random.return_value = 0.5
        # 75 + (25 * 0.5) = 87.5 (truncated to int)
        self.assertEqual(backoff_counter.get_random_delay(stagger_fraction=0.25), 87)
