import pprint
import unittest

from landscape.client.tests.subunit import run_isolated
from landscape.client.watchdog import bootstrap_list

from landscape.lib.persist import Persist
from landscape.lib.testing import FakeReactor

from landscape.client.broker.config import BrokerConfiguration
from landscape.client.broker.transport import FakeTransport
from landscape.client.monitor.config import MonitorConfiguration
from landscape.client.monitor.monitor import Monitor
from landscape.client.manager.manager import Manager

from landscape.client.broker.service import BrokerService
from landscape.client.broker.amp import FakeRemoteBroker, RemoteBrokerConnector
from landscape.client.deployment import BaseConfiguration
from landscape.client.manager.config import ManagerConfiguration

from landscape.lib import testing


DEFAULT_ACCEPTED_TYPES = [
    "accepted-types", "registration", "resynchronize", "set-id",
    "set-intervals", "unknown-id"]


class MessageTestCase(unittest.TestCase):

    def assertMessage(self, obtained, expected):
        obtained = obtained.copy()
        for key in ["api", "timestamp"]:
            if key not in expected and key in obtained:
                obtained.pop(key)
        if obtained != expected:
            raise self.failureException("Messages don't match.\n"
                                        "Expected:\n%s\nObtained:\n%s\n"
                                        % (pprint.pformat(expected),
                                           pprint.pformat(obtained)))

    def assertMessages(self, obtained, expected):
        self.assertEqual(type(obtained), list)
        self.assertEqual(type(expected), list)
        for obtained_message, expected_message in zip(obtained, expected):
            self.assertMessage(obtained_message, expected_message)
        obtained_len = len(obtained)
        expected_len = len(expected)
        diff = abs(expected_len - obtained_len)
        if obtained_len < expected_len:
            extra = pprint.pformat(expected[-diff:])
            raise self.failureException("Expected the following %d additional "
                                        "messages:\n%s" % (diff, extra))
        elif expected_len < obtained_len:
            extra = pprint.pformat(obtained[-diff:])
            raise self.failureException("Got %d more messages than expected:\n"
                                        "%s" % (diff, extra))


class LandscapeTest(MessageTestCase, testing.TwistedTestCase,
                    testing.HelperTestCase, testing.ConfigTestCase,
                    testing.CompatTestCase):

    def setUp(self):
        testing.TwistedTestCase.setUp(self)
        result = testing.HelperTestCase.setUp(self)

        self._orig_filenames = BaseConfiguration.default_config_filenames
        BaseConfiguration.default_config_filenames = (
                testing.BaseConfiguration.default_config_filenames)

        return result

    def tearDown(self):
        BaseConfiguration.default_config_filenames = self._orig_filenames

        testing.TwistedTestCase.tearDown(self)
        testing.HelperTestCase.tearDown(self)

    def makePersistFile(self, *args, **kwargs):
        """Return a temporary filename to be used by a L{Persist} object.

        The possible .old persist file is cleaned up after the test.
        """
        return self.makeFile(*args, backupsuffix=".old", **kwargs)


class LandscapeIsolatedTest(LandscapeTest):
    """TestCase that also runs all test methods in a subprocess."""

    def run(self, result):
        if not getattr(LandscapeTest, "_cleanup_patch", False):
            run_method = LandscapeTest.run

            def run_wrapper(oself, *args, **kwargs):
                try:
                    return run_method(oself, *args, **kwargs)
                finally:
                    self.doCleanups()
            LandscapeTest.run = run_wrapper
            LandscapeTest._cleanup_patch = True
        run_isolated(LandscapeTest, self, result)


class FakeBrokerServiceHelper(object):
    """
    The following attributes will be set in your test case:
      - broker_service: A C{BrokerService}.
      - remote: A C{FakeRemoteBroker} behaving like a L{RemoteBroker} connected
          to the broker serivice but performing all operation synchronously.
    """

    def set_up(self, test_case):
        test_case.data_path = test_case.makeDir()
        log_dir = test_case.makeDir()
        test_case.config_filename = test_case.makeFile(
            "[client]\n"
            "url = http://localhost:91919\n"
            "computer_title = Some Computer\n"
            "account_name = some_account\n"
            "ping_url = http://localhost:91910\n"
            "data_path = %s\n"
            "log_dir = %s\n" % (test_case.data_path, log_dir))

        bootstrap_list.bootstrap(data_path=test_case.data_path,
                                 log_dir=log_dir)

        config = BrokerConfiguration()
        config.load(["-c", test_case.config_filename])

        class FakeBrokerService(BrokerService):
            reactor_factory = FakeReactor
            transport_factory = FakeTransport

        test_case.broker_service = FakeBrokerService(config)
        test_case.reactor = test_case.broker_service.reactor
        test_case.remote = FakeRemoteBroker(
            test_case.broker_service.exchanger,
            test_case.broker_service.message_store,
            test_case.broker_service.broker)


class BrokerServiceHelper(FakeBrokerServiceHelper):
    """
    Provides what L{FakeBrokerServiceHelper} does, and makes it a
    'live' service using a real L{RemoteBroker} connected over AMP.

    This adds the following attributes to your test case:
     - remote: A connected L{RemoteBroker}.
    """

    def set_up(self, test_case):
        super(BrokerServiceHelper, self).set_up(test_case)
        test_case.broker_service.startService()
        # Use different reactor to simulate separate processes
        self._connector = RemoteBrokerConnector(
            FakeReactor(), test_case.broker_service.config)
        deferred = self._connector.connect()
        test_case.remote = test_case.successResultOf(deferred)

    def tear_down(self, test_case):
        self._connector.disconnect()
        test_case.broker_service.stopService()


class MonitorHelper(FakeBrokerServiceHelper):
    """
    Provides everything that L{FakeBrokerServiceHelper} does plus a
    L{Monitor} instance.
    """

    def set_up(self, test_case):
        super(MonitorHelper, self).set_up(test_case)
        persist = Persist()
        persist_filename = test_case.makePersistFile()
        test_case.config = MonitorConfiguration()
        test_case.config.load(["-c", test_case.config_filename])
        test_case.config.stagger_launch = 0  # let's keep tests deterministic
        test_case.reactor = FakeReactor()
        test_case.monitor = Monitor(
            test_case.reactor, test_case.config,
            persist, persist_filename)
        test_case.monitor.broker = test_case.remote
        test_case.mstore = test_case.broker_service.message_store


class ManagerHelper(FakeBrokerServiceHelper):
    """
    Provides everything that L{FakeBrokerServiceHelper} does plus a
    L{Manager} instance.
    """

    def set_up(self, test_case):
        super(ManagerHelper, self).set_up(test_case)
        test_case.config = ManagerConfiguration()
        test_case.config.load(["-c", test_case.config_filename])
        test_case.reactor = FakeReactor()
        test_case.manager = Manager(test_case.reactor, test_case.config)
        test_case.manager.broker = test_case.remote


class MockCoverageMonitor(object):

    def __init__(self, count=None, expected_count=None, percent=None,
                 since_reset=None, warn=None):
        self.count = count or 0
        self.expected_count = expected_count or 0
        self.percent = percent or 0.0
        self.since_reset_value = since_reset or 0
        self.warn_value = bool(warn)

    def since_reset(self):
        return self.since_reset_value

    def warn(self):
        return self.warn_value

    def reset(self):
        pass


class MockFrequencyMonitor(object):

    def __init__(self, count=None, expected_count=None, warn=None):
        self.count = count or 0
        self.expected_count = expected_count or 0
        self.warn_value = bool(warn)

    def warn(self):
        return self.warn_value

    def reset(self):
        pass


class FakePersist(object):
    """
    Incompletely fake a C{landscape.lib.Persist} to simplify higher level tests
    that result in an attempt to clear down persisted data.
    """

    def __init__(self):
        self.called = False

    def remove(self, key):
        self.called = True
