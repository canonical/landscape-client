from landscape.tests.mocker import ANY
from landscape.tests.helpers import LandscapeTest, FakeBrokerServiceHelper
from landscape.reactor import FakeReactor
from landscape.monitor.config import MonitorConfiguration, ALL_PLUGINS
from landscape.monitor.service import MonitorService
from landscape.monitor.computerinfo import ComputerInfo
from landscape.monitor.loadaverage import LoadAverage


class MonitorServiceTest(LandscapeTest):

    helpers = [FakeBrokerServiceHelper]

    def setUp(self):
        super(MonitorServiceTest, self).setUp()
        config = MonitorConfiguration()
        config.load(["-c", self.config_filename])

        class FakeMonitorService(MonitorService):
            reactor_factory = FakeReactor

        self.service = FakeMonitorService(config)

    def test_plugins(self):
        """
        By default the L{MonitorService.plugins} list holds an instance of
        every enabled monitor plugin.
        """
        self.assertEquals(len(self.service.plugins), len(ALL_PLUGINS))

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
        # FIXME: don't actually run the real register method, because at the
        # moment the UserMonitor plugin still depends on DBus. We can probably
        # drop this mocking once the AMP migration is completed.
        for plugin in self.service.plugins:
            plugin.register = self.mocker.mock()
            plugin.register(ANY)
        self.mocker.replay()

        def stop_service(ignored):
            [connector] = self.broker_service.broker.get_connectors()
            connector.disconnect()
            self.service.stopService()
            self.broker_service.stopService()

        def assert_broker_connection(ignored):
            self.assertEquals(len(self.broker_service.broker.get_clients()), 1)
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
        self.service.monitor = self.mocker.mock()
        self.service.monitor.flush()
        self.service.connector = self.mocker.mock()
        self.service.connector.disconnect()
        self.service.port = self.mocker.mock()
        self.service.port.stopListening()
        self.mocker.replay()
        self.service.stopService()
