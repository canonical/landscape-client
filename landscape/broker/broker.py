"""The DBUS service which interfaces to the broker."""

import logging

from dbus.service import signal
import dbus.glib

from landscape.lib.dbus_util import (get_object, Object, method,
                                     byte_array, array_to_string)
from landscape.lib.bpickle import loads, dumps
from landscape.lib.twisted_util import gather_results

from landscape.manager.manager import FAILED


BUS_NAME = "com.canonical.landscape.Broker"
OBJECT_PATH = "/com/canonical/landscape/Broker"
IFACE_NAME = BUS_NAME


class BrokerDBusObject(Object):
    """
    A DBus-published object exposing broker's services and emitting signals.

    Each public method decorated with C{@method(IFACE_NAME)} exposes a
    broker's service to the other Landscape client processes, which can
    remote call it through the D-Bus interface.
    
    Each public method decorated with C{@signal(IFACE_NAME)} turns the
    corresponding broker's L{TwistedReactor} event into a a D-Bus signal,
    which get broadcasted over the bus and eventually received by the
    other Landscape client processes.
    """

    bus_name = BUS_NAME
    object_path = OBJECT_PATH

    def __init__(self, config, reactor, exchange, registration,
                 message_store, bus):
        """
        @param config: The L{BrokerConfiguration} used by the broker.
        @param reactor: The L{TwistedReactor} driving the broker's events.
        @param exchange: The L{MessageExchange} to send messages with.
        @param registration: The {RegistrationHandler}.
        @param message_store: The broker's L{MessageStore}.
        @param bus: The L{Bus} that represents where we're listening.
        """
        super(BrokerDBusObject, self).__init__(bus)
        self._registered_plugins = set()
        self.bus = bus
        self.config = config
        self.reactor = reactor
        self.exchange = exchange
        self.registration = registration
        self.message_store = message_store
        reactor.call_on("message", self._broadcast_message)
        reactor.call_on("impending-exchange", self.impending_exchange)
        reactor.call_on("exchange-failed", self.exchange_failed)
        reactor.call_on("registration-done", self.registration_done)
        reactor.call_on("registration-failed", self.registration_failed)
        reactor.call_on("message-type-acceptance-changed",
                        self.message_type_acceptance_changed)
        def server_uuid_changed(old_uuid, new_uuid):
            # Convert Nones to empty strings.  The Remote will
            # convert them back to Nones.
            self.server_uuid_changed(old_uuid or "", new_uuid or "")
        reactor.call_on("server-uuid-changed", server_uuid_changed)
        reactor.call_on("resynchronize-clients", self.resynchronize)

    @signal(IFACE_NAME)
    def resynchronize(self):
        pass

    @signal(IFACE_NAME)
    def impending_exchange(self):
        pass

    @signal(IFACE_NAME)
    def exchange_failed(self):
        pass

    def _broadcast_message(self, message):
        """
        Call the C{message} method of all the registered plugins.

        @see: L{register_plugin}.
        """
        blob = byte_array(dumps(message))
        results = []
        for plugin in self.get_plugin_objects():
            results.append(plugin.message(blob))
        return gather_results(results).addCallback(self._message_delivered,
                                                   message)

    def _message_delivered(self, results, message):
        """
        If the message wasn't handled, and it's an operation request (i.e. it
        has an operation-id), then respond with a failing operation result
        indicating as such.
        """
        opid = message.get("operation-id")
        if (True not in results
            and opid is not None
            and message["type"] != "resynchronize"):
            mtype = message["type"]
            logging.error("Nobody handled the %s message." % (mtype,))

            result_text = """\
Landscape client failed to handle this request (%s) because the
plugin which should handle it isn't available.  This could mean that the
plugin has been intentionally disabled, or that the client isn't running
properly, or you may be running an older version of the client that doesn't
support this feature.

Please contact the Landscape team for more information.
""" % (mtype,)
            response = {
                "type": "operation-result",
                "status": FAILED,
                "result-text": result_text,
                "operation-id": opid}
            self.exchange.send(response, urgent=True)


    @method(IFACE_NAME)
    def ping(self):
        """Return True"""
        return True

    @method(IFACE_NAME)
    def send_message(self, message, urgent=False):
        """Queue the given message in the message exchange.

        This method is DBUS-published.

        @param message: The message dict.
        @param urgent: If True, exchange urgently. Defaults to False.
        """
        message = loads(array_to_string(message))
        try:
            logging.debug("Got a %r message over DBUS." % (message["type"],))
        except (KeyError, TypeError), e:
            logging.exception(str(e))
        return self.exchange.send(message, urgent=urgent)

    @method(IFACE_NAME)
    def is_message_pending(self, message_id):
        return self.message_store.is_pending(message_id)

    @method(IFACE_NAME)
    def reload_configuration(self):
        self.config.reload()
        # Now we'll kill off everything else so that they can be restarted and
        # notice configuration changes.
        return self.stop_plugins()

    @method(IFACE_NAME)
    def register(self):
        return self.registration.register()

    @signal(IFACE_NAME)
    def registration_done(self):
        pass

    @signal(IFACE_NAME)
    def registration_failed(self):
        pass

    @method(IFACE_NAME, out_signature="as")
    def get_accepted_message_types(self):
        return self.message_store.get_accepted_types()

    @signal(IFACE_NAME)
    def message_type_acceptance_changed(self, type, accepted):
        pass

    @method(IFACE_NAME, out_signature="s")
    def get_server_uuid(self):
        # Convert Nones to empty strings.  The Remote will
        # convert them back to Nones.
        return self.message_store.get_server_uuid() or ""

    @signal(IFACE_NAME)
    def server_uuid_changed(self, old_uuid, new_uuid):
        pass

    @method(IFACE_NAME)
    def register_client_accepted_message_type(self, type):
        self.exchange.register_client_accepted_message_type(type)

    @method(IFACE_NAME)
    def register_plugin(self, bus_name, object_path):
        """
        Register a new plugin.

        Plugins are DBus-published objects identified by C{bus_name}
        and C{object_path}.
        """
        self._registered_plugins.add((bus_name, object_path))

    @method(IFACE_NAME)
    def get_registered_plugins(self):
        return list(self._registered_plugins)

    def get_plugin_objects(self, retry_timeout=None):
        return [get_object(self.bus, bus_name, object_path,
                           retry_timeout=retry_timeout)
                for bus_name, object_path in self._registered_plugins]

    def stop_plugins(self):
        """Tell all plugins to exit."""
        results = []
        # We disable our timeout with retry_timeout=0 here.  The process might
        # already have exited, or be truly wedged, so the default DBus timeout
        # is good enough.
        for plugin in self.get_plugin_objects(retry_timeout=0):
            results.append(plugin.exit())
        result = gather_results(results, consume_errors=True)
        result.addCallback(lambda ignored: None)
        return result

    @method(IFACE_NAME)
    def exit(self):
        """Request a graceful exit from the broker.

        Before this method returns, all plugins will be notified of the
        broker's intention of exiting, so that they have the chance to
        stop whatever they're doing in a graceful way, and then exit
        themselves.

        This method will only return a result when all plugins returned
        their own results.
        """
        # Fire pre-exit before calling any of the plugins, so that everything
        # in the broker acknowledges that we're about to exit and asking
        # plugins to die.  This prevents any exchanges from happening,
        # for instance.
        self.reactor.fire("pre-exit")

        result = self.stop_plugins()

        def fire_post_exit(ignored):
            # Fire it shortly, to give us a chance to send a DBUS reply.
            self.reactor.call_later(1, lambda: self.reactor.fire("post-exit"))
        result.addBoth(fire_post_exit)

        return result
