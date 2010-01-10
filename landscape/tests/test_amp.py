import os

from twisted.internet.error import ConnectError

from landscape.tests.helpers import LandscapeTest
from landscape.reactor import FakeReactor
from landscape.deployment import Configuration
from landscape.amp import (
    LandscapeComponentServerFactory, LandscapeComponentClientFactory,
    RemoteLandscapeComponentCreator)


class TestComponent(object):
    pass


class TestComponentClientFactory(LandscapeComponentClientFactory):

    maxRetries = 0


class RemoteTestComponentCreator(RemoteLandscapeComponentCreator):

    factory = TestComponentClientFactory
    socket = "test.sock"


class RemoteLandscapeComponentTest(LandscapeTest):

    def setUp(self):
        super(RemoteLandscapeComponentTest, self).setUp()
        reactor = FakeReactor()
        config = Configuration()
        config.data_path = self.makeDir()
        socket = os.path.join(config.data_path, "test.sock")
        self.component = TestComponent()
        factory = LandscapeComponentServerFactory(self.component)
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
        reactor = FakeReactor()
        config = Configuration()
        config.data_path = self.makeDir()
        self.connector = RemoteTestComponentCreator(reactor, config)

    def test_connect_logs_errors(self):
        """
        Connection errors are logged.
        """
        self.log_helper.ignore_errors("Error while trying to connect test")

        def assert_log(ignored):
            self.assertIn("Error while trying to connect test",
                          self.logfile.getvalue())

        result = self.connector.connect(max_retries=0)
        self.assertFailure(result, ConnectError)
        return result.addCallback(assert_log)
