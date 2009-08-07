from cStringIO import StringIO
import logging
import shutil
import pprint
import re
import os
import tempfile
import sys
import unittest

import dbus

from twisted.trial.unittest import TestCase
from twisted.internet.defer import Deferred

from landscape.tests.subunit import run_isolated
from landscape.tests.mocker import MockerTestCase
from landscape.watchdog import bootstrap_list

from landscape.lib.dbus_util import get_object
from landscape.lib import bpickle_dbus
from landscape.lib.persist import Persist

from landscape.reactor import FakeReactor

from landscape.broker.deployment import (BrokerService, BrokerConfiguration)
from landscape.deployment import BaseConfiguration
from landscape.broker.remote import RemoteBroker, FakeRemoteBroker
from landscape.broker.transport import FakeTransport

from landscape.monitor.monitor import MonitorPluginRegistry
from landscape.manager.manager import ManagerPluginRegistry
from landscape.manager.deployment import ManagerConfiguration


DEFAULT_ACCEPTED_TYPES = [
    "accepted-types", "registration", "resynchronize", "set-id",
    "set-intervals", "unknown-id"]


class HelperTestCase(unittest.TestCase):

    helpers = []

    def setUp(self):
        self._helper_instances = []
        if LogKeeperHelper not in self.helpers:
            self.helpers.insert(0, LogKeeperHelper)
        for helper_factory in self.helpers:
            helper = helper_factory()
            helper.set_up(self)
            self._helper_instances.append(helper)

    def tearDown(self):
        for helper in reversed(self._helper_instances):
            helper.tear_down(self)


class MakeDirTestCase(unittest.TestCase):

    def setUp(self):
        # make_path-related stuff
        self.dirname = tempfile.mkdtemp()
        self.counter = 0

    def tearDown(self):
        shutil.rmtree(self.dirname)

    def make_dir(self):
        path = self.make_path()
        os.mkdir(path)
        return path

    def make_path(self, content=None, path=None):
        if path is None:
            self.counter += 1
            path = "%s/%03d" % (self.dirname, self.counter)
        if content is not None:
            file = open(path, "w")
            try:
                file.write(content)
            finally:
                file.close()
        return path


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
        self.assertEquals(type(obtained), list)
        self.assertEquals(type(expected), list)
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


class LandscapeTest(MessageTestCase, MockerTestCase, MakeDirTestCase,
                    HelperTestCase, TestCase):

    def setUp(self):
        self._old_config_filenames = BaseConfiguration.default_config_filenames
        BaseConfiguration.default_config_filenames = []
        MockerTestCase.setUp(self)
        MakeDirTestCase.setUp(self)
        HelperTestCase.setUp(self)
        TestCase.setUp(self)

    def tearDown(self):
        BaseConfiguration.default_config_filenames = self._old_config_filenames
        TestCase.tearDown(self)
        HelperTestCase.tearDown(self)
        MakeDirTestCase.tearDown(self)
        MockerTestCase.tearDown(self)

    def assertDeferredSucceeded(self, deferred):
        self.assertTrue(isinstance(deferred, Deferred))
        called = []
        def callback(result):
            called.append(True)
        deferred.addCallback(callback)
        self.assertTrue(called)

class LandscapeIsolatedTest(LandscapeTest):
    """TestCase that also runs all test methods in a subprocess."""

    def run(self, result):
        run_isolated(LandscapeTest, self, result)


class DBusHelper(object):
    """Create a temporary D-Bus."""

    def set_up(self, test_case):
        if not getattr(test_case, "I_KNOW", False):
            test_case.assertTrue(isinstance(test_case, LandscapeIsolatedTest),
                                 "DBusHelper must only be used on "
                                 "LandscapeIsolatedTests")
        bpickle_dbus.install()
        test_case.bus = dbus.SessionBus()

    def tear_down(self, test_case):
        bpickle_dbus.uninstall()


from logging import Handler, ERROR, Formatter

class ErrorHandler(Handler):
    def __init__(self, *args, **kwargs):
        Handler.__init__(self, *args, **kwargs)
        self.errors = []

    def emit(self, record):
        if record.levelno >= ERROR:
            self.errors.append(record)


class LoggedErrorsError(Exception):
    def __str__(self):
        out = "The following errors were logged\n"
        formatter = Formatter()
        for error in self.args[0]:
            out += formatter.format(error) + "\n"
        return out


class LogKeeperHelper(object):
    """Record logging information.

    Puts a 'logfile' attribute on your test case, which is a StringIO
    containing all log output.
    """

    def set_up(self, test_case):
        self.ignored_exception_regexes = []
        self.ignored_exception_types = []
        self.error_handler = ErrorHandler()
        test_case.log_helper = self
        test_case.logger = logger = logging.getLogger()
        test_case.logfile = StringIO()
        handler = logging.StreamHandler(test_case.logfile)
        format = ("%(levelname)8s: %(message)s")
        handler.setFormatter(logging.Formatter(format))
        self.old_handlers = logger.handlers
        self.old_level = logger.level
        logger.handlers = [handler, self.error_handler]
        logger.setLevel(logging.NOTSET)

    def tear_down(self, test_case):
        logger = logging.getLogger()
        logger.setLevel(self.old_level)
        logger.handlers = self.old_handlers
        errors = []
        for record in self.error_handler.errors:
            for ignored_type in self.ignored_exception_types:
                if (record.exc_info and record.exc_info[0]
                    and issubclass(record.exc_info[0], ignored_type)):
                    break
            else:
                for ignored_regex in self.ignored_exception_regexes:
                    if ignored_regex.match(record.message):
                        break
                else:
                    errors.append(record)
        if errors:
            raise LoggedErrorsError(errors)

    def ignore_errors(self, type_or_regex):
        if isinstance(type_or_regex, basestring):
            self.ignored_exception_regexes.append(re.compile(type_or_regex))
        else:
            self.ignored_exception_types.append(type_or_regex)


class EnvironSnapshot(object):

    def __init__(self):
        self._snapshot = os.environ.copy()

    def restore(self):
        os.environ.update(self._snapshot)
        for key in list(os.environ):
            if key not in self._snapshot:
                del os.environ[key]


class EnvironSaverHelper(object):

    def set_up(self, test_case):
        self._snapshot = EnvironSnapshot()

    def tear_down(self, test_case):
        self._snapshot.restore()


class FakeRemoteBrokerHelper(object):
    """
    The following attributes will be set on your test case:
      - broker_service: A L{landscape.broker.deployment.BrokerService}.
      - config_filename: The name of the configuration file that was used to
        generate the C{broker}.
      - data_path: The data path that the broker will use.
    """

    reactor_factory = FakeReactor
    transport_factory = FakeTransport
    needs_bpickle_dbus = True

    def set_up(self, test_case):
        if self.needs_bpickle_dbus:
            bpickle_dbus.install()

        test_case.config_filename = test_case.make_path(
            "[client]\n"
            "url = http://localhost:91919\n"
            "computer_title = Default Computer Title\n"
            "account_name = default_account_name\n"
            "ping_url = http://localhost:91910/\n")

        test_case.data_path = test_case.make_dir()
        test_case.log_dir = test_case.make_dir()

        bootstrap_list.bootstrap(data_path=test_case.data_path,
                                 log_dir=test_case.log_dir)

        class MyBrokerConfiguration(BrokerConfiguration):
            default_config_filenames = [test_case.config_filename]

        config = MyBrokerConfiguration()
        config.load(["--bus", "session",
                     "--data-path", test_case.data_path,
                     "--ignore-sigusr1"])

        class FakeBrokerService(BrokerService):
            """A broker which uses a fake reactor and fake transport."""
            reactor_factory = self.reactor_factory
            transport_factory = self.transport_factory

        test_case.broker_service = service = FakeBrokerService(config)
        test_case.remote = FakeRemoteBroker(service.exchanger,
                                            service.message_store)

    def tear_down(self, test_case):
        if self.needs_bpickle_dbus:
            bpickle_dbus.uninstall()


class RemoteBrokerHelper(FakeRemoteBrokerHelper):
    """
    Provides what L{FakeRemoteBrokerHelper} does, and makes it a
    'live' service. Since it uses DBUS, your test case must be a
    subclass of L{LandscapeIsolatedTest}.

    This adds the following attributes to your test case:
     - remote: A L{landscape.broker.remote.RemoteBroker}.
     - remote_service: The low level DBUS object that refers to the
       L{landscape.broker.broker.BrokerDBusObject}.
    """

    def set_up(self, test_case):
        if not getattr(test_case, "I_KNOW", False):
            test_case.assertTrue(isinstance(test_case, LandscapeIsolatedTest),
                                 "RemoteBrokerHelper must only be used on "
                                 "LandscapeIsolatedTests")
        super(RemoteBrokerHelper, self).set_up(test_case)
        service = test_case.broker_service
        service.startService()
        test_case.remote = RemoteBroker(service.bus)
        test_case.remote_service = get_object(service.bus,
                                              service.dbus_object.bus_name,
                                              service.dbus_object.object_path)

    def tear_down(self, test_case):
        test_case.broker_service.stopService()
        super(RemoteBrokerHelper, self).tear_down(test_case)


class ExchangeHelper(FakeRemoteBrokerHelper):
    """
    Backwards compatibility layer for tests that want a bunch of attributes
    jammed on to them instead of having C{self.broker_service}.
    """

    def set_up(self, test_case):
        super(ExchangeHelper, self).set_up(test_case)

        service = test_case.broker_service

        test_case.persist_filename = service.persist_filename
        test_case.message_directory = service.config.message_store_path
        test_case.transport = service.transport
        test_case.reactor = service.reactor
        test_case.persist = service.persist
        test_case.mstore = service.message_store
        test_case.exchanger = service.exchanger
        test_case.identity = service.identity


class MonitorHelper(ExchangeHelper):
    """
    Provides everything that L{ExchangeHelper} does plus a
    L{landscape.monitor.monitor.Monitor}.
    """

    def set_up(self, test_case):
        super(MonitorHelper, self).set_up(test_case)
        persist = Persist()
        persist_filename = test_case.make_path()
        test_case.monitor = MonitorPluginRegistry(
            test_case.remote, test_case.broker_service.reactor,
            test_case.broker_service.config,
            # XXX Ugh, the fake broker service doesn't have a bus.
            # We should get rid of the fake broker service.
            getattr(test_case.broker_service, "bus", None),
            persist, persist_filename)


class ManagerHelper(FakeRemoteBrokerHelper):
    """
    Provides everything that L{FakeRemoteBrokerHelper} does plus a
    L{landscape.manager.manager.Manager}.
    """
    def set_up(self, test_case):
        super(ManagerHelper, self).set_up(test_case)
        class MyManagerConfiguration(ManagerConfiguration):
            default_config_filenames = [test_case.config_filename]
        config = MyManagerConfiguration()
        test_case.manager = ManagerPluginRegistry(
            test_case.remote, test_case.broker_service.reactor,
            config)


class MockPopen(object):

    def __init__(self, output, return_codes=None):
        self.output = output
        self.stdout = StringIO(output)
        self.popen_inputs = []
        self.return_codes = return_codes

    def __call__(self, args, stdout=None, stderr=None):
        return self.popen(args, stdout=stdout, stderr=stderr)

    def popen(self, args, stdout=None, stderr=None):
        self.popen_inputs.append(args)
        return self

    def wait(self):
        if self.return_codes is None:
            return 0
        return self.return_codes.pop(0)


class StandardIOHelper(object):

    def set_up(self, test_case):
        from StringIO import StringIO

        test_case.old_stdout = sys.stdout
        test_case.old_stdin = sys.stdin
        test_case.stdout = sys.stdout = StringIO()
        test_case.stdin = sys.stdin = StringIO()
        test_case.stdin.encoding = "UTF-8"

    def tear_down(self, test_case):
        sys.stdout = test_case.old_stdout
        sys.stdin = test_case.old_stdin


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


def mock_counter(i=0):
    """Generator starts at zero and yields integers that grow by one."""
    while True:
        yield i
        i += 1


def mock_time():
    """Generator starts at 100 and yields int timestamps that grow by one."""
    return mock_counter(100)


class StubProcessFactory(object):
    """
    A L{IReactorProcess} provider which records L{spawnProcess} calls and
    allows tests to get at the protocol.
    """
    def __init__(self):
        self.spawns = []

    def spawnProcess(self, protocol, executable, args=(), env={}, path=None,
                    uid=None, gid=None, usePTY=0, childFDs=None):
        self.spawns.append((protocol, executable, args,
                            env, path, uid, gid, usePTY, childFDs))


class DummyProcess(object):
    """A process (transport) that doesn't do anything."""
    def __init__(self):
        self.signals = []

    def signalProcess(self, signal):
        self.signals.append(signal)

    def closeChildFD(self, fd):
        pass



class ProcessDataBuilder(object):
    """Builder creates sample data for the process info plugin to consume."""

    RUNNING = "R (running)"
    STOPPED = "T (stopped)"
    TRACING_STOP = "T (tracing stop)"
    DISK_SLEEP = "D (disk sleep)"
    SLEEPING = "S (sleeping)"
    DEAD = "X (dead)"
    ZOMBIE = "Z (zombie)"

    def __init__(self, sample_dir):
        """Initialize factory with directory for sample data."""
        self._sample_dir = sample_dir

    def create_data(self, process_id, state, uid, gid,
                    started_after_boot=0, process_name=None,
                    generate_cmd_line=True, stat_data=None, vmsize=11676):

        """Creates sample data for a process.

        @param started_after_boot: The amount of time, in jiffies,
            between the system uptime and start of the process.
        @param process_name: Used to generate the process name that appears in
            /proc/%(pid)s/status
        @param generate_cmd_line: If true, place the process_name in
            /proc/%(pid)s/cmdline, otherwise leave it empty (this simulates a
            kernel process)
        @param stat_data: Array of items to write to the /proc/<pid>/stat file.
        """
        sample_data = """
Name:   %(process_name)s
State:  %(state)s
Tgid:   24759
Pid:    24759
PPid:   17238
TracerPid:      0
Uid:    %(uid)d    0    0    0
Gid:    %(gid)d    0    0    0
FDSize: 256
Groups: 4 20 24 25 29 30 44 46 106 110 112 1000
VmPeak:    11680 kB
VmSize:    %(vmsize)d kB
VmLck:         0 kB
VmHWM:      6928 kB
VmRSS:      6924 kB
VmData:     1636 kB
VmStk:       196 kB
VmExe:      1332 kB
VmLib:      4240 kB
VmPTE:        20 kB
Threads:        1
SigQ:   0/4294967295
SigPnd: 0000000000000000
ShdPnd: 0000000000000000
SigBlk: 0000000000000000
SigIgn: 0000000000000000
SigCgt: 0000000059816eff
CapInh: 0000000000000000
CapPrm: 0000000000000000
CapEff: 0000000000000000
""" % ({"process_name": process_name[:15], "state": state, "uid": uid,
        "gid": gid, "vmsize": vmsize})
        process_dir = os.path.join(self._sample_dir, str(process_id))
        os.mkdir(process_dir)
        filename = os.path.join(process_dir, "status")

        file = open(filename, "w+")
        try:
            file.write(sample_data)
        finally:
            file.close()
        if stat_data is None:
            stat_data = """\
0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 %d\
""" % (started_after_boot,)
        filename = os.path.join(process_dir, "stat")

        file = open(filename, "w+")
        try:
            file.write(stat_data)
        finally:
            file.close()

        if generate_cmd_line:
            sample_data = """\
/usr/sbin/%(process_name)s\0--pid-file\0/var/run/%(process_name)s.pid\0
""" % {"process_name": process_name}
        else:
            sample_data = ""
        filename = os.path.join(process_dir, "cmdline")

        file = open(filename, "w+")
        try:
            file.write(sample_data)
        finally:
            file.close()

    def remove_data(self, process_id):
        """Remove sample data for the process that matches C{process_id}."""
        process_dir = os.path.join(self._sample_dir, str(process_id))
        shutil.rmtree(process_dir)



from twisted.python import log
from twisted.python import failure
from twisted.trial import reporter

def install_trial_hack():
    """
    Trial's TestCase in Twisted 2.2 had a bug which would prevent
    certain errors from being reported when being run in a non-trial
    test runner. This function monkeypatches trial to fix the bug, and
    only takes effect if using Twisted 2.2.
    """
    from twisted.trial.itrial import IReporter
    if "addError" in IReporter:
        # We have no need for this monkey patch with newer versions of Twisted.
        return
    def run(self, result):
        """
        Copied from twisted.trial.unittest.TestCase.run, but some
        lines from Twisted 2.5.
        """
        log.msg("--> %s <--" % (self.id()))

        # From Twisted 2.5
        if not isinstance(result, reporter.TestResult):
            result = PyUnitResultAdapter(result)
        # End from Twisted 2.5

        self._timedOut = False
        if self._shared and self not in self.__class__._instances:
            self.__class__._instances.add(self)
        result.startTest(self)
        if self.getSkip(): # don't run test methods that are marked as .skip
            result.addSkip(self, self.getSkip())
            result.stopTest(self)
            return
        # From twisted 2.5
        if hasattr(self, "_installObserver"):
            self._installObserver()
        # End from Twisted 2.5
        self._passed = False
        first = False
        if self._shared:
            first = self._isFirst()
            self.__class__._instancesRun.add(self)
        if first:
            d = self.deferSetUpClass(result)
        else:
            d = self.deferSetUp(None, result)
        try:
            self._wait(d)
        finally:
            self._cleanUp(result)
            result.stopTest(self)
            if self._shared and self._isLast():
                self._initInstances()
                self._classCleanUp(result)
            if not self._shared:
                self._classCleanUp(result)
    TestCase.run = run

### Copied from Twisted, to fix a bug in trial in Twisted 2.2! ###

class UnsupportedTrialFeature(Exception):
    """A feature of twisted.trial was used that pyunit cannot support."""


class PyUnitResultAdapter(object):
    """
    Wrap a C{TestResult} from the standard library's C{unittest} so that it
    supports the extended result types from Trial, and also supports
    L{twisted.python.failure.Failure}s being passed to L{addError} and
    L{addFailure}.
    """

    def __init__(self, original):
        """
        @param original: A C{TestResult} instance from C{unittest}.
        """
        self.original = original

    def _exc_info(self, err):
        if isinstance(err, failure.Failure):
            # Unwrap the Failure into a exc_info tuple.
            err = (err.type, err.value, err.tb)
        return err

    def startTest(self, method):
        # We'll need this later in cleanupErrors.
        self.__currentTest = method
        self.original.startTest(method)

    def stopTest(self, method):
        self.original.stopTest(method)

    def addFailure(self, test, fail):
        self.original.addFailure(test, self._exc_info(fail))

    def addError(self, test, error):
        self.original.addError(test, self._exc_info(error))

    def _unsupported(self, test, feature, info):
        self.original.addFailure(
            test,
            (UnsupportedTrialFeature,
             UnsupportedTrialFeature(feature, info),
             None))

    def addSkip(self, test, reason):
        """
        Report the skip as a failure.
        """
        self._unsupported(test, 'skip', reason)

    def addUnexpectedSuccess(self, test, todo):
        """
        Report the unexpected success as a failure.
        """
        self._unsupported(test, 'unexpected success', todo)

    def addExpectedFailure(self, test, error):
        """
        Report the expected failure (i.e. todo) as a failure.
        """
        self._unsupported(test, 'expected failure', error)

    def addSuccess(self, test):
        self.original.addSuccess(test)

    def upDownError(self, method, error, warn, printStatus):
        pass

    def cleanupErrors(self, errs):
        # Let's consider cleanupErrors as REAL errors. In recent
        # Twisted this is the default behavior, and cleanupErrors
        # isn't even called.
        self.addError(self.__currentTest, errs)

    def startSuite(self, name):
        pass

### END COPY FROM TWISTED ###

install_trial_hack()
