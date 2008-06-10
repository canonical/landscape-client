from landscape.lib.persist import Persist
from landscape.reactor import FakeReactor
from landscape.monitor.computerinfo import ComputerInfo
from landscape.monitor.loadaverage import LoadAverage
from landscape.monitor.deployment import MonitorService, MonitorConfiguration
from landscape.tests.helpers import (
    LandscapeTest, LandscapeIsolatedTest, RemoteBrokerHelper)
from landscape.broker.tests.test_remote import assertTransmitterActive
from landscape.tests.test_plugin import assertReceivesMessages


class DeploymentTest(LandscapeTest):

    def test_get_plugins(self):
        configuration = MonitorConfiguration()
        configuration.load(["--monitor-plugins", "ComputerInfo, LoadAverage",
                            "-d", self.make_path()])
        monitor = MonitorService(configuration)
        plugins = monitor.plugins
        self.assertEquals(len(plugins), 2)
        self.assertTrue(isinstance(plugins[0], ComputerInfo))
        self.assertTrue(isinstance(plugins[1], LoadAverage))

    def test_get_all_plugins(self):
        configuration = MonitorConfiguration()
        configuration.load(["--monitor-plugins", "ALL",
                            "-d", self.make_path()])
        monitor = MonitorService(configuration)
        plugins = monitor.plugins
        self.assertEquals(len(plugins), 10)


class MonitorServiceTest(LandscapeIsolatedTest):

    helpers = [RemoteBrokerHelper]

    def setUp(self):
        super(MonitorServiceTest, self).setUp()
        configuration = MonitorConfiguration()
        configuration.load(["-d", self.broker_service.config.data_path,
                            "--bus", "session"])
        self.monitor = MonitorService(configuration)
        self.monitor.reactor = FakeReactor()
        self.monitor.startService()

    def tearDown(self):
        super(MonitorServiceTest, self).tearDown()
        self.monitor.stopService()


class DeploymentBusTest(MonitorServiceTest):

    def test_dbus_reactor_transmitter_installed(self):
        return assertTransmitterActive(self, self.broker_service,
                                       self.monitor.reactor)

    def test_receives_messages(self):
        return assertReceivesMessages(self, self.monitor.dbus_service,
                                      self.broker_service, self.remote)


class MonitorTest(MonitorServiceTest):

    def test_monitor_flushes_on_flush_event(self):
        """L{MonitorService.flush} saves the persist."""
        self.monitor.registry.persist.set("a", 1)
        self.monitor.registry.flush()

        persist = Persist()
        persist.load(self.monitor.registry.persist_filename)
        self.assertEquals(persist.get("a"), 1)

    def test_monitor_flushes_on_flush_interval(self):
        """
        The monitor is flushed every C{flush_interval} seconds, after
        the monitor service is started.
        """
        self.monitor.registry.persist.set("a", 1)
        self.monitor.reactor.advance(self.monitor.config.flush_interval)

        persist = Persist()
        persist.load(self.monitor.registry.persist_filename)
        self.assertEquals(persist.get("a"), 1)

    def test_monitor_flushes_on_service_stop(self):
        """The monitor is flushed when the service stops."""
        self.monitor.registry.persist.set("a", 1)
        self.monitor.stopService()

        persist = Persist()
        persist.load(self.monitor.registry.persist_filename)
        self.assertEquals(persist.get("a"), 1)

    def test_monitor_stops_flushing_after_service_stops(self):
        """The recurring flush event is cancelled when the service stops."""
        self.monitor.stopService()
        self.monitor.registry.persist.set("a", 1)
        self.monitor.reactor.advance(self.monitor.config.flush_interval)

        persist = Persist()
        persist.load(self.monitor.registry.persist_filename)
        self.assertEquals(persist.get("a"), None)
