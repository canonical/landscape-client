from landscape.lib.monitor import (
    Timer, Monitor, BurstMonitor, CoverageMonitor, FrequencyMonitor)
from landscape.reactor import FakeReactor
from landscape.tests.helpers import LandscapeTest


class ReactorHavingTest(LandscapeTest):
    def setUp(self):
        super(ReactorHavingTest, self).setUp()
        self.reactor = FakeReactor()


class TimerTest(ReactorHavingTest):

    def setUp(self):
        super(TimerTest, self).setUp()
        self.timer = Timer(create_time=self.reactor.time)

    def test_since_start(self):
        self.assertEquals(self.timer.since_start(), 0.0)

        self.reactor.advance(1)
        self.assertEquals(self.timer.since_start(), 1.0)

        self.reactor.advance(2)
        self.assertEquals(self.timer.since_start(), 3.0)

    def test_since_reset(self):
        self.reactor.advance(1)
        self.assertEquals(self.timer.since_reset(), 1.0)

        self.reactor.advance(1)
        self.assertEquals(self.timer.since_start(), 2.0)

        self.reactor.advance(2)
        self.timer.reset()
        self.assertEquals(self.timer.since_start(), 4.0)


class MonitorTest(ReactorHavingTest):

    def setUp(self):
        super(MonitorTest, self).setUp()
        self.monitor = Monitor("test", create_time=self.reactor.time)

    def test_ping(self):
        self.assertEquals(self.monitor.count, 0)
        self.assertEquals(self.monitor.total_count, 0)

        self.monitor.ping()
        self.assertEquals(self.monitor.count, 1)
        self.assertEquals(self.monitor.total_count, 1)

    def test_reset(self):
        self.assertEquals(self.monitor.count, 0)

        self.monitor.ping()
        self.monitor.ping()
        self.assertEquals(self.monitor.count, 2)
        self.assertEquals(self.monitor.total_count, 2)

        self.monitor.reset()
        self.monitor.ping()
        self.assertEquals(self.monitor.count, 1)
        self.assertEquals(self.monitor.total_count, 3)

    def test_log(self):
        for i in range(100):
            self.monitor.ping()
            self.reactor.advance(1)
        self.monitor.log()
        self.assertTrue("INFO: 100 test events occurred in the last 100.00s."
                        in self.logfile.getvalue())


class BurstMonitorTest(ReactorHavingTest):

    def setUp(self):
        super(BurstMonitorTest, self).setUp()
        self.monitor = BurstMonitor(60, 1, "test",
                                    create_time=self.reactor.time)

    def test_warn_no_pings(self):
        self.assertFalse(self.monitor.warn())

    def test_warn_below_threshold(self):
        self.monitor.ping()
        self.reactor.advance(61)
        self.assertFalse(self.monitor.warn())

    def test_warn_on_threshold(self):
        self.monitor.ping()
        self.reactor.advance(61)
        self.assertFalse(self.monitor.warn())

    def test_warn_over_threshold(self):
        self.monitor.ping()
        self.reactor.advance(30)
        self.monitor.ping()
        self.assertTrue(self.monitor.warn())

        self.reactor.advance(31)
        self.assertFalse(self.monitor.warn())

    def test_warn_in_first_interval(self):
        self.monitor.ping()
        self.reactor.advance(59)
        self.assertFalse(self.monitor.warn())

    def test_warn_unexpected_burst(self):
        self.monitor.ping()
        self.reactor.advance(5000)
        self.assertFalse(self.monitor.warn())

        self.monitor.ping()
        self.assertFalse(self.monitor.warn())

        self.monitor.ping()
        self.assertTrue(self.monitor.warn())

    def test_warn_maximum_count(self):
        monitor = BurstMonitor(60, 2, "test", create_time=self.reactor.time)
        monitor.ping()
        monitor.ping()
        self.assertFalse(monitor.warn())

        monitor.ping()
        self.assertTrue(monitor.warn())

    def test_warn_maximum_count_over_time_span(self):
        monitor = BurstMonitor(60, 3, "test", create_time=self.reactor.time)
        monitor.ping()
        monitor.ping()
        self.assertFalse(monitor.warn())

        self.reactor.advance(30)
        monitor.ping()
        self.assertFalse(monitor.warn())

        self.reactor.advance(31)
        monitor.ping()
        self.assertFalse(monitor.warn())

        monitor.ping()
        monitor.ping()
        self.assertTrue(monitor.warn())


class CoverageMonitorTest(ReactorHavingTest):

    def setUp(self):
        super(CoverageMonitorTest, self).setUp()
        self.monitor = CoverageMonitor(1, 1.0, "test",
                                       create_time=self.reactor.time)

    def test_warn(self):
        self.monitor.ping()
        self.reactor.advance(1)
        self.assertFalse(self.monitor.warn())

        self.reactor.advance(1)
        self.assertTrue(self.monitor.warn())

        self.monitor.reset()
        self.assertFalse(self.monitor.warn())

    def test_percent_no_data(self):
        """
        If no time has passed and the monitor hasn't received any
        pings it should return 100%.
        """
        self.assertEquals(self.monitor.percent, 1.0)

    def test_percent(self):
        self.reactor.advance(1)
        self.assertEquals(self.monitor.percent, 0.0)

        self.monitor.ping()
        self.reactor.advance(1)
        self.assertEquals(self.monitor.percent, 0.5)

    def test_percent_reset(self):
        self.reactor.advance(1)
        self.assertEquals(self.monitor.percent, 0.0)

        self.monitor.reset()
        self.monitor.ping()
        self.reactor.advance(1)
        self.assertEquals(self.monitor.percent, 1.0)

    def test_expected_count(self):
        self.reactor.advance(1)
        self.assertEquals(self.monitor.expected_count, 1.0)

        self.reactor.advance(1)
        self.assertEquals(self.monitor.expected_count, 2.0)

    def test_expected_count_reset(self):
        self.reactor.advance(1)
        self.assertEquals(self.monitor.expected_count, 1.0)

        self.monitor.reset()
        self.reactor.advance(1)
        self.assertEquals(self.monitor.expected_count, 1.0)

    def test_log(self):
        for i in range(100):
            self.monitor.ping()
            self.reactor.advance(1)
        self.monitor.log()
        self.assertTrue("INFO: 100 of 100 expected test events (100.00%) "
                        "occurred in the last 100.00s."
                        in self.logfile.getvalue())

    def test_log_warning(self):
        for i in range(100):
            self.reactor.advance(1)
        self.monitor.log()
        self.assertTrue("WARNING: 0 of 100 expected test events (0.00%) "
                        "occurred in the last 100.00s."
                        in self.logfile.getvalue())


class FrequencyMonitorTest(ReactorHavingTest):

    def setUp(self):
        super(FrequencyMonitorTest, self).setUp()
        self.monitor = FrequencyMonitor(100, 1, "test",
                                        create_time=self.reactor.time)

    def test_expected_count(self):
        self.assertEquals(self.monitor.expected_count, 0)

        self.reactor.advance(99)
        self.assertEquals(self.monitor.expected_count, 0)

        self.reactor.advance(1)
        self.assertEquals(self.monitor.expected_count, 1)

    def test_ping(self):
        self.assertFalse(self.monitor.warn())

        self.reactor.advance(80)
        self.monitor.ping()
        self.assertFalse(self.monitor.warn())

        self.reactor.advance(80)
        self.assertFalse(self.monitor.warn())

    def test_warn(self):
        self.assertFalse(self.monitor.warn())

        self.reactor.advance(101)
        self.assertTrue(self.monitor.warn())

    def test_log(self):
        self.monitor.ping()
        self.reactor.advance(100)
        self.monitor.log()
        self.assertTrue("minimum expected test events"
                        not in self.logfile.getvalue())
        self.reactor.advance(1)
        self.monitor.log()
        self.assertTrue("WARNING: Only 0 of 1 minimum expected test events "
                        "occurred in the last 100.00s."
                        in self.logfile.getvalue())
