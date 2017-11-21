from mock import Mock

from landscape.client.monitor.monitor import Monitor
from landscape.lib.persist import Persist
from landscape.client.tests.helpers import LandscapeTest, MonitorHelper
from landscape.client.broker.client import BrokerClientPlugin


class MonitorTest(LandscapeTest):

    helpers = [MonitorHelper]

    def test_persist(self):
        """
        A L{Monitor} instance has a C{persist} attribute.
        """
        self.monitor.persist.set("a", 1)
        self.assertEqual(self.monitor.persist.get("a"), 1)

    def test_flush_saves_persist(self):
        """
        The L{Monitor.flush} method saves any changes made to the persist
        database.
        """
        self.monitor.persist.set("a", 1)
        self.monitor.flush()

        persist = Persist()
        persist.load(self.monitor.persist_filename)
        self.assertEqual(persist.get("a"), 1)

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
        self.assertEqual(persist.get("a"), 1)

    def test_flush_every_flush_interval(self):
        """
        The L{Monitor.flush} method gets called every C{flush_interval}
        seconds, and perists data to the disk.
        """
        self.monitor.persist.save = Mock()
        self.reactor.advance(self.config.flush_interval * 3)
        self.monitor.persist.save.assert_called_with(
            self.monitor.persist_filename)
        self.assertEqual(self.monitor.persist.save.call_count, 3)

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
        self.assertEqual(monitor.persist.get("a"), "Hi there!")
