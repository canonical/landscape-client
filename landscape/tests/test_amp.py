import os

from twisted.internet.defer import Deferred
from twisted.internet.error import ConnectError

from landscape.tests.helpers import LandscapeTest
from landscape.reactor import FakeReactor
from landscape.deployment import Configuration
from landscape.amp import ComponentProtocolFactory, RemoteComponentConnector


class TestComponent(object):

    name = "test"


class TestComponentProtocolFactory(ComponentProtocolFactory):

    maxRetries = 0
    initialDelay = 0.01


class RemoteTestComponentConnector(RemoteComponentConnector):

    factory = TestComponentProtocolFactory
    component = TestComponent


class RemoteComponentTest(LandscapeTest):

    def setUp(self):
        super(RemoteComponentTest, self).setUp()
        reactor = FakeReactor()
        config = Configuration()
        config.data_path = self.makeDir()
        self.makeDir(path=config.sockets_path)
        socket = os.path.join(config.sockets_path, "test.sock")
        self.component = TestComponent()
        factory = ComponentProtocolFactory(object=self.component)
        self.port = reactor.listen_unix(socket, factory)

        self.connector = RemoteTestComponentConnector(reactor, config)
        connected = self.connector.connect()
        connected.addCallback(lambda remote: setattr(self, "remote", remote))
        return connected

    def tearDown(self):
        self.connector.disconnect()
        self.port.stopListening()
        super(RemoteComponentTest, self).tearDown()

    def test_ping(self):
        """
        The L{ComponentProtocol} exposes the C{ping} method of a
        remote Landscape component.
        """
        self.component.ping = self.mocker.mock()
        self.expect(self.component.ping()).result(True)
        self.mocker.replay()
        result = self.remote.ping()
        return self.assertSuccess(result, True)

    def test_exit(self):
        """
        The L{ComponentProtocol} exposes the C{exit} method of a
        remote Landscape component.
        """
        self.component.exit = self.mocker.mock()
        self.component.exit()
        self.mocker.replay()
        result = self.remote.exit()
        return self.assertSuccess(result)


class RemoteComponentConnectorTest(LandscapeTest):

    def setUp(self):
        super(RemoteComponentConnectorTest, self).setUp()
        self.reactor = FakeReactor()
        self.config = Configuration()
        self.config.data_path = self.makeDir()
        self.makeDir(path=self.config.sockets_path)
        self.connector = RemoteTestComponentConnector(self.reactor,
                                                      self.config)

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
        socket = os.path.join(self.config.sockets_path, "test.sock")
        factory = ComponentProtocolFactory()
        ports = []
        ports.append(self.reactor.listen_unix(socket, factory))

        def listen_again():
            ports.append(self.reactor.listen_unix(socket, factory))

        def connected(remote):
            remote._sender.protocol.transport.loseConnection()
            ports[0].stopListening()
            self.reactor._reactor.callLater(0.01, listen_again)

        def reconnected():
            self.connector.disconnect()
            ports[1].stopListening()
            deferred.callback(None)

        deferred = Deferred()
        self.reactor.call_on("test-reconnect", reconnected)
        result = self.connector.connect()
        result.addCallback(connected)
        return deferred
