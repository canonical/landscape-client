from landscape.client.tests.helpers import (
    LandscapeTest, FakeBrokerServiceHelper)
from landscape.lib.testing import FakeReactor
from landscape.client.manager.config import ManagerConfiguration, ALL_PLUGINS
from landscape.client.manager.service import ManagerService
from landscape.client.manager.processkiller import ProcessKiller


class ManagerServiceTest(LandscapeTest):

    helpers = [FakeBrokerServiceHelper]

    def setUp(self):
        super(ManagerServiceTest, self).setUp()
        config = ManagerConfiguration()
        config.load(["-c", self.config_filename])

        class FakeManagerService(ManagerService):
            reactor_factory = FakeReactor

        self.service = FakeManagerService(config)

    def test_plugins(self):
        """
        By default the L{ManagerService.plugins} list holds an instance of
        every enabled manager plugin.
        """
        self.assertEqual(len(self.service.plugins), len(ALL_PLUGINS))

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
        def stop_service(ignored):
            for plugin in self.service.plugins:
                if getattr(plugin, "stop", None) is not None:
                    plugin.stop()
            [connector] = self.broker_service.broker.get_connectors()
            connector.disconnect()
            self.service.stopService()
            self.broker_service.stopService()

        def assert_broker_connection(ignored):
            self.assertEqual(len(self.broker_service.broker.get_clients()), 1)
            self.assertIs(self.service.broker, self.service.manager.broker)
            result = self.service.broker.ping()
            return result.addCallback(stop_service)

        self.broker_service.startService()
        started = self.service.startService()
        return started.addCallback(assert_broker_connection)
