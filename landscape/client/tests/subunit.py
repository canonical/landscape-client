#
# subunit: extensions to python unittest to get test results from subprocesses.
# Copyright (C) 2005  Robert Collins <robertc@robertcollins.net>
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA
#
import os
import subprocess
import sys
import unittest

from landscape.lib.compat import StringIO


def test_suite():
    import subunit.tests

    return subunit.tests.test_suite()


def join_dir(base_path, path):
    """
    Returns an absolute path to C{path}, calculated relative to the parent
    of C{base_path}.

    @param base_path: A path to a file or directory.
    @param path: An absolute path, or a path relative to the containing
    directory of C{base_path}.

    @return: An absolute path to C{path}.
    """
    return os.path.join(os.path.dirname(os.path.abspath(base_path)), path)


class TestProtocolServer:
    """A class for receiving results from a TestProtocol client."""

    OUTSIDE_TEST = 0
    TEST_STARTED = 1
    READING_FAILURE = 2
    READING_ERROR = 3

    def __init__(self, client, stream=sys.stdout):
        """Create a TestProtocol server instance.

        client should be an object that provides
         - starttest
         - addsuccess
         - addfailure
         - adderror
         - stoptest
        methods, i.e. a TestResult.
        """
        self.state = TestProtocolServer.OUTSIDE_TEST
        self.client = client
        self._stream = stream

    def _adderror(self, offset, line):
        if (
            self.state == TestProtocolServer.TEST_STARTED
            and self.current_test_description == line[offset:-1]
        ):

            self.state = TestProtocolServer.OUTSIDE_TEST
            self.current_test_description = None
            self.client.adderror(self._current_test, RemoteError(""))
            self.client.stopTest(self._current_test)
            self._current_test = None
        elif (
            self.state == TestProtocolServer.TEST_STARTED
            and self.current_test_description + " [" == line[offset:-1]
        ):
            self.state = TestProtocolServer.READING_ERROR
            self._message = ""
        else:
            self.stdoutlinereceived(line)

    def _addfailure(self, offset, line):
        if (
            self.state == TestProtocolServer.TEST_STARTED
            and self.current_test_description == line[offset:-1]
        ):

            self.state = TestProtocolServer.OUTSIDE_TEST
            self.current_test_description = None
            self.client.addfailure(self._current_test, RemoteError())
            self.client.stopTest(self._current_test)
        elif (
            self.state == TestProtocolServer.TEST_STARTED
            and self.current_test_description + " [" == line[offset:-1]
        ):
            self.state = TestProtocolServer.READING_FAILURE
            self._message = ""
        else:
            self.stdoutlinereceived(line)

    def _addsuccess(self, offset, line):
        if (
            self.state == TestProtocolServer.TEST_STARTED
            and self.current_test_description == line[offset:-1]
        ):

            self.client.addsuccess(self._current_test)
            self.client.stopTest(self._current_test)
            self.current_test_description = None
            self._current_test = None
            self.state = TestProtocolServer.OUTSIDE_TEST
        else:
            self.stdoutlinereceived(line)

    def _appendmessage(self, line):
        if line[0:2] == " ]":
            # quoted ] start
            self._message += line[1:]
        else:
            self._message += line

    def endquote(self, line):
        if self.state == TestProtocolServer.READING_FAILURE:
            self.state = TestProtocolServer.OUTSIDE_TEST
            self.current_test_description = None
            self.client.addfailure(
                self._current_test,
                RemoteError(self._message),
            )
            self.client.stopTest(self._current_test)
        elif self.state == TestProtocolServer.READING_ERROR:
            self.state = TestProtocolServer.OUTSIDE_TEST
            self.current_test_description = None
            self.client.adderror(
                self._current_test,
                RemoteError(self._message),
            )
            self.client.stopTest(self._current_test)
        else:
            self.stdoutlinereceived(line)

    def linereceived(self, line):
        """Call the appropriate local method for the received line."""
        if line == "]\n":
            self.endquote(line)
        elif (
            self.state == TestProtocolServer.READING_FAILURE
            or self.state == TestProtocolServer.READING_ERROR
        ):
            self._appendmessage(line)
        else:
            parts = line.split(None, 1)
            if len(parts) == 2:
                cmd, rest = parts
                offset = len(cmd) + 1
                cmd = cmd.strip(":")
                if cmd in ("test", "testing"):
                    self._starttest(offset, line)
                elif cmd == "error":
                    self._adderror(offset, line)
                elif cmd == "failure":
                    self._addfailure(offset, line)
                elif cmd in ("success", "successful"):
                    self._addsuccess(offset, line)
                else:
                    self.stdoutLinereceived(line)
            else:
                self.stdOutLinereceived(line)

    def lostconnection(self):
        """The input connection has finished."""
        if self.state == TestProtocolServer.TEST_STARTED:
            self.client.adderror(
                self._current_test,
                RemoteError(
                    "lost connection during test "
                    f"'{self.current_test_description}'",
                ),
            )
            self.client.stopTest(self._current_test)
        elif self.state == TestProtocolServer.READING_ERROR:
            self.client.adderror(
                self._current_test,
                RemoteError(
                    "lost connection during "
                    "error report of test "
                    f"'{self.current_test_description}'",
                ),
            )
            self.client.stopTest(self._current_test)
        elif self.state == TestProtocolServer.READING_FAILURE:
            self.client.adderror(
                self._current_test,
                RemoteError(
                    "lost connection during "
                    "failure report of test "
                    f"'{self.current_test_description}'",
                ),
            )
            self.client.stopTest(self._current_test)

    def readfrom(self, pipe):
        for line in pipe.readlines():
            self.linereceived(line)
        self.lostconnection()

    def _starttest(self, offset, line):
        """Internal call to change state machine. Override starttest()."""
        if self.state == TestProtocolServer.OUTSIDE_TEST:
            self.state = TestProtocolServer.TEST_STARTED
            self._current_test = RemotedTestCase(line[offset:-1])
            self.current_test_description = line[offset:-1]
            self.client.startTest(self._current_test)
        else:
            self.stdoutlinereceived(line)

    def stdoutlinereceived(self, line):
        self._stream.write(line)


class RemoteException(Exception):
    """An exception that occured remotely to python."""

    def __eq__(self, other):
        try:
            return self.args == other.args
        except AttributeError:
            return False


class TestProtocolClient(unittest.TestResult):
    """Looks like a TestResult and informs a TestProtocolServer."""

    def __init__(self, stream):
        unittest.TestResult.__init__(self)
        self._stream = stream

    def adderror(self, test, error):
        """Report an error in test test."""
        self._stream.write(f"error: {test.shortDescription()} [\n")
        for line in self._exc_info_to_string(error, test).splitlines():
            self._stream.write(f"{line}\n")
        self._stream.write("]\n")

    def addfailure(self, test, error):
        """Report a failure in test test."""
        self._stream.write(f"failure: {test.shortDescription()} [\n")
        for line in self._exc_info_to_string(error, test).splitlines():
            self._stream.write(f"{line}\n")
        self._stream.write("]\n")

    def addsuccess(self, test):
        """Report a success in a test."""
        self._stream.write(f"successful: {test.shortDescription()}\n")

    def starttest(self, test):
        """Mark a test as starting its test run."""
        self._stream.write(f"test: {test.shortDescription()}\n")


def RemoteError(description=""):  # noqa: N802
    if description == "":
        description = "\n"
    return (RemoteException, RemoteException(description), None)


class RemotedTestCase(unittest.TestCase):
    """A class to represent test cases run in child processes."""

    def __eq__(self, other):
        try:
            return self.__description == other.__description
        except AttributeError:
            return False

    def __init__(self, description):
        """Create a psuedo test case with description description."""
        self.__description = description

    def error(self, label):
        raise NotImplementedError(
            f"{label} on RemotedTestCases is not permitted.",
        )

    def setUp(self):
        self.error("setUp")

    def tearDown(self):
        self.error("tearDown")

    def shortDescription(self):  # noqa: N802
        return self.__description

    def id(self):
        return f"{self._strclass()}.{self.__description}"

    def __str__(self):
        return f"{self.__description} ({self._strclass()})"

    def __repr__(self):
        return f"<{self._strclass()} description='{self.__description}'>"

    def run(self, result=None):
        if result is None:
            result = self.defaultTestResult()
        result.starttest(self)
        result.adderror(self, RemoteError("Cannot run RemotedTestCases.\n"))
        result.stopTest(self)

    def _strclass(self):
        cls = self.__class__
        return f"{cls.__module__}.{cls.__name__}"


class ExecTestCase(unittest.TestCase):
    """A test case which runs external scripts for test fixtures."""

    def __init__(self, methodName="runTest"):  # noqa: N803
        """Create an instance of the class that will use the named test
        method when executed. Raises a ValueError if the instance does
        not have a method with the specified name.
        """
        unittest.TestCase.__init__(self, methodName)
        testmethod = getattr(self, methodName)
        self.script = join_dir(
            sys.modules[self.__class__.__module__].__file__,
            testmethod.__doc__,
        )

    def countTestCases(self):  # noqa: N802
        return 1

    def run(self, result=None):
        if result is None:
            result = self.defaultTestResult()
        self._run(result)

    def debug(self):
        """Run the test without collecting errors in a TestResult"""
        self._run(unittest.TestResult())

    def _run(self, result):
        protocol = TestProtocolServer(result)
        output = subprocess.Popen(
            [self.script],
            stdout=subprocess.PIPE,
        ).communicate()[0]
        protocol.readfrom(StringIO(output))


class IsolatedTestCase(unittest.TestCase):
    """A TestCase which runs its tests in a forked process."""

    def run(self, result=None):
        if result is None:
            result = self.defaultTestResult()
        run_isolated(unittest.TestCase, self, result)


class IsolatedTestSuite(unittest.TestSuite):
    """A TestCase which runs its tests in a forked process."""

    def run(self, result=None):
        if result is None:
            result = unittest.TestResult()
        run_isolated(unittest.TestSuite, self, result)


def run_isolated(klass, self, result):
    """Test suite or case in a subprocess, using the run method on klass."""
    c2pread, c2pwrite = os.pipe()
    # fixme - error -> result
    # now fork
    pid = os.fork()
    if pid == 0:
        # Child
        # Close parent's pipe ends
        os.close(c2pread)
        # Dup fds for child
        os.dup2(c2pwrite, 1)
        # Close pipe fds.
        os.close(c2pwrite)

        # at this point, sys.stdin is redirected, now we want
        # to filter it to escape ]'s.
        # XXX: test and write that bit.

        result = TestProtocolClient(sys.stdout)
        klass.run(self, result)
        sys.stdout.flush()
        sys.stderr.flush()
        # exit HARD, exit NOW.
        os._exit(0)
    else:
        # Parent
        # Close child pipe ends
        os.close(c2pwrite)
        # hookup a protocol engine
        protocol = TestProtocolServer(result)
        protocol.readfrom(os.fdopen(c2pread, "rU"))
        os.waitpid(pid, 0)
        # TODO return code evaluation.
    return result
