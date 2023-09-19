from unittest.mock import Mock
from unittest.mock import patch

from landscape.client.monitor.computerinfo import ComputerInfo
from landscape.client.monitor.config import ALL_PLUGINS
from landscape.client.monitor.config import MonitorConfiguration
from landscape.client.monitor.loadaverage import LoadAverage
from landscape.client.monitor.service import MonitorService
from landscape.client.tests.helpers import FakeBrokerServiceHelper
from landscape.client.tests.helpers import LandscapeTest
from landscape.lib.testing import FakeReactor


class MonitorServiceTest(LandscapeTest):

    helpers = [FakeBrokerServiceHelper]

    def setUp(self):
        super().setUp()
        config = MonitorConfiguration()
        config.load(["-c", self.config_filename])

        class FakeMonitorService(MonitorService):
            reactor_factory = FakeReactor

        self.service = FakeMonitorService(config)
        self.log_helper.ignore_errors("Typelib file for namespace")

    def test_plugins(self):
        """
        By default the L{MonitorService.plugins} list holds an instance of
        every enabled monitor plugin.
        """
        self.assertEqual(len(self.service.plugins), len(ALL_PLUGINS))

    def test_get_plugins(self):
        """
        If the C{--monitor-plugins} command line option is specified, only the
        given plugins will be enabled.
        """
        self.service.config.load(
            ["--monitor-plugins", "ComputerInfo, LoadAverage"],
        )
        plugins = self.service.get_plugins()
        self.assertTrue(isinstance(plugins[0], ComputerInfo))
        self.assertTrue(isinstance(plugins[1], LoadAverage))

    def test_get_plugins_module_not_found(self):
        """If a module is not found, a warning is logged."""
        self.service.config.load(["--monitor-plugins", "TotallyDoesNotExist"])

        with self.assertLogs(level="WARN") as cm:
            plugins = self.service.get_plugins()

        self.assertEqual(len(plugins), 0)
        self.assertIn("Invalid monitor plugin", cm.output[0])
        self.assertIn("TotallyDoesNotExist", cm.output[0])

    def test_get_plugins_other_exception(self):
        """If loading a plugin fails for another reason, a warning is logged,
        with the exception.
        """
        self.service.config.load(["--monitor-plugins", "ComputerInfo"])

        with self.assertLogs(level="WARN") as cm:
            with patch(
                "landscape.client.monitor.service.namedClass",
            ) as namedClass:
                namedClass.side_effect = Exception("Is there life on Mars?")
                plugins = self.service.get_plugins()

        self.assertEqual(len(plugins), 0)
        self.assertIn("Unable to load", cm.output[0])
        self.assertIn("Mars?", cm.output[0])

    def test_start_service(self):
        """
        The L{MonitorService.startService} method connects to the broker,
        starts the plugins and register the monitor as broker client.  It also
        start listening on its own socket for incoming connections.
        """

        def stop_service(ignored):
            [connector] = self.broker_service.broker.get_connectors()
            connector.disconnect()
            self.service.stopService()
            self.broker_service.stopService()

        def assert_broker_connection(ignored):
            self.assertEqual(len(self.broker_service.broker.get_clients()), 1)
            self.assertIs(self.service.broker, self.service.monitor.broker)
            result = self.service.broker.ping()
            return result.addCallback(stop_service)

        self.broker_service.startService()
        started = self.service.startService()
        return started.addCallback(assert_broker_connection)

    def test_stop_service(self):
        """
        The L{MonitorService.stopService} method flushes the data before
        shutting down the monitor, and closes the connection with the broker.
        """
        self.service.monitor = Mock()
        self.service.connector = Mock()
        self.service.publisher = Mock()
        self.service.stopService()
        self.service.monitor.flush.assert_called_once_with()
        self.service.connector.disconnect.assert_called_once_with()
        self.service.publisher.stop.assert_called_once_with()
