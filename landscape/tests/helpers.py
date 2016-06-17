from cStringIO import StringIO
from ConfigParser import ConfigParser
import logging
import shutil
import pprint
import re
import os
import sys
import tempfile
import unittest


from logging import Handler, ERROR, Formatter
from twisted.trial.unittest import TestCase
from twisted.python.failure import Failure
from twisted.internet.defer import Deferred

from landscape.tests.subunit import run_isolated
from landscape.watchdog import bootstrap_list

from landscape.lib.persist import Persist

from landscape.reactor import FakeReactor

from landscape.deployment import BaseConfiguration
from landscape.broker.config import BrokerConfiguration
from landscape.broker.transport import FakeTransport
from landscape.monitor.config import MonitorConfiguration
from landscape.monitor.monitor import Monitor
from landscape.manager.manager import Manager

from landscape.broker.service import BrokerService
from landscape.broker.amp import FakeRemoteBroker, RemoteBrokerConnector
from landscape.manager.config import ManagerConfiguration


DEFAULT_ACCEPTED_TYPES = [
    "accepted-types", "registration", "resynchronize", "set-id",
    "set-intervals", "unknown-id"]


class HelperTestCase(unittest.TestCase):

    helpers = []

    def setUp(self):
        self._helper_instances = []
        if LogKeeperHelper not in self.helpers:
            self.helpers.insert(0, LogKeeperHelper)
        result = None
        for helper_factory in self.helpers:
            helper = helper_factory()
            if hasattr(helper, "set_up"):
                result = helper.set_up(self)
            self._helper_instances.append(helper)
        # Return the return value of the last helper, which
        # might be a deferred
        return result

    def tearDown(self):
        for helper in reversed(self._helper_instances):
            if hasattr(helper, "tear_down"):
                helper.tear_down(self)


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


class LandscapeTest(MessageTestCase, HelperTestCase, TestCase):

    def setUp(self):
        self._old_config_filenames = BaseConfiguration.default_config_filenames
        BaseConfiguration.default_config_filenames = [self.makeFile("")]
        TestCase.setUp(self)
        return HelperTestCase.setUp(self)

    def tearDown(self):
        BaseConfiguration.default_config_filenames = self._old_config_filenames
        TestCase.tearDown(self)
        HelperTestCase.tearDown(self)

    def successResultOf(self, deferred):
        """See C{twisted.trial._synctest._Assertions.successResultOf}.

        This is a copy of the original method, which is available only
        since Twisted 12.3.0 (from 2012-12-20).
        """
        result = []
        deferred.addBoth(result.append)
        if not result:
            self.fail(
                "Success result expected on %r, found no result instead" % (
                    deferred,))
        elif isinstance(result[0], Failure):
            self.fail(
                "Success result expected on %r, "
                "found failure result (%r) instead" % (deferred, result[0]))
        else:
            return result[0]

    def failureResultOf(self, deferred):
        """See C{twisted.trial._synctest._Assertions.failureResultOf}.

        This is a copy of the original method, which is available only
        since Twisted 12.3.0 (from 2012-12-20).
        """
        result = []
        deferred.addBoth(result.append)
        if not result:
            self.fail(
                "Failure result expected on %r, found no result instead" % (
                    deferred,))
        elif not isinstance(result[0], Failure):
            self.fail(
                "Failure result expected on %r, "
                "found success result (%r) instead" % (deferred, result[0]))
        else:
            return result[0]

    def assertNoResult(self, deferred):
        """See C{twisted.trial._synctest._Assertions.assertNoResult}.

        This is a copy of the original method, which is available only
        since Twisted 12.3.0 (from 2012-12-20).
        """
        result = []
        deferred.addBoth(result.append)
        if result:
            self.fail(
                "No result expected on %r, found %r instead" % (
                    deferred, result[0]))

    def assertDeferredSucceeded(self, deferred):
        self.assertTrue(isinstance(deferred, Deferred))
        called = []

        def callback(result):
            called.append(True)
        deferred.addCallback(callback)
        self.assertTrue(called)

    def assertSuccess(self, deferred, result=None):
        """
        Assert that the given C{deferred} results in the given C{result}.
        """
        self.assertTrue(isinstance(deferred, Deferred))
        return deferred.addCallback(self.assertEqual, result)

    def assertFileContent(self, filename, expected_content):
        fd = open(filename)
        actual_content = fd.read()
        fd.close()
        self.assertEqual(expected_content, actual_content)

    def assertConfigEqual(self, first, second):
        """
        Compare two configuration files for equality.  The order of parameters
        and comments may be different but the actual parameters and sections
        must be the same.
        """
        first_fp = StringIO(first)
        first_parser = ConfigParser()
        first_parser.readfp(first_fp)

        second_fp = StringIO(second)
        second_parser = ConfigParser()
        second_parser.readfp(second_fp)

        self.assertEqual(set(first_parser.sections()),
                         set(second_parser.sections()))
        for section in first_parser.sections():
            self.assertEqual(dict(first_parser.items(section)),
                             dict(second_parser.items(section)))

    def makePersistFile(self, *args, **kwargs):
        """Return a temporary filename to be used by a L{Persist} object.

        The possible .old persist file is cleaned up after the test.
        """
        persist_filename = self.makeFile(*args, **kwargs)

        def remove_saved_persist():
            try:
                os.remove(persist_filename + ".old")
            except OSError:
                pass
        self.addCleanup(remove_saved_persist)
        return persist_filename

    def makeFile(self, content=None, suffix="", prefix="tmp", basename=None,
                 dirname=None, path=None):
        """Create a temporary file and return the path to it.

        @param content: Initial content for the file.
        @param suffix: Suffix to be given to the file's basename.
        @param prefix: Prefix to be given to the file's basename.
        @param basename: Full basename for the file.
        @param dirname: Put file inside this directory.

        The file is removed after the test runs.
        """
        if path is not None:
            self.addCleanup(shutil.rmtree, path, ignore_errors=True)
        elif basename is not None:
            if dirname is None:
                dirname = tempfile.mkdtemp()
                self.addCleanup(shutil.rmtree, dirname, ignore_errors=True)
            path = os.path.join(dirname, basename)
        else:
            fd, path = tempfile.mkstemp(suffix, prefix, dirname)
            self.addCleanup(shutil.rmtree, path, ignore_errors=True)
            os.close(fd)
            if content is None:
                os.unlink(path)
        if content is not None:
            file = open(path, "w")
            file.write(content)
            file.close()
        return path

    def makeDir(self, suffix="", prefix="tmp", dirname=None, path=None):
        """Create a temporary directory and return the path to it.

        @param suffix: Suffix to be given to the file's basename.
        @param prefix: Prefix to be given to the file's basename.
        @param dirname: Put directory inside this parent directory.

        The directory is removed after the test runs.
        """
        if path is not None:
            os.makedirs(path)
        else:
            path = tempfile.mkdtemp(suffix, prefix, dirname)
        self.addCleanup(shutil.rmtree, path, ignore_errors=True)
        return path


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
    """Builder creates sample data for the process info plugin to consume.

    @param sample_dir: The directory for sample data.
    """

    RUNNING = "R (running)"
    STOPPED = "T (stopped)"
    TRACING_STOP = "T (tracing stop)"
    DISK_SLEEP = "D (disk sleep)"
    SLEEPING = "S (sleeping)"
    DEAD = "X (dead)"
    ZOMBIE = "Z (zombie)"

    def __init__(self, sample_dir):
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


class FakePersist(object):
    """
    Incompletely fake a C{landscape.lib.Persist} to simplify higher level tests
    that result in an attempt to clear down persisted data.
    """

    def __init__(self):
        self.called = False

    def remove(self, key):
        self.called = True
