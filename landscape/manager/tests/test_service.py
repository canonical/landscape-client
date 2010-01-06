from landscape.tests.mocker import ANY
from landscape.tests.helpers import (
    LandscapeTest, BrokerServiceHelper, RemoteBrokerHelper_)
from landscape.reactor import FakeReactor
from landscape.manager.config import ManagerConfiguration, ALL_PLUGINS
from landscape.manager.service import ManagerService
from landscape.manager.processkiller import ProcessKiller


class ManagerServiceTest(LandscapeTest):

    helpers = [BrokerServiceHelper, RemoteBrokerHelper_]

    def setUp(self):

        def set_service(ignored):
            config = ManagerConfiguration()
            config.load(["-c", self.config_filename])
            ManagerService.reactor_factory = FakeReactor
            self.service = ManagerService(config)

        broker_started = super(ManagerServiceTest, self).setUp()
        return broker_started.addCallback(set_service)

    def test_plugins(self):
        """
        By default the L{ManagerService.plugins} list holds an instance of
        every enabled manager plugin.
        """
        self.assertEquals(len(self.service.plugins), len(ALL_PLUGINS))

    def test_get_plugins(self):
        """
        If the C{--manager-plugins} command line option is specified, only the
        given plugins will be enabled.
        """
        self.service.config.load(["--manager-plugins", "ProcessKiller"])
        [plugin] = self.service.get_plugins()
        self.assertTrue(isinstance(plugin, ProcessKiller))

    def test_start_service(self):
        """
        The L{ManagerService.startService} method connects to the broker,
        starts the plugins and register the manager as broker client.
        """
        # FIXME: don't actually run the real register method, because at the
        # moment the UserManager plugin still depends on DBus. We can probably
        # drop this mocking once the AMP migration is completed.
        for plugin in self.service.plugins:
            plugin.register = self.mocker.mock()
            plugin.register(ANY)
        self.mocker.replay()

        def assert_broker_connection(ignored):

            self.assertEquals(len(self.service.manager.get_plugins()),
                              len(ALL_PLUGINS))
            [client] = self.broker_service.broker.get_clients()
            self.assertEquals(client.name, "manager")
            result = self.service.broker.ping()
            result.addCallback(lambda x: self.service.stopService())
            return result

        started = self.service.startService()
        return started.addCallback(assert_broker_connection)
