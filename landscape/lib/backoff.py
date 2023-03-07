import random


class ExponentialBackoff:
    """
    Keeps track of a backoff delay that staggers down and staggers up
    exponentially.
    """

    def __init__(self, start_delay, max_delay):

        self._error_count = 0  # A tally of server errors

        self._start_delay = start_delay
        self._max_delay = max_delay

    def decrease(self):
        """Decreases error count with zero being the lowest"""
        self._error_count -= 1
        self._error_count = max(self._error_count, 0)

    def increase(self):
        """Increases error count but not higher than gives the max delay"""
        if self.get_delay() < self._max_delay:
            self._error_count += 1

    def get_delay(self):
        """
        Calculates the delay using formula that gives this chart. In this
        specific example start is 5 seconds and max is 60 seconds
                Count  Delay
                0      0
                1      5
                2      10
                3      20
                4      40
                5      60 (max)
        """
        if self._error_count:
            delay = (2 ** (self._error_count - 1)) * self._start_delay
        else:
            delay = 0
        return min(int(delay), self._max_delay)

    def get_random_delay(self, stagger_fraction=0.25):
        """
        Adds randomness to the specified stagger of the delay. For example
        for a delay of 12 and 25% stagger, it works out to 9 + rand(0,3)
        """
        delay = self.get_delay()
        non_random_part = delay * (1 - stagger_fraction)
        random_part = delay * stagger_fraction * random.random()
        return int(non_random_part + random_part)
