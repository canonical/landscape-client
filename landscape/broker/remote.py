"""A client for the service in L{landscape.broker.broker.BrokerDBusObject}."""

from twisted.internet.defer import execute, maybeDeferred, succeed

from dbus import DBusException

from landscape.schema import InvalidError
from landscape.broker.broker import BUS_NAME, OBJECT_PATH, IFACE_NAME
from landscape.lib.dbus_util import get_object, byte_array, array_to_string
from landscape.lib.bpickle import dumps, loads


class RemoteBroker(object):
    """
    An object which knows how to talk to a remote BrokerDBusObject
    service over DBUS.
    """

    def __init__(self, bus, retry_timeout=None):
        self.bus = bus
        try:
            self.broker = get_object(bus, BUS_NAME, OBJECT_PATH,
                                     retry_timeout=retry_timeout)
        except DBusException, e:
            if str(e).startswith("org.freedesktop.DBus.Error.ServiceUnknown"):
                raise ServiceUnknownError()

    def connect_to_signal(self, *args, **kwargs):
        kwargs["dbus_interface"] = IFACE_NAME
        return self.broker.connect_to_signal(*args, **kwargs)

    def send_message(self, message, urgent=False):
        """Send a message to the message exchange service.

        @return: A deferred which will fire with the result of the send() call.
        """
        return self._perform_call("send_message",
                                  byte_array(dumps(message)), urgent)

    def schedule_exchange(self, urgent=False):
        """Schedule an exchange.

        @param urgent: An urgent exchange is scheduled if the flag is C{True}.
        """
        return self._perform_call("schedule_exchange", urgent)

    def reload_configuration(self):
        """Reload the broker configuration.

        @return: A deferred which will fire with the result of the
                 reload_configuration() call.
        """
        return self._perform_call("reload_configuration")

    def register(self, timeout=1):
        return self._perform_call("register", timeout=timeout)

    def get_accepted_message_types(self):
        return self._perform_call("get_accepted_message_types")

    def call_if_accepted(self, type, callable, *args):
        deferred_types = self.get_accepted_message_types()
        def got_accepted_types(result):
            if type in result:
                return callable(*args)
        deferred_types.addCallback(got_accepted_types)
        return deferred_types

    def is_message_pending(self, message_id):
        return self._perform_call("is_message_pending", message_id)

    def register_plugin(self, service_name, path):
        return self._perform_call("register_plugin", service_name, path)

    def get_registered_plugins(self):
        def convert(result):
            return [(str(service), str(path)) for service, path in result]
        result = self._perform_call("get_registered_plugins")
        return result.addCallback(convert)

    def exit(self):
        return self._perform_call("exit")

    def _perform_call(self, name, *args, **kwargs):
        method = getattr(self.broker, name)
        result = method(*args, **kwargs)
        return result


class FakeRemoteBroker(object):
    """Looks like L{RemoteBroker}, but actually talks to local objects."""

    def __init__(self, exchanger, message_store):
        self.exchanger = exchanger
        self.message_store = message_store

    def call_if_accepted(self, type, callable, *args):
        if type in self.message_store.get_accepted_types():
            return maybeDeferred(callable, *args)
        return succeed(None)

    def send_message(self, message, urgent=False):
        """Send to the previously given L{MessageExchange} object."""
        return execute(self.exchanger.send, message, urgent=urgent)

    def schedule_exchange(self, urgent=False):
        return succeed(self.exchanger.schedule_exchange(urgent=urgent))


class DBusSignalToReactorTransmitter(object):
    """
    An object which broadcasts Landscape messages received via DBUS to the
    reactor. The event key is C{("message", message-type)}, and one argument,
    the message, will be passed.

    In addition, C{resynchronize} signals will be translated to
    C{resynchronize} reactor events.
    """
    def __init__(self, bus, reactor):
        self.bus = bus
        self.reactor = reactor
        bus.add_signal_receiver(self._broadcast_resynchronize, "resynchronize")
        bus.add_signal_receiver(self._broadcast_message_type_acceptance_changed,
                                "message_type_acceptance_changed")


    def _broadcast_resynchronize(self):
        # XXX This event should probably be renamed to something like
        # "clear data" since the only result of this event being fired
        # is that persist data is cleared out, no actual data uploads
        # are triggered by it.
        self.reactor.fire("resynchronize")

    def _broadcast_message_type_acceptance_changed(self, type, acceptance):
        self.reactor.fire(("message-type-acceptance-changed", type), acceptance)
