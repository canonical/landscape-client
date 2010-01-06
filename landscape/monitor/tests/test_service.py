from landscape.tests.mocker import ANY
from landscape.tests.helpers import (
    LandscapeTest, BrokerServiceHelper, RemoteBrokerHelper_)
from landscape.reactor import FakeReactor
from landscape.monitor.config import MonitorConfiguration, ALL_PLUGINS
from landscape.monitor.service import MonitorService
from landscape.monitor.computerinfo import ComputerInfo
from landscape.monitor.loadaverage import LoadAverage


class MonitorServiceTest(LandscapeTest):

    helpers = [BrokerServiceHelper, RemoteBrokerHelper_]

    def setUp(self):

        def set_service(ignored):
            config = MonitorConfiguration()
            config.load(["-c", self.config_filename])
            MonitorService.reactor_factory = FakeReactor
            self.service = MonitorService(config)

        broker_started = super(MonitorServiceTest, self).setUp()
        return broker_started.addCallback(set_service)

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
        starts the plugins and register the monitor as broker client.
        """
        # FIXME: don't actually run the real register method, because at the
        # moment the UserMonitor plugin still depends on DBus. We can probably
        # drop this mocking once the AMP migration is completed.
        for plugin in self.service.plugins:
            plugin.register = self.mocker.mock()
            plugin.register(ANY)
        self.mocker.replay()

        def assert_broker_connection(ignored):

            self.assertEquals(len(self.service.monitor.get_plugins()),
                              len(ALL_PLUGINS))
            [client] = self.broker_service.broker.get_clients()
            self.assertEquals(client.name, "monitor")
            result = self.service.broker.ping()
            result.addCallback(lambda x: self.service.creator.disconnect())
            return result

        started = self.service.startService()
        return started.addCallback(assert_broker_connection)

    def test_stop_service(self):
        """
        The L{MonitorService.stopService} method flushes the data before
        shutting down the monitor, and closes the connection with the broker.
        """
        self.service.monitor = self.mocker.mock()
        self.service.monitor.flush()
        self.service.creator = self.mocker.mock()
        self.service.creator.disconnect()
        self.mocker.replay()
        self.service.stopService()
