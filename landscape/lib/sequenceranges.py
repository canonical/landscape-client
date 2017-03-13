from twisted.python.compat import xrange


class SequenceError(Exception):
    """Raised when the sequence isn't proper for translation to ranges."""


class SequenceRanges(object):
    """High level interface to ranges.

    A ranges list represent a sequence of ordered and non-repeating
    elements into a more compact format, by representing 3 or more
    consecutive entries by a range.

    This means that a sequence such as

        [1, 2, 4, 5, 6, 8, 10, 11, 12, 14]

    becomes

        [1, 2, (4, 6), 8, (10, 12), 14]
    """

    def __init__(self):
        self._ranges = []

    @classmethod
    def from_sequence(cls, sequence):
        obj = cls()
        obj._ranges[:] = sequence_to_ranges(sequence)
        return obj

    @classmethod
    def from_ranges(cls, ranges):
        obj = cls()
        obj._ranges[:] = ranges
        return obj

    def to_sequence(self):
        return list(ranges_to_sequence(self._ranges))

    def to_ranges(self):
        return list(self._ranges)

    def __iter__(self):
        return ranges_to_sequence(self._ranges)

    def __contains__(self, item):
        index = find_ranges_index(self._ranges, item)
        if index < len(self._ranges):
            test = self._ranges[index]
            if isinstance(test, tuple):
                return (test[0] <= item <= test[1])
            return (test == item)
        return False

    def add(self, item):
        add_to_ranges(self._ranges, item)

    def remove(self, item):
        remove_from_ranges(self._ranges, item)


def sequence_to_ranges(sequence):
    """Iterate over range items that compose the given sequence."""

    iterator = iter(sequence)
    try:
        range_start = range_stop = next(iterator)
    except StopIteration:
        return
    while range_start is not None:
        try:
            item = next(iterator)
        except StopIteration:
            item = None
        if item == range_stop + 1:
            range_stop += 1
        else:
            if item is not None and item <= range_stop:
                if item < range_stop:
                    raise SequenceError("Sequence is unordered (%r < %r)" %
                                        (item, range_stop))
                else:
                    raise SequenceError("Found duplicated item (%r)" % (item,))
            if range_stop == range_start:
                yield range_start
            elif range_stop == range_start + 1:
                yield range_start
                yield range_stop
            else:
                yield (range_start, range_stop)
            range_start = range_stop = item


def ranges_to_sequence(ranges):
    """Iterate over individual items represented in a ranges list."""
    for item in ranges:
        if isinstance(item, tuple):
            start, end = item
            if start > end:
                raise ValueError("Range error %d > %d", start, end)
            for item in xrange(start, end + 1):
                yield item
        else:
            yield item


def find_ranges_index(ranges, item):
    """Find the index where an entry *may* be."""
    lo = 0
    hi = len(ranges)
    while lo < hi:
        mid = (lo + hi) // 2
        test = ranges[mid]
        try:
            test = test[1]
        except TypeError:
            pass
        if item > test:
            lo = mid + 1
        else:
            hi = mid
    return lo


def add_to_ranges(ranges, item):
    """Insert item in ranges, reorganizing as needed."""

    index_start = index_stop = index = find_ranges_index(ranges, item)
    range_start = range_stop = item

    ranges_len = len(ranges)

    # Look for duplicates.
    if index < ranges_len:
        test = ranges[index]
        if isinstance(test, tuple):
            if test[0] <= item <= test[1]:
                return
        elif test == item:
            return

    # Merge to the left side.
    while index_start > 0:
        test = ranges[index_start - 1]
        if isinstance(test, tuple):
            if test[1] != range_start - 1:
                break
            range_start = test[0]
        else:
            if test != range_start - 1:
                break
            range_start -= 1
        index_start -= 1

    # Merge to the right side.
    while index_stop < ranges_len:
        test = ranges[index_stop]
        if isinstance(test, tuple):
            if test[0] != range_stop + 1:
                break
            range_stop = test[1]
        else:
            if test != range_stop + 1:
                break
            range_stop += 1
        index_stop += 1

    if range_stop - range_start < 2:
        ranges.insert(index, item)
    else:
        ranges[index_start:index_stop] = ((range_start, range_stop),)


def remove_from_ranges(ranges, item):
    """Remove item from ranges, reorganizing as needed."""

    index = find_ranges_index(ranges, item)
    ranges_len = len(ranges)
    if index < ranges_len:
        test = ranges[index]
        if isinstance(test, tuple):
            range_start, range_stop = test
            if item >= range_start:
                # Handle right side of the range (and replace original item).
                if range_stop < item + 3:
                    ranges[index:index + 1] = range(item + 1, range_stop + 1)
                else:
                    ranges[index:index + 1] = ((item + 1, range_stop),)

                # Handle left side of the range.
                if range_start > item - 3:
                    if range_start != item:
                        ranges[index:index] = range(range_start, item)
                else:
                    ranges[index:index] = ((range_start, item - 1),)
        elif item == test:
            del ranges[index]
