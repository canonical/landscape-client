import errno
import os
import socket as socket_module
from unittest import mock

from twisted.internet.error import CannotListenError, ConnectError
from twisted.internet.task import Clock

from landscape.client.amp import (
    ComponentConnector,
    ComponentPublisher,
    _remove_socket_file,
    _socket_has_no_live_listener,
    remote,
)
from landscape.client.deployment import Configuration
from landscape.client.reactor import LandscapeReactor
from landscape.client.tests.helpers import LandscapeTest, ready_subprocess
from landscape.lib.amp import MethodCallError
from landscape.lib.testing import FakeReactor


class MockComponent:
    name = "test"

    @remote
    def ping(self):
        return True

    def non_remote(self):
        return False


class MockComponentConnector(ComponentConnector):
    component = MockComponent


class FakeAMP:
    def __init__(self, locator):
        self._locator = locator


class ComponentPublisherTest(LandscapeTest):
    def setUp(self):
        super().setUp()
        reactor = FakeReactor()
        config = Configuration()
        config.data_path = self.makeDir()
        self.makeDir(path=config.sockets_path)
        self.component = MockComponent()
        self.publisher = ComponentPublisher(self.component, reactor, config)
        self.publisher.start()

        self.connector = MockComponentConnector(reactor, config)
        connected = self.connector.connect()
        connected.addCallback(lambda remote: setattr(self, "remote", remote))
        return connected

    def tearDown(self):
        self.connector.disconnect()
        self.publisher.stop()
        super().tearDown()

    def test_remote_methods(self):
        """Methods decorated with @remote are accessible remotely."""
        result = self.remote.ping()
        return self.assertSuccess(result, True)

    def test_protect_non_remote(self):
        """Methods not decorated with @remote are not accessible remotely."""
        result = self.remote.non_remote()
        failure = self.failureResultOf(result)
        self.assertTrue(failure.check(MethodCallError))


class ComponentPublisherStaleSocketTest(LandscapeTest):
    """The publisher recovers from a stale socket left by a dead process."""

    def setUp(self):
        super().setUp()
        self.config = Configuration()
        self.config.data_path = self.makeDir()
        self.makeDir(path=self.config.sockets_path)
        self.sock_path = os.path.join(self.config.sockets_path, "test.sock")

    def test_recovers_from_stale_socket(self):
        """A leftover socket with no live listener is removed and re-bound."""
        # Simulate a SIGKILLed component: a bound socket file with nobody
        # listening on it (close immediately, leaving the file behind).
        stale = socket_module.socket(socket_module.AF_UNIX, socket_module.SOCK_STREAM)
        stale.bind(self.sock_path)
        stale.close()
        self.assertTrue(os.path.exists(self.sock_path))

        # Test the actual Unix reactor implementation. Fakes won't do.
        reactor = LandscapeReactor()
        publisher = ComponentPublisher(MockComponent(), reactor, self.config)
        publisher.start()  # must not raise CannotListenError
        self.assertTrue(os.path.exists(self.sock_path))
        publisher.stop()
        reactor._cleanup()

    def test_refuses_socket_with_live_listener(self):
        """A socket still served by a live process is left untouched."""
        live = socket_module.socket(socket_module.AF_UNIX, socket_module.SOCK_STREAM)
        live.bind(self.sock_path)
        live.listen(1)
        self.addCleanup(live.close)

        reactor = LandscapeReactor()
        publisher = ComponentPublisher(MockComponent(), reactor, self.config)
        with self.assertRaises(CannotListenError):
            publisher.start()
        reactor._cleanup()


class ComponentConnectorTest(LandscapeTest):
    def setUp(self):
        super().setUp()
        self.reactor = FakeReactor()
        # XXX this should be dropped once the FakeReactor doesn't use the
        # real reactor anymore under the hood.
        self.reactor._reactor = Clock()
        self.config = Configuration()
        self.config.data_path = self.makeDir()
        self.makeDir(path=self.config.sockets_path)
        self.connector = MockComponentConnector(self.reactor, self.config)

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
            self.assertIn(
                "Error while connecting to test",
                self.logfile.getvalue(),
            )

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

        component = MockComponent()
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
        component = MockComponent()
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
        component = MockComponent()
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
        mock_kill.side_effect = [OSError(errno.ESRCH, "No such process")]
        sock_path = os.path.join(self.config.sockets_path, "test.sock")
        lock_path = f"{sock_path}.lock"
        # fake a PID which does not exist
        os.symlink("-1", lock_path)

        component = MockComponent()
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
            OSError(errno.EPERM, "Operation not permitted"),
        ]
        sock_path = os.path.join(self.config.sockets_path, "test.sock")
        lock_path = f"{sock_path}.lock"
        # fake a PID recycled by a known process which isn't landscape (init)
        os.symlink("1", lock_path)

        component = MockComponent()
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
        sock_path = os.path.join(self.config.sockets_path, "test.sock")
        lock_path = f"{sock_path}.lock"

        component = MockComponent()
        # Test the actual Unix reactor implementation. Fakes won't do.
        reactor = LandscapeReactor()
        publisher = ComponentPublisher(component, reactor, self.config)

        with ready_subprocess(self, "landscape-manager") as call:
            os.symlink(str(call.pid), lock_path)

            with self.assertRaises(CannotListenError):
                publisher.start()

            # ensure lock was not replaced
            self.assertEqual(str(call.pid), os.readlink(lock_path))
            mock_kill.assert_called_with(call.pid, 0)
            reactor._cleanup()


class SocketHasNoLiveListenerTest(LandscapeTest):
    def test_missing_path_has_no_listener(self):
        """A path that does not exist has no live listener."""
        path = os.path.join(self.makeDir(), "missing.sock")
        self.assertTrue(_socket_has_no_live_listener(path))

    def test_stale_socket_refusing_connection(self):
        """
        A socket file with nothing accepting connections raises OSError on
        connect and is reported as having no live listener.
        """
        path = os.path.join(self.makeDir(), "stale.sock")
        stale = socket_module.socket(
            socket_module.AF_UNIX,
            socket_module.SOCK_STREAM,
        )
        stale.bind(path)
        stale.close()
        self.assertTrue(os.path.exists(path))
        self.assertTrue(_socket_has_no_live_listener(path))

    def test_live_listener_is_detected(self):
        """A socket with a listener accepting connections is reported live."""
        path = os.path.join(self.makeDir(), "live.sock")
        live = socket_module.socket(
            socket_module.AF_UNIX,
            socket_module.SOCK_STREAM,
        )
        live.bind(path)
        live.listen(1)
        self.addCleanup(live.close)
        self.assertFalse(_socket_has_no_live_listener(path))


class RemoveSocketFileTest(LandscapeTest):
    def test_remove_socket_file(self):
        """A regular socket file is unlinked."""
        path = os.path.join(self.makeDir(), "test.sock")
        with open(path, "w"):
            pass
        self.assertTrue(os.path.exists(path))
        _remove_socket_file(path)
        self.assertFalse(os.path.exists(path))

    def test_remove_directory_left_behind(self):
        """A directory left in place of a socket is removed with rmdir."""
        path = os.path.join(self.makeDir(), "stale")
        os.mkdir(path)
        self.assertTrue(os.path.isdir(path))
        self.assertFalse(os.path.islink(path))
        _remove_socket_file(path)
        self.assertFalse(os.path.exists(path))

    def test_remove_symlink_to_directory(self):
        """A symlink pointing at a directory is unlinked rather than rmdir'd."""
        target = self.makeDir()
        path = os.path.join(self.makeDir(), "link")
        os.symlink(target, path)
        self.assertTrue(os.path.islink(path))
        _remove_socket_file(path)
        self.assertFalse(os.path.lexists(path))
        self.assertTrue(os.path.isdir(target))
