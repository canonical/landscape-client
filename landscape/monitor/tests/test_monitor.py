from twisted.internet.defer import Deferred

from landscape.monitor.monitor import (
    MonitorPluginRegistry, MonitorDBusObject, Monitor)
from landscape.lib.persist import Persist
from landscape.lib.dbus_util import get_object
from landscape.tests.test_plugin import ExchangePlugin
from landscape.tests.helpers import (
    LandscapeTest, LandscapeIsolatedTest, RemoteBrokerHelper, MonitorHelper)
from landscape.broker.client import BrokerClientPlugin


class MonitorPluginRegistryTest(LandscapeTest):

    helpers = [MonitorHelper]

    def test_persist(self):
        self.monitor.persist.set("a", 1)
        self.assertEquals(self.monitor.persist.get("a"), 1)

    def test_flush_saves_persist(self):
        """L{Monitor.flush} saves any changes made to the persist database."""
        self.monitor.persist.set("a", 1)
        self.monitor.flush()

        persist = Persist()
        persist.load(self.monitor.persist_filename)
        self.assertEquals(persist.get("a"), 1)

    def test_flush_after_exchange(self):
        """
        The L{Monitor.exchange} method flushes the monitor after
        C{exchange} on all plugins has been called.
        """

        class SamplePlugin(ExchangePlugin):

            def exchange(myself):
                self.monitor.persist.set("a", 1)
                super(SamplePlugin, myself).exchange()

        self.monitor.add(SamplePlugin())
        self.monitor.exchange()

        persist = Persist()
        persist.load(self.monitor.persist_filename)
        self.assertEquals(persist.get("a"), 1)

    def test_creating_loads_persist(self):
        filename = self.makeFile()

        persist = Persist()
        persist.set("a", "Hi there!")
        persist.save(filename)

        manager = MonitorPluginRegistry(self.remote, self.reactor,
                                        self.broker_service.config,
                                        None,
                                        persist=Persist(),
                                        persist_filename=filename)
        self.assertEquals(manager.persist.get("a"), "Hi there!")


class MonitorDBusObjectTest(LandscapeIsolatedTest):
    """Tests that use a monitor with a real DBUS service."""

    helpers = [RemoteBrokerHelper]

    def setUp(self):
        super(MonitorDBusObjectTest, self).setUp()
        persist = Persist()
        self.monitor = MonitorPluginRegistry(self.remote,
                                             self.broker_service.reactor,
                                             self.broker_service.config,
                                             self.broker_service.bus,
                                             persist)
        self.dbus_service = MonitorDBusObject(self.broker_service.bus,
                                              self.monitor)
        self.service = get_object(self.broker_service.bus,
                                  MonitorDBusObject.bus_name,
                                  MonitorDBusObject.object_path)

    def test_ping(self):
        result = self.service.ping()

        def got_result(result):
            self.assertEquals(result, True)
        return result.addCallback(got_result)

    def test_exit(self):
        result = Deferred()

        reactor = self.mocker.replace("twisted.internet.reactor")

        self.expect(reactor.stop()).call(lambda: result.callback(None))
        self.mocker.replay()

        self.service.exit()

        return result


class MonitorTest(LandscapeTest):

    helpers = [MonitorHelper]

    def test_persist(self):
        """
        A L{Monitor} instance has a C{persist} attribute.
        """
        self.monitor.persist.set("a", 1)
        self.assertEquals(self.monitor.persist.get("a"), 1)

    def test_flush_saves_persist(self):
        """
        The L{Monitor.flush} method saves any changes made to the persist
        database.
        """
        self.monitor.persist.set("a", 1)
        self.monitor.flush()

        persist = Persist()
        persist.load(self.monitor.persist_filename)
        self.assertEquals(persist.get("a"), 1)

    def test_flush_after_exchange(self):
        """
        The L{Monitor.exchange} method flushes the monitor after
        C{exchange} on all plugins has been called.
        """
        plugin = BrokerClientPlugin()
        plugin.exchange = lambda: self.monitor.persist.set("a", 1)
        self.monitor.add(plugin)
        self.monitor.exchange()

        persist = Persist()
        persist.load(self.monitor.persist_filename)
        self.assertEquals(persist.get("a"), 1)

    def test_flush_every_flush_interval(self):
        """
        The L{Monitor.flush} method gets called every C{flush_interval}
        seconds, and perists data to the disk.
        """
        self.monitor.persist.save = self.mocker.mock()
        self.monitor.persist.save(self.monitor.persist_filename)
        self.mocker.count(3)
        self.mocker.replay()
        self.reactor.advance(self.config.flush_interval * 3)

    def test_creating_loads_persist(self):
        """
        If C{persist_filename} exists, it is loaded by the constructor.
        """
        filename = self.makeFile()

        persist = Persist()
        persist.set("a", "Hi there!")
        persist.save(filename)

        monitor = Monitor(self.reactor, self.config, persist=Persist(),
                          persist_filename=filename)
        self.assertEquals(monitor.persist.get("a"), "Hi there!")
