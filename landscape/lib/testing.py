import logging
import os
import os.path
import re
import shutil
import sys
import tempfile
import unittest


from logging import Handler, ERROR, Formatter
from twisted.trial.unittest import TestCase
from twisted.python.compat import StringType as basestring
from twisted.python.compat import _PY3
from twisted.python.failure import Failure
from twisted.internet.defer import Deferred

from landscape.lib.compat import ConfigParser
from landscape.lib.compat import stringio, cstringio
from landscape.lib.config import BaseConfiguration


class CompatTestCase(unittest.TestCase):

    if not _PY3:
        assertCountEqual = TestCase.assertItemsEqual


class HelperTestCase(unittest.TestCase):

    helpers = []

    def setUp(self):
        super(HelperTestCase, self).setUp()

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

        super(HelperTestCase, self).tearDown()


class FSTestCase(object):

    def assertFileContent(self, filename, expected_content):
        with open(filename, "rb") as fd:
            actual_content = fd.read()
        self.assertEqual(expected_content, actual_content)

    def makeFile(self, content=None, suffix="", prefix="tmp", basename=None,
                 dirname=None, path=None, mode="w", backupsuffix=None):
        """Create a temporary file and return the path to it.

        @param content: Initial content for the file.
        @param suffix: Suffix to be given to the file's basename.
        @param prefix: Prefix to be given to the file's basename.
        @param basename: Full basename for the file.
        @param dirname: Put file inside this directory.

        The file is removed after the test runs.
        """
        if basename is not None:
            if dirname is None:
                dirname = tempfile.mkdtemp()
            path = os.path.join(dirname, basename)
        elif path is None:
            fd, path = tempfile.mkstemp(suffix, prefix, dirname)
            os.close(fd)
            if content is None:
                os.unlink(path)
        if content is not None:
            with open(path, mode) as file:
                file.write(content)
        self.addCleanup(self._clean_file, path)

        if backupsuffix:

            def remove_backup():
                try:
                    os.remove(path + backupsuffix)
                except OSError:
                    pass
            self.addCleanup(remove_backup)

        return path

    def _clean_file(self, path):
        """Try to remove a filesystem path, whether it's a directory or file.

        @param path: the path to remove
        """
        try:
            if os.path.isdir(path):
                shutil.rmtree(path)
            else:
                os.unlink(path)
        except OSError:
            pass

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
        self.addCleanup(self._clean_file, path)
        return path

    def write_script(self, config, name, content, bindir=None):
        """Return the path to the script after writing it to a temp dir."""
        if bindir is None:
            bindir = self.makeDir()
        config.bindir = bindir
        filename = self.makeFile(
            content,
            dirname=bindir,
            basename=name)
        os.chmod(filename, 0o755)
        return filename


class ConfigTestCase(FSTestCase):

    def setUp(self):
        super(ConfigTestCase, self).setUp()

        self._old_config_filenames = BaseConfiguration.default_config_filenames
        BaseConfiguration.default_config_filenames = [self.makeFile("")]

    def tearDown(self):
        BaseConfiguration.default_config_filenames = self._old_config_filenames

        super(ConfigTestCase, self).tearDown()

    def assertConfigEqual(self, first, second):
        """
        Compare two configuration files for equality.  The order of parameters
        and comments may be different but the actual parameters and sections
        must be the same.
        """
        first_fp = cstringio(first)
        first_parser = ConfigParser()
        first_parser.readfp(first_fp)

        second_fp = cstringio(second)
        second_parser = ConfigParser()
        second_parser.readfp(second_fp)

        self.assertEqual(set(first_parser.sections()),
                         set(second_parser.sections()))
        for section in first_parser.sections():
            self.assertEqual(dict(first_parser.items(section)),
                             dict(second_parser.items(section)))


class TwistedTestCase(TestCase):

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
        test_case.logfile = cstringio()
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
                if (record.exc_info and record.exc_info[0] and
                    issubclass(record.exc_info[0], ignored_type)
                    ):
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


class MockPopen(object):

    def __init__(self, output, return_codes=None):
        self.output = output
        self.stdout = cstringio(output)
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
        test_case.old_stdout = sys.stdout
        test_case.old_stdin = sys.stdin
        test_case.stdout = sys.stdout = stringio()
        test_case.stdin = sys.stdin = stringio()
        if not _PY3:
            test_case.stdin.encoding = "UTF-8"

    def tear_down(self, test_case):
        sys.stdout = test_case.old_stdout
        sys.stdin = test_case.old_stdin


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
        "gid": gid, "vmsize": vmsize})  # noqa
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
