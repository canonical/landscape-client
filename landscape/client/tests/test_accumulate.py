from landscape.lib.persist import Persist
from landscape.client.accumulate import Accumulator, accumulate
from landscape.client.tests.helpers import LandscapeTest


class AccumulateTest(LandscapeTest):
    """Test for the accumulate function that implements accumulation logic."""

    def test_accumulate(self):
        """
        step:    0              5
               --|--+--+--+--+--|--
        value:   0              4
        """
        accumulated_value, step_data = accumulate(0, 0, 5, 4, 5)
        self.assertEqual(accumulated_value, 0)
        self.assertEqual(step_data, (5, 4))

    def test_accumulate_non_zero_accumulated_value(self):
        """
        step:    5              10             15
               --|--+--+--+--+--|--+--+--+--+--|--
        value:         4                 3
        """
        accumulated_value, step_data = accumulate(7, 8, 13, 3, 5)
        self.assertEqual(accumulated_value, 9)
        self.assertEqual(step_data, (10, float((2 * 4) + (3 * 3)) / 5))

    def test_accumulate_skipped_step(self):
        """
        step:    0              5              10             15
               --|--+--+--+--+--|--+--+--+--+--|--+--+--+--+--|--
        value:   0                                   4
        """
        accumulated_value, step_data = accumulate(0, 0, 12, 4, 5)
        self.assertEqual(accumulated_value, 8)
        self.assertEqual(step_data, None)

    def test_accumulate_within_step(self):
        """
        step:    0              5
               --|--+--+--+--+--|--
        value:   0     4
        """
        accumulated_value, step_data = accumulate(0, 0, 2, 4, 5)
        self.assertEqual(accumulated_value, 8)
        self.assertEqual(step_data, None)

    def test_accumulate_within_step_with_nonzero_start_accumulated_value(self):
        """
        step:    0              5
               --|--+--+--+--+--|--
        value:   0     3     4
        """
        accumulated_value, step_data = accumulate(2, 6, 4, 4, 5)
        self.assertEqual(accumulated_value, 14)
        self.assertEqual(step_data, None)

    def test_accumulate_with_first_value_on_step_boundary(self):
        """
        step:    0              5
               --|--+--+--+--+--|--
        value:   14
        """
        accumulated_value, step_data = accumulate(0, 0, 0, 14, 5)
        self.assertEqual(accumulated_value, 0)
        self.assertEqual(step_data, None)


class AccumulatorTest(LandscapeTest):
    """Tests for the Accumulator plugin helper class."""

    def test_accumulate(self):
        """
        step:    0              5
               --|--+--+--+--+--|--
        value:   0              4
        """
        persist = Persist()
        accumulate = Accumulator(persist, 5)

        self.assertEqual(persist.get("key"), None)
        step_data = accumulate(5, 4, "key")
        self.assertEqual(step_data, (5, 4))
        self.assertEqual(persist.get("key"), (5, 0))

    def test_accumulate_non_zero_accumulated_value(self):
        """
        step:    5              10             15
               --|--+--+--+--+--|--+--+--+--+--|--
        value:         4                 3
        """
        persist = Persist()
        accumulate = Accumulator(persist, 5)

        # Persist data that would have been stored when
        # accumulate(7, 4, "key") was called.
        persist.set("key", (7, 8))
        step_data = accumulate(13, 3, "key")
        self.assertEqual(step_data, (10, float((2 * 4) + (3 * 3)) / 5))
        self.assertEqual(persist.get("key"), (13, 9))

    def test_accumulate_skipped_step(self):
        """
        step:    0              5              10             15
               --|--+--+--+--+--|--+--+--+--+--|--+--+--+--+--|--
        value:   0                                   4
        """
        persist = Persist()
        accumulate = Accumulator(persist, 5)

        self.assertEqual(persist.get("key"), None)
        step_data = accumulate(12, 4, "key")
        self.assertEqual(step_data, None)
        self.assertEqual(persist.get("key"), (12, 8))

    def test_accumulate_within_step(self):
        """
        step:    0              5
               --|--+--+--+--+--|--
        value:   0     4
        """
        persist = Persist()
        accumulate = Accumulator(persist, 5)

        self.assertEqual(persist.get("key"), None)
        step_data = accumulate(2, 4, "key")
        self.assertEqual(step_data, None)
        self.assertEqual(persist.get("key"), (2, 8))

    def test_accumulate_within_step_with_nonzero_start_accumulated_value(self):
        """
        step:    0              5
               --|--+--+--+--+--|--
        value:   0     3     4
        """
        persist = Persist()
        accumulate = Accumulator(persist, 5)

        # Persist data that would have been stored when
        # accumulate(2, 3, "key") was called.
        persist.set("key", (2, 6))
        step_data = accumulate(4, 4, "key")
        self.assertEqual(step_data, None)
        self.assertEqual(persist.get("key"), (4, 14))

    def test_accumulate_with_first_value_on_step_boundary(self):
        """
        step:    0              5
               --|--+--+--+--+--|--
        value:   14
        """
        persist = Persist()
        accumulate = Accumulator(persist, 5)

        self.assertEqual(persist.get("key"), None)
        step_data = accumulate(0, 14, "key")
        self.assertEqual(step_data, None)
        self.assertEqual(persist.get("key"), (0, 0))
