from __future__ import absolute_import

import logging
import time

from landscape.lib.format import format_delta, format_percent


class Timer(object):
    """
    A timer keeps track of the number of seconds passed during it's
    lifetime and since the last reset.
    """

    def __init__(self, create_time=None):
        self._create_time = create_time or time.time
        self._creation_time = self._create_time()
        self._last_time = self._creation_time

    def time(self):
        return self._create_time()

    def since_start(self):
        return self._create_time() - self._creation_time

    def since_reset(self):
        return self._create_time() - self._last_time

    def reset(self):
        self._last_time = self._create_time()


class Monitor(Timer):
    """
    A monitor tracks the number of pings it received during it's
    lifetime and since the last reset.  The component being monitored
    is responsible for calling C{ping()} everytime a monitored
    activity occurs.  It should register a reactor event that logs
    statistics from this monitor every N seconds.  Essentially,
    monitors are just statistics checkers that components can use to
    monitor themselves.
    """

    def __init__(self, event_name, create_time=None):
        super(Monitor, self).__init__(create_time=create_time)
        self.event_name = event_name
        self.count = 0
        self.total_count = 0

    def ping(self):
        self.count += 1
        self.total_count += 1

    def reset(self):
        super(Monitor, self).reset()
        self.count = 0

    def log(self):
        logging.info("%d %s events occurred in the last %s.", self.count,
                     self.event_name, format_delta(self.since_reset()))
        self.reset()


class BurstMonitor(Monitor):
    """
    A burst monitor tracks the volume pings it receives.  It goes into
    warn mode when too many pings are received in a short period of
    time.
    """

    def __init__(self, repeat_interval, maximum_count, event_name,
                 create_time=None):
        super(BurstMonitor, self).__init__(event_name, create_time=create_time)
        self.repeat_interval = repeat_interval
        self.maximum_count = maximum_count
        self._last_times = []

    def ping(self):
        super(BurstMonitor, self).ping()
        now = self.time()
        self._last_times.append(now)
        if (self._last_times[0] - now > self.repeat_interval or
            len(self._last_times) > self.maximum_count + 1
            ):
            self._last_times.pop(0)

    def warn(self):
        if not self._last_times:
            return False
        delta = self.time() - self._last_times[0]
        return (delta < self.repeat_interval and
                len(self._last_times) >= self.maximum_count + 1)


class CoverageMonitor(Monitor):
    """
    A coverage monitor tracks the volume of pings received since the
    last reset.  It has normal and warn states that are determined by
    calculating the number of expected pings since the last reset.  If
    the actual number of pings falls below the minimum required
    percent the monitor goes into warn mode.  The component being
    monitored should register a reactor event that logs statistics
    from this monitor every N seconds.
    """

    def __init__(self, repeat_interval, min_percent, event_name,
                 create_time=None):
        super(CoverageMonitor, self).__init__(event_name,
                                              create_time=create_time)
        self.repeat_interval = repeat_interval
        self.min_percent = min_percent

    @property
    def percent(self):
        try:
            return self.count / float(self.expected_count)
        except ZeroDivisionError:
            return 1.0

    @property
    def expected_count(self):
        return int(self.since_reset() / self.repeat_interval)

    def log(self):
        percent = 0.0
        if self.percent and self.expected_count:
            percent = self.percent * 100

        log = logging.info
        if self.warn():
            log = logging.warning
        log("%d of %d expected %s events (%s) occurred in the last %s.",
            self.count, self.expected_count, self.event_name,
            format_percent(percent), format_delta(self.since_reset()))

        self.reset()

    def warn(self):
        if self.repeat_interval and self.min_percent:
            if not self.expected_count:
                return False
            if self.percent < self.min_percent:
                return True
        return False


class FrequencyMonitor(Monitor):
    """
    A frequency monitor tracks the number of pings received during a
    fixed period of time.  It has normal and warn states; a warn state
    is triggered when the minimum expected pings were not received
    during the specified interval.  The component being monitored
    should register a reactor event that checks the warn state of this
    monitor every N seconds.
    """

    def __init__(self, repeat_interval, min_frequency, event_name,
                 create_time=None):
        super(FrequencyMonitor, self).__init__(event_name,
                                               create_time=create_time)
        self.repeat_interval = repeat_interval
        self.min_frequency = min_frequency
        self._last_count = self._create_time()

    @property
    def expected_count(self):
        since_ping = self._create_time() - self._last_count
        return since_ping // self.repeat_interval

    def ping(self):
        super(FrequencyMonitor, self).ping()
        self._last_count = self._create_time()

    def log(self):
        if self.warn():
            logging.warning("Only %d of %d minimum expected %s events "
                            "occurred in the last %s.", self.count,
                            self.expected_count, self.event_name,
                            format_delta(self.repeat_interval))
        self.reset()

    def warn(self):
        if self.repeat_interval and self.min_frequency:
            if ((self._create_time() - self._last_count >=
                 self.repeat_interval) and
                self.count < self.min_frequency
                ):
                return True
        return False
