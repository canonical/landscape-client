from logging import info

from twisted.internet.defer import succeed

from landscape.lib.format import format_object
from landscape.lib.log import log_failure
from landscape.client.broker.client import BrokerClientPlugin


class MonitorPlugin(BrokerClientPlugin):
    """
    @cvar persist_name: If specified as a string, a C{_persist} attribute
    will be available after registration.
    """

    persist_name = None
    scope = None

    def register(self, monitor):
        super(MonitorPlugin, self).register(monitor)
        if self.persist_name is not None:
            self._persist = self.monitor.persist.root_at(self.persist_name)
        else:
            self._persist = None

    def _reset(self):
        if self.persist_name is not None:
            self.registry.persist.remove(self.persist_name)

    @property
    def persist(self):
        """Return our L{Persist}, if any."""
        return self._persist

    @property
    def monitor(self):
        """An alias for the C{client} attribute."""
        return self.client


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
            result = self.registry.broker.send_message(
                message, self._session_id, urgent=urgent)

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
