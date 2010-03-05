import os

from twisted.internet.defer import Deferred
from twisted.internet.error import ConnectError

from landscape.tests.helpers import LandscapeTest
from landscape.reactor import FakeReactor
from landscape.deployment import Configuration
from landscape.amp import (
    LandscapeComponentFactory, RemoteLandscapeComponentCreator)


class TestComponent(object):

    name = "test"


class TestComponentFactory(LandscapeComponentFactory):

    maxRetries = 0
    initialDelay = 0.01


class RemoteTestComponentCreator(RemoteLandscapeComponentCreator):

    factory = TestComponentFactory
    component = TestComponent


class RemoteLandscapeComponentTest(LandscapeTest):

    def setUp(self):
        super(RemoteLandscapeComponentTest, self).setUp()
        reactor = FakeReactor()
        config = Configuration()
        config.data_path = self.makeDir()
        socket = os.path.join(config.data_path, "test.sock")
        self.component = TestComponent()
        factory = LandscapeComponentFactory(object=self.component)
        self.port = reactor.listen_unix(socket, factory)


        self.connector = RemoteTestComponentCreator(reactor, config)
        connected = self.connector.connect()
        connected.addCallback(lambda remote: setattr(self, "remote", remote))
        return connected

    def tearDown(self):
        self.connector.disconnect()
        self.port.stopListening()
        super(RemoteLandscapeComponentTest, self).tearDown()

    def test_ping(self):
        """
        The L{LandscapeComponentProtocol} exposes the C{ping} method of a
        remote Landscape component.
        """
        self.component.ping = self.mocker.mock()
        self.expect(self.component.ping()).result(True)
        self.mocker.replay()
        result = self.remote.ping()
        return self.assertSuccess(result, True)

    def test_exit(self):
        """
        The L{LandscapeComponentProtocol} exposes the C{exit} method of a
        remote Landscape component.
        """
        self.component.exit = self.mocker.mock()
        self.component.exit()
        self.mocker.replay()
        result = self.remote.exit()
        return self.assertSuccess(result)


class RemoteLandscapeComponentCreatorTest(LandscapeTest):

    def setUp(self):
        super(RemoteLandscapeComponentCreatorTest, self).setUp()
        self.reactor = FakeReactor()
        self.config = Configuration()
        self.config.data_path = self.makeDir()
        self.connector = RemoteTestComponentCreator(self.reactor, self.config)

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

    def test_reconnect_fires_event(self):
        """
        An event is fired whenever the connection is established again after
        it has been lost.
        """
        socket = os.path.join(self.config.data_path, "test.sock")
        factory = LandscapeComponentFactory()
        ports = []
        ports.append(self.reactor.listen_unix(socket, factory))

        def listen_again():
            ports.append(self.reactor.listen_unix(socket, factory))

        def connected(remote):
            remote._protocol.transport.loseConnection()
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
