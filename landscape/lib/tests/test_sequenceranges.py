import unittest

from landscape.lib.sequenceranges import (
    SequenceRanges, remove_from_ranges, add_to_ranges, find_ranges_index,
    ranges_to_sequence, sequence_to_ranges, SequenceError)


class SequenceRangesTest(unittest.TestCase):

    def setUp(self):
        self.ranges = [1, 2, (15, 17), 19, (21, 24), 26, 27]
        self.sequence = [1, 2, 15, 16, 17, 19, 21, 22, 23, 24, 26, 27]

    def test_empty_to_sequence(self):
        self.assertEqual(SequenceRanges().to_sequence(), [])

    def test_empty_to_ranges(self):
        self.assertEqual(SequenceRanges().to_ranges(), [])

    def test_from_to_sequence(self):
        obj = SequenceRanges.from_sequence(self.sequence)
        self.assertEqual(obj.to_sequence(), self.sequence)

    def test_from_to_ranges(self):
        obj = SequenceRanges.from_ranges(self.ranges)
        self.assertEqual(obj.to_ranges(), self.ranges)

    def test_to_ranges_immutable(self):
        obj = SequenceRanges.from_ranges(self.ranges)
        obj.to_ranges().append(123)
        self.assertEqual(obj.to_ranges(), self.ranges)

    def test_from_sequence_to_ranges(self):
        obj = SequenceRanges.from_sequence(self.sequence)
        self.assertEqual(list(obj.to_ranges()), self.ranges)

    def test_from_ranges_to_sequence(self):
        obj = SequenceRanges.from_ranges(self.ranges)
        self.assertEqual(list(obj.to_sequence()), self.sequence)

    def test_iter(self):
        obj = SequenceRanges.from_ranges(self.ranges)
        self.assertEqual(list(obj), self.sequence)

    def test_contains(self):
        obj = SequenceRanges.from_ranges(self.ranges)
        self.assertTrue(1 in obj)
        self.assertTrue(2 in obj)
        self.assertTrue(15 in obj)
        self.assertTrue(16 in obj)
        self.assertTrue(17 in obj)
        self.assertTrue(19 in obj)
        self.assertTrue(27 in obj)
        self.assertTrue(0 not in obj)
        self.assertTrue(3 not in obj)
        self.assertTrue(14 not in obj)
        self.assertTrue(18 not in obj)
        self.assertTrue(20 not in obj)
        self.assertTrue(28 not in obj)

    def test_add(self):
        obj = SequenceRanges()
        obj.add(1)
        self.assertEqual(obj.to_ranges(), [1])
        obj.add(2)
        self.assertEqual(obj.to_ranges(), [1, 2])
        obj.add(3)
        self.assertEqual(obj.to_ranges(), [(1, 3)])
        obj.add(3)
        self.assertEqual(obj.to_ranges(), [(1, 3)])

    def test_remove(self):
        obj = SequenceRanges.from_ranges([(1, 3)])
        obj.remove(2)
        self.assertEqual(obj.to_ranges(), [1, 3])
        obj.remove(1)
        self.assertEqual(obj.to_ranges(), [3])
        obj.remove(3)
        self.assertEqual(obj.to_ranges(), [])
        obj.remove(4)
        self.assertEqual(obj.to_ranges(), [])


class SequenceToRangesTest(unittest.TestCase):

    def test_empty(self):
        self.assertEqual(list(sequence_to_ranges([])), [])

    def test_one_element(self):
        self.assertEqual(list(sequence_to_ranges([1])), [1])

    def test_two_elements(self):
        self.assertEqual(list(sequence_to_ranges([1, 2])), [1, 2])

    def test_three_elements(self):
        self.assertEqual(list(sequence_to_ranges([1, 2, 3])), [(1, 3)])

    def test_many_elements(self):
        sequence = [1, 2, 15, 16, 17, 19, 21, 22, 23, 24, 26, 27]
        self.assertEqual(list(sequence_to_ranges(sequence)),
                         [1, 2, (15, 17), 19, (21, 24), 26, 27])

    def test_out_of_order(self):
        self.assertRaises(SequenceError, next, sequence_to_ranges([2, 1]))

    def test_duplicated_item(self):
        self.assertRaises(SequenceError, next, sequence_to_ranges([1, 1]))


class RangesToSequenceTest(unittest.TestCase):

    def test_empty(self):
        self.assertEqual(list(ranges_to_sequence([])), [])

    def test_one_element(self):
        self.assertEqual(list(ranges_to_sequence([1])), [1])

    def test_two_elements(self):
        self.assertEqual(list(ranges_to_sequence([1, 2])), [1, 2])

    def test_three_elements(self):
        self.assertEqual(list(ranges_to_sequence([(1, 3)])), [1, 2, 3])

    def test_many_elements(self):
        ranges = [1, 2, (15, 17), 19, (21, 24), 26, 27]
        self.assertEqual(list(ranges_to_sequence(ranges)),
                         [1, 2, 15, 16, 17, 19, 21, 22, 23, 24, 26, 27])

    def test_invalid_range(self):
        """
        If range start value is greater than the end one, an error is raised.
        """
        ranges = [1, 2, (5, 3), 10]
        self.assertRaises(ValueError, list, ranges_to_sequence(ranges))


class FindRangesIndexTest(unittest.TestCase):

    def test_empty(self):
        self.assertEqual(find_ranges_index([], 2), 0)

    def test_sequence(self):
        self.assertEqual(find_ranges_index([1, 2, 3, 4, 5], 0), 0)
        self.assertEqual(find_ranges_index([1, 2, 3, 4, 5], 1), 0)
        self.assertEqual(find_ranges_index([1, 2, 3, 4, 5], 2), 1)
        self.assertEqual(find_ranges_index([1, 2, 3, 4, 5], 3), 2)
        self.assertEqual(find_ranges_index([1, 2, 3, 4, 5], 4), 3)
        self.assertEqual(find_ranges_index([1, 2, 3, 4, 5], 5), 4)
        self.assertEqual(find_ranges_index([1, 2, 3, 4, 5], 6), 5)

    def test_sequence_with_missing(self):
        self.assertEqual(find_ranges_index([1, 2, 4, 5], 2), 1)
        self.assertEqual(find_ranges_index([1, 2, 4, 5], 3), 2)
        self.assertEqual(find_ranges_index([1, 2, 4, 5], 4), 2)

    def test_range(self):
        self.assertEqual(find_ranges_index([1, (2, 4), 5], 0), 0)
        self.assertEqual(find_ranges_index([1, (2, 4), 5], 1), 0)
        self.assertEqual(find_ranges_index([1, (2, 4), 5], 2), 1)
        self.assertEqual(find_ranges_index([1, (2, 4), 5], 3), 1)
        self.assertEqual(find_ranges_index([1, (2, 4), 5], 4), 1)
        self.assertEqual(find_ranges_index([1, (2, 4), 5], 5), 2)
        self.assertEqual(find_ranges_index([1, (2, 4), 5], 6), 3)

    def test_range_with_missing(self):
        self.assertEqual(find_ranges_index([1, (3, 4), 5], 0), 0)
        self.assertEqual(find_ranges_index([1, (3, 4), 5], 1), 0)
        self.assertEqual(find_ranges_index([1, (3, 4), 5], 2), 1)
        self.assertEqual(find_ranges_index([1, (3, 4), 5], 3), 1)
        self.assertEqual(find_ranges_index([1, (3, 4), 5], 4), 1)
        self.assertEqual(find_ranges_index([1, (3, 4), 5], 5), 2)
        self.assertEqual(find_ranges_index([1, (3, 4), 5], 6), 3)


class AddToRangesTest(unittest.TestCase):

    def test_empty(self):
        ranges = []
        add_to_ranges(ranges, 1)
        self.assertEqual(ranges, [1])

    def test_append(self):
        ranges = [1]
        add_to_ranges(ranges, 2)
        self.assertEqual(ranges, [1, 2])

    def test_prepend(self):
        ranges = [2]
        add_to_ranges(ranges, 1)
        self.assertEqual(ranges, [1, 2])

    def test_insert(self):
        ranges = [1, 4]
        add_to_ranges(ranges, 2)
        self.assertEqual(ranges, [1, 2, 4])

    def test_merge_sequence(self):
        ranges = [1, 2, 4, 5]
        add_to_ranges(ranges, 3)
        self.assertEqual(ranges, [(1, 5)])

    def test_merge_ranges(self):
        ranges = [(1, 3), (5, 7)]
        add_to_ranges(ranges, 4)
        self.assertEqual(ranges, [(1, 7)])

    def test_merge_sequence_and_ranges(self):
        ranges = [(1, 3), 5, 6, 7]
        add_to_ranges(ranges, 4)
        self.assertEqual(ranges, [(1, 7)])

    def test_merge_sequence_and_ranges_with_gaps(self):
        ranges = [1, (3, 5), 7, 9]
        add_to_ranges(ranges, 6)
        self.assertEqual(ranges, [1, (3, 7), 9])

    def test_dont_merge_ranges_with_gap(self):
        ranges = [(1, 3), (7, 9)]
        add_to_ranges(ranges, 5)
        self.assertEqual(ranges, [(1, 3), 5, (7, 9)])

    def test_duplicate(self):
        ranges = [1]
        add_to_ranges(ranges, 1)
        self.assertEqual(ranges, [1])

    def test_duplicate_in_range(self):
        ranges = [(1, 3)]
        add_to_ranges(ranges, 1)
        self.assertEqual(ranges, [(1, 3)])
        add_to_ranges(ranges, 2)
        self.assertEqual(ranges, [(1, 3)])
        add_to_ranges(ranges, 3)
        self.assertEqual(ranges, [(1, 3)])


class RemoveFromRangesTest(unittest.TestCase):

    def test_empty(self):
        ranges = []
        remove_from_ranges(ranges, 1)
        self.assertEqual(ranges, [])

    def test_single(self):
        ranges = [1]
        remove_from_ranges(ranges, 1)
        self.assertEqual(ranges, [])

    def test_remove_before(self):
        ranges = [1, 2]
        remove_from_ranges(ranges, 1)
        self.assertEqual(ranges, [2])

    def test_remove_after(self):
        ranges = [1, 2]
        remove_from_ranges(ranges, 2)
        self.assertEqual(ranges, [1])

    def test_remove_inside(self):
        ranges = [1, 2, 3]
        remove_from_ranges(ranges, 2)
        self.assertEqual(ranges, [1, 3])

    def test_remove_unexistent(self):
        ranges = [1, 3]
        remove_from_ranges(ranges, 2)
        self.assertEqual(ranges, [1, 3])

    def test_split_range(self):
        ranges = [(1, 5)]
        remove_from_ranges(ranges, 3)
        self.assertEqual(ranges, [1, 2, 4, 5])

    def test_split_range_into_ranges(self):
        ranges = [(1, 7)]
        remove_from_ranges(ranges, 4)
        self.assertEqual(ranges, [(1, 3), (5, 7)])

    def test_decrement_left(self):
        ranges = [(1, 5)]
        remove_from_ranges(ranges, 1)
        self.assertEqual(ranges, [(2, 5)])

    def test_decrement_right(self):
        ranges = [(1, 5)]
        remove_from_ranges(ranges, 5)
        self.assertEqual(ranges, [(1, 4)])

    def test_dont_removing_unmatched_range(self):
        ranges = [(1, 3), (5, 7)]
        remove_from_ranges(ranges, 4)
        self.assertEqual(ranges, [(1, 3), (5, 7)])


def test_suite():
    return unittest.TestSuite((
        unittest.makeSuite(SequenceToRangesTest),
        unittest.makeSuite(RangesToSequenceTest),
        unittest.makeSuite(SequenceRangesTest),
        unittest.makeSuite(FindRangesIndexTest),
        unittest.makeSuite(AddToRangesTest),
        unittest.makeSuite(RemoveFromRangesTest),
    ))
