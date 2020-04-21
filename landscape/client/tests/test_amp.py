import os
import errno
import subprocess
import textwrap

import mock

from twisted.internet.error import ConnectError, CannotListenError
from twisted.internet.task import Clock

from landscape.client.tests.helpers import LandscapeTest
from landscape.client.deployment import Configuration
from landscape.client.amp import ComponentPublisher, ComponentConnector, remote
from landscape.client.reactor import LandscapeReactor
from landscape.lib.amp import MethodCallError
from landscape.lib.testing import FakeReactor


class TestComponent(object):

    name = "test"

    @remote
    def ping(self):
        return True

    def non_remote(self):
        return False


class TestComponentConnector(ComponentConnector):

    component = TestComponent


class FakeAMP(object):

    def __init__(self, locator):
        self._locator = locator


class ComponentPublisherTest(LandscapeTest):

    def setUp(self):
        super(ComponentPublisherTest, self).setUp()
        reactor = FakeReactor()
        config = Configuration()
        config.data_path = self.makeDir()
        self.makeDir(path=config.sockets_path)
        self.component = TestComponent()
        self.publisher = ComponentPublisher(self.component, reactor, config)
        self.publisher.start()

        self.connector = TestComponentConnector(reactor, config)
        connected = self.connector.connect()
        connected.addCallback(lambda remote: setattr(self, "remote", remote))
        return connected

    def tearDown(self):
        self.connector.disconnect()
        self.publisher.stop()
        super(ComponentPublisherTest, self).tearDown()

    def test_remote_methods(self):
        """Methods decorated with @remote are accessible remotely."""
        result = self.remote.ping()
        return self.assertSuccess(result, True)

    def test_protect_non_remote(self):
        """Methods not decorated with @remote are not accessible remotely."""
        result = self.remote.non_remote()
        failure = self.failureResultOf(result)
        self.assertTrue(failure.check(MethodCallError))


class ComponentConnectorTest(LandscapeTest):

    def setUp(self):
        super(ComponentConnectorTest, self).setUp()
        self.reactor = FakeReactor()
        # XXX this should be dropped once the FakeReactor doesn't use the
        # real reactor anymore under the hood.
        self.reactor._reactor = Clock()
        self.config = Configuration()
        self.config.data_path = self.makeDir()
        self.makeDir(path=self.config.sockets_path)
        self.connector = TestComponentConnector(self.reactor, self.config)

    def test_connect_with_max_retries(self):
        """
        If C{max_retries} is passed to L{RemoteObjectConnector.connect},
        then it will give up trying to connect after that amount of times.
        """
        self.log_helper.ignore_errors("Error while connecting to test")
        deferred = self.connector.connect(max_retries=2)
        self.assertNoResult(deferred)
        return
        self.failureResultOf(deferred).trap(ConnectError)

    def test_connect_logs_errors(self):
        """
        Connection errors are logged.
        """
        self.log_helper.ignore_errors("Error while connecting to test")

        def assert_log(ignored):
            self.assertIn("Error while connecting to test",
                          self.logfile.getvalue())

        result = self.connector.connect(max_retries=0)
        self.assertFailure(result, ConnectError)
        return result.addCallback(assert_log)

    def test_connect_with_quiet(self):
        """
        If the C{quiet} option is passed, no errors will be logged.
        """
        result = self.connector.connect(max_retries=0, quiet=True)
        return self.assertFailure(result, ConnectError)

    def test_reconnect_fires_event(self):
        """
        An event is fired whenever the connection is established again after
        it has been lost.
        """
        reconnects = []
        self.reactor.call_on("test-reconnect", lambda: reconnects.append(True))

        component = TestComponent()
        publisher = ComponentPublisher(component, self.reactor, self.config)
        publisher.start()
        deferred = self.connector.connect()
        self.successResultOf(deferred)
        self.connector._connector.disconnect()  # Simulate a disconnection
        self.assertEqual([], reconnects)
        self.reactor._reactor.advance(10)
        self.assertEqual([True], reconnects)

    def test_connect_with_factor(self):
        """
        If C{factor} is passed to the L{ComponentConnector.connect} method,
        then the associated protocol factory will be set to that value.
        """
        component = TestComponent()
        publisher = ComponentPublisher(component, self.reactor, self.config)
        publisher.start()
        deferred = self.connector.connect(factor=1.0)
        remote = self.successResultOf(deferred)
        self.assertEqual(1.0, remote._factory.factor)

    def test_disconnect(self):
        """
        It is possible to call L{ComponentConnector.disconnect} multiple times,
        even if the connection has been already closed.
        """
        component = TestComponent()
        publisher = ComponentPublisher(component, self.reactor, self.config)
        publisher.start()
        self.connector.connect()
        self.connector.disconnect()
        self.connector.disconnect()

    def test_disconnect_without_connect(self):
        """
        It is possible to call L{ComponentConnector.disconnect} even if the
        connection was never established. In that case the method is
        effectively a no-op.
        """
        self.connector.disconnect()

    @mock.patch("twisted.python.lockfile.kill")
    def test_stale_locks_with_dead_pid(self, mock_kill):
        """Publisher starts with stale lock."""
        mock_kill.side_effect = [
            OSError(errno.ESRCH, "No such process")]
        sock_path = os.path.join(self.config.sockets_path, u"test.sock")
        lock_path = u"{}.lock".format(sock_path)
        # fake a PID which does not exist
        os.symlink("-1", lock_path)

        component = TestComponent()
        # Test the actual Unix reactor implementation. Fakes won't do.
        reactor = LandscapeReactor()
        publisher = ComponentPublisher(component, reactor, self.config)

        # Shouldn't raise the exception.
        publisher.start()

        # ensure stale lock was replaced
        self.assertNotEqual("-1", os.readlink(lock_path))
        mock_kill.assert_called_with(-1, 0)

        publisher.stop()
        reactor._cleanup()

    @mock.patch("twisted.python.lockfile.kill")
    def test_stale_locks_recycled_pid(self, mock_kill):
        """Publisher starts with stale lock pointing to recycled process."""
        mock_kill.side_effect = [
            OSError(errno.EPERM, "Operation not permitted")]
        sock_path = os.path.join(self.config.sockets_path, u"test.sock")
        lock_path = u"{}.lock".format(sock_path)
        # fake a PID recycled by a known process which isn't landscape (init)
        os.symlink("1", lock_path)

        component = TestComponent()
        # Test the actual Unix reactor implementation. Fakes won't do.
        reactor = LandscapeReactor()
        publisher = ComponentPublisher(component, reactor, self.config)

        # Shouldn't raise the exception.
        publisher.start()

        # ensure stale lock was replaced
        self.assertNotEqual("1", os.readlink(lock_path))
        mock_kill.assert_not_called()
        self.assertFalse(publisher._port.lockFile.clean)

        publisher.stop()
        reactor._cleanup()

    @mock.patch("twisted.python.lockfile.kill")
    def test_with_valid_lock(self, mock_kill):
        """Publisher raises lock error if a valid lock is held."""
        sock_path = os.path.join(self.config.sockets_path, u"test.sock")
        lock_path = u"{}.lock".format(sock_path)
        # fake a landscape process
        app = self.makeFile(textwrap.dedent("""\
            #!/usr/bin/python3
            import time
            time.sleep(10)
        """), basename="landscape-manager")
        os.chmod(app, 0o755)
        call = subprocess.Popen([app])
        self.addCleanup(call.terminate)
        os.symlink(str(call.pid), lock_path)

        component = TestComponent()
        # Test the actual Unix reactor implementation. Fakes won't do.
        reactor = LandscapeReactor()
        publisher = ComponentPublisher(component, reactor, self.config)

        with self.assertRaises(CannotListenError):
            publisher.start()

        # ensure lock was not replaced
        self.assertEqual(str(call.pid), os.readlink(lock_path))
        mock_kill.assert_called_with(call.pid, 0)
        reactor._cleanup()
