from unittest import mock

from landscape.client.manager.config import ALL_PLUGINS
from landscape.client.manager.config import ManagerConfiguration
from landscape.client.manager.processkiller import ProcessKiller
from landscape.client.manager.service import ManagerService
from landscape.client.tests.helpers import FakeBrokerServiceHelper
from landscape.client.tests.helpers import LandscapeTest
from landscape.lib.testing import FakeReactor


class ManagerServiceTest(LandscapeTest):

    helpers = [FakeBrokerServiceHelper]

    class FakeManagerService(ManagerService):
        reactor_factory = FakeReactor

    def setUp(self):
        super().setUp()
        config = ManagerConfiguration()
        config.load(["-c", self.config_filename])

        self.service = self.FakeManagerService(config)

    @mock.patch("dbus.SystemBus")
    def test_plugins(self, system_bus_mock):
        """
        By default the L{ManagerService.plugins} list holds an instance of
        every enabled manager plugin.

        We mock `dbus` because in some build environments that run these tests,
        such as buildd, SystemBus is not available.
        """
        config = ManagerConfiguration()
        config.load(["-c", self.config_filename])
        service = self.FakeManagerService(config)

        self.assertEqual(len(service.plugins), len(ALL_PLUGINS))
        system_bus_mock.assert_called_once_with()

    def test_get_plugins(self):
        """
        If the C{--manager-plugins} command line option is specified, only the
        given plugins will be enabled.
        """
        self.service.config.load(["--manager-plugins", "ProcessKiller"])
        [plugin] = self.service.get_plugins()
        self.assertTrue(isinstance(plugin, ProcessKiller))

    def test_get_plugins_module_not_found(self):
        """If a module is not found, a warning is logged."""
        self.service.config.load(["--manager-plugins", "TotallyDoesNotExist"])

        with self.assertLogs(level="WARN") as cm:
            plugins = self.service.get_plugins()

        self.assertEqual(len(plugins), 0)
        self.assertIn("Invalid manager plugin", cm.output[0])
        self.assertIn("TotallyDoesNotExist", cm.output[0])

    def test_get_plugins_other_exception(self):
        """If loading a plugin fails for another reason, a warning is logged,
        with the exception.
        """
        self.service.config.load(["--manager-plugins", "ProcessKiller"])

        with self.assertLogs(level="WARN") as cm:
            with mock.patch(
                "landscape.client.manager.service.namedClass",
            ) as namedClass:
                namedClass.side_effect = Exception("Is there life on Mars?")
                plugins = self.service.get_plugins()

        self.assertEqual(len(plugins), 0)
        self.assertIn("Unable to load", cm.output[0])
        self.assertIn("Mars?", cm.output[0])

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
