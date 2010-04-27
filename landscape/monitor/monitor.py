"""The Landscape monitor plugin system."""

import os

from landscape.lib.dbus_util import method

from landscape.plugin import BrokerClientPluginRegistry, BrokerPlugin
from landscape.broker.client import BrokerClient


BUS_NAME = "com.canonical.landscape.Monitor"
OBJECT_PATH = "/com/canonical/landscape/Monitor"
IFACE_NAME = BUS_NAME


class MonitorDBusObject(BrokerPlugin):
    """A DBUS object which provides an interface to the Landscape Monitor."""

    bus_name = BUS_NAME
    object_path = OBJECT_PATH

    ping = method(IFACE_NAME)(BrokerPlugin.ping)
    exit = method(IFACE_NAME)(BrokerPlugin.exit)
    message = method(IFACE_NAME)(BrokerPlugin.message)


class MonitorPluginRegistry(BrokerClientPluginRegistry):
    """The central point of integration in the Landscape monitor."""

    def __init__(self, broker, reactor, config, bus,
                 persist, persist_filename=None,
                 step_size=5*60):
        super(MonitorPluginRegistry, self).__init__(broker)
        self.reactor = reactor
        self.config = config
        self.persist = persist
        self.persist_filename = persist_filename
        if persist_filename and os.path.exists(persist_filename):
            self.persist.load(persist_filename)
        self._plugins = []
        self.step_size = step_size
        self.bus = bus

    def flush(self):
        """Flush data to disk."""
        if self.persist_filename:
            self.persist.save(self.persist_filename)

    def exchange(self):
        """Call C{exchange} on all plugins."""
        super(MonitorPluginRegistry, self).exchange()
        self.flush()


class Monitor(BrokerClient):
    """The central point of integration in the Landscape monitor."""

    name = "monitor"

    def __init__(self, reactor, config, persist, persist_filename=None,
                 step_size=5*60):
        super(Monitor, self).__init__(reactor)
        self.reactor = reactor
        self.config = config
        self.persist = persist
        self.persist_filename = persist_filename
        if persist_filename and os.path.exists(persist_filename):
            self.persist.load(persist_filename)
        self._plugins = []
        self.step_size = step_size
        self.reactor.call_every(self.config.flush_interval, self.flush)

    def flush(self):
        """Flush data to disk."""
        if self.persist_filename:
            self.persist.save(self.persist_filename)

    def exchange(self):
        """Call C{exchange} on all plugins."""
        super(Monitor, self).exchange()
        self.flush()
