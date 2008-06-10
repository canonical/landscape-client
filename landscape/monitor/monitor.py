"""The Landscape monitor plugin system."""

import os
from logging import exception, info

from twisted.internet.defer import succeed

from landscape.lib.dbus_util import Object, method
from landscape.lib.log import log_failure

from landscape.log import format_object
from landscape.plugin import PluginRegistry, Plugin, BrokerPlugin


BUS_NAME = "com.canonical.landscape.Monitor"
OBJECT_PATH = "/com/canonical/landscape/Monitor"
IFACE_NAME = BUS_NAME


class MonitorDBusObject(BrokerPlugin):
    """A DBUS object which provides an interface to the Landscape Monitor."""

    bus_name = BUS_NAME
    object_path = OBJECT_PATH

    def __init__(self, bus, monitor):
        super(MonitorDBusObject, self).__init__(bus, monitor)
        bus.add_signal_receiver(self.notify_exchange, "impending_exchange")

    def notify_exchange(self):
        info("Got notification of impending exchange. Notifying all plugins.")
        self.registry.exchange()

    ping = method(IFACE_NAME)(BrokerPlugin.ping)
    exit = method(IFACE_NAME)(BrokerPlugin.exit)
    message = method(IFACE_NAME)(BrokerPlugin.message)



class MonitorPluginRegistry(PluginRegistry):
    """The central point of integration in the Landscape monitor."""

    def __init__(self, reactor, broker, config, bus,
                 persist, persist_filename=None,
                 step_size=5*60):
        super(MonitorPluginRegistry, self).__init__()
        self.reactor = reactor
        self.broker = broker
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
        for plugin in self._plugins:
            if hasattr(plugin, "exchange"):
                try:
                    plugin.exchange()
                except:
                    exception("Error during plugin exchange")
        self.flush()


class MonitorPlugin(Plugin):
    """
    @cvar persist_name: If specified as a string, a C{_persist} attribute
    will be available after registration.

    XXX This class is no longer very useful and should be cleaned out
    at some point.
    """

    persist_name = None

    def register(self, registry):
        super(MonitorPlugin, self).register(registry)
        if self.persist_name is not None:
            self._persist = registry.persist.root_at(self.persist_name)

    def call_on_accepted(self, type, callable, *args, **kwargs):
        def acceptance_changed(acceptance):
            if acceptance:
                return callable(*args, **kwargs)
        self.registry.reactor.call_on(("message-type-acceptance-changed", type),
                                      acceptance_changed)


class DataWatcher(MonitorPlugin):
    """
    A utility for plugins which send data to the Landscape server
    which does not constantly change. New messages will only be sent
    when the result of get_data() has changed since the last time it
    was called.

    Subclasses should provide a get_data method, and message_type,
    message_key, and persist_name class attributes.
    """

    message_type = None
    message_key = None

    def get_message(self):
        """
        Construct a message with the latest data, or None, if the data
        has not changed since the last call.
        """
        data = self.get_data()
        if self._persist.get("data") != data:
            self._persist.set("data", data)
            return {"type": self.message_type, self.message_key: data}

    def send_message(self, urgent):
        message = self.get_message()
        if message is not None:
            info("Queueing a message with updated data watcher info "
                 "for %s.", format_object(self))
            result = self.registry.broker.send_message(message, urgent=urgent)
            def persist_data(message_id):
                self.persist_data()
            result.addCallback(persist_data)
            result.addErrback(log_failure)
            return result
        return succeed(None)

    def persist_data(self):
        """
        Sub-classes that need to defer the saving of persistent data
        should override this method.
        """
        pass

    def exchange(self, urgent=False):
        """
        Conditionally add a message to the message store if new data
        is available.
        """
        return self.registry.broker.call_if_accepted(self.message_type,
                                                     self.send_message, urgent)
