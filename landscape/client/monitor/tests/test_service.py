from mock import Mock

from landscape.lib.testing import FakeReactor
from landscape.client.tests.helpers import (
        LandscapeTest, FakeBrokerServiceHelper)
from landscape.client.monitor.config import MonitorConfiguration, ALL_PLUGINS
from landscape.client.monitor.service import MonitorService
from landscape.client.monitor.computerinfo import ComputerInfo
from landscape.client.monitor.loadaverage import LoadAverage


class MonitorServiceTest(LandscapeTest):

    helpers = [FakeBrokerServiceHelper]

    def setUp(self):
        super(MonitorServiceTest, self).setUp()
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
        self.service.config.load(["--monitor-plugins",
                                  "ComputerInfo, LoadAverage"])
        plugins = self.service.get_plugins()
        self.assertTrue(isinstance(plugins[0], ComputerInfo))
        self.assertTrue(isinstance(plugins[1], LoadAverage))

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
