import logging

from twisted.internet.defer import Deferred

from landscape.lib.twisted_util import gather_results
from landscape.amp import RemoteComponentsRegistry
from landscape.manager.manager import FAILED


def event(method):
    """Turns a L{BrokerServer} method into an event broadcaster.

    When the decorated method is called, an event is fired on all connected
    clients. The event will have the same name as the method being called,
    except that any underscore in the method name will be replaced with a dash.
    """
    event_type = method.__name__.replace("_", "-")

    def broadcast_event(self, *args, **kwargs):
        fired = []
        for client in self.get_clients():
            fired.append(client.fire_event(event_type, *args, **kwargs))
        return gather_results(fired)

    return broadcast_event


class BrokerServer(object):
    """
    A broker server capable of handling messages from plugins connected using
    the L{BrokerProtocol}.
    """
    name = "broker"
    connectors_registry = RemoteComponentsRegistry

    def __init__(self, config, reactor, exchange, registration,
                 message_store):
        """
        @param config: The L{BrokerConfiguration} used by the broker.
        @param reactor: The L{TwistedReactor} driving the broker's events.
        @param exchange: The L{MessageExchange} to send messages with.
        @param registration: The {RegistrationHandler}.
        @param message_store: The broker's L{MessageStore}.
        """
        self._config = config
        self._reactor = reactor
        self._exchanger = exchange
        self._registration = registration
        self._message_store = message_store
        self._registered_clients = {}
        self._connectors = {}

        reactor.call_on("message", self.broadcast_message)
        reactor.call_on("impending-exchange", self.impending_exchange)
        reactor.call_on("message-type-acceptance-changed",
                        self.message_type_acceptance_changed)
        reactor.call_on("server-uuid-changed", self.server_uuid_changed)
        reactor.call_on("package-data-changed", self.package_data_changed)
        reactor.call_on("resynchronize-clients", self.resynchronize)

    def ping(self):
        """Return C{True}."""
        return True

    def register_client(self, name):
        """Register a broker client called C{name}.

        Various broker clients interact with the broker server, such as the
        monitor for example, using the L{BrokerServerProtocol} for performing
        remote method calls on the L{BrokerServer}.

        They establish connectivity with the broker by connecting and
        registering themselves, the L{BrokerServer} will in turn connect
        to them in order to be able to perform remote method calls like
        broadcasting events and messages.

        @param name: The name of the client, such a C{monitor} or C{manager}.
        """
        connector_class = self.connectors_registry.get(name)
        connector = connector_class(self._reactor, self._config)

        def register(remote_client):
            self._registered_clients[name] = remote_client
            self._connectors[remote_client] = connector

        connected = connector.connect()
        return connected.addCallback(register)

    def get_clients(self):
        """Get L{RemoteClient} instances for registered clients."""
        return self._registered_clients.values()

    def get_client(self, name):
        """Return the client with the given C{name} or C{None}."""
        return self._registered_clients.get(name)

    def get_connectors(self):
        """Get connectors for registered clients.

        @see L{RemoteLandscapeComponentCreator}.
        """
        return self._connectors.values()

    def get_connector(self, name):
        """Return the connector for the given C{name} or C{None}."""
        return self._connectors.get(self.get_client(name))

    def send_message(self, message, urgent=False):
        """Queue C{message} for delivery to the server at the next exchange.

        @param message: The message C{dict} to send to the server.  It must
            have a C{type} key and be compatible with C{landscape.lib.bpickle}.
        @param urgent: If C{True}, exchange urgently, otherwise exchange
            during the next regularly scheduled exchange.
        @return: The message identifier created when queuing C{message}.
        """
        return self._exchanger.send(message, urgent=urgent)

    def is_message_pending(self, message_id):
        """Indicate if a message with given C{message_id} is pending."""
        return self._message_store.is_pending(message_id)

    def stop_clients(self):
        """Tell all the clients to exit."""
        results = []
        # FIXME: check whether the client are still alive
        for client in self.get_clients():
            results.append(client.exit())
        result = gather_results(results, consume_errors=True)
        return result.addCallback(lambda ignored: None)

    def reload_configuration(self):
        """Reload the configuration file, and stop all clients."""
        self._config.reload()
        # Now we'll kill off everything else so that they can be restarted and
        # notice configuration changes.
        return self.stop_clients()

    def register(self):
        """Attempt to register with the Landscape server.

        @see: L{RegistrationHandler.register}
        """
        return self._registration.register()

    def get_accepted_message_types(self):
        """Return the message types accepted by the Landscape server."""
        return self._message_store.get_accepted_types()

    def get_server_uuid(self):
        """Return the uuid of the Landscape server we're pointing at."""
        # Convert Nones to empty strings.  The Remote will
        # convert them back to Nones.
        return self._message_store.get_server_uuid()

    def register_client_accepted_message_type(self, type):
        """Register a new message type which can be accepted by this client.

        @param type: The message type to accept.
        """
        self._exchanger.register_client_accepted_message_type(type)

    def fire_event(self, event_type):
        """Fire an event in the broker reactor."""
        self._reactor.fire(event_type)

    def exit(self):
        """Request a graceful exit from the broker server.

        Before this method returns, all broker clients will be notified
        of the server broker's intention of exiting, so that they have
        the chance to stop whatever they're doing in a graceful way, and
        then exit themselves.

        This method will only return a result when all plugins returned
        their own results.
        """
        # Fire pre-exit before calling any of the plugins, so that everything
        # in the broker acknowledges that we're about to exit and asking
        # broker clients to die.  This prevents any exchanges from happening,
        # for instance.
        self._reactor.fire("pre-exit")

        clients_stopped = self.stop_clients()

        def fire_post_exit(ignored):
            # Fire it shortly, to give us a chance to send an AMP reply.
            self._reactor.call_later(
                1, lambda: self._reactor.fire("post-exit"))

        return clients_stopped.addBoth(fire_post_exit)

    @event
    def resynchronize(self):
        """Broadcast a C{resynchronize} event to the clients."""

    @event
    def impending_exchange(self):
        """Broadcast an C{impending-exchange} event to the clients."""

    def listen_events(self, event_types):
        """
        Return a C{Deferred} that fires when the first event occurs among the
        given ones.
        """
        deferred = Deferred()
        calls = []

        def get_handler(event_type):

            def handler():
                for call in calls:
                    self._reactor.cancel_call(call)
                deferred.callback(event_type)

            return handler

        for event_type in event_types:
            call = self._reactor.call_on(event_type, get_handler(event_type))
            calls.append(call)
        return deferred

    @event
    def broker_reconnect(self):
        """Broadcast a C{broker-reconnect} event to the clients."""

    @event
    def server_uuid_changed(self, old_uuid, new_uuid):
        """Broadcast a C{server-uuid-changed} event to the clients."""

    @event
    def message_type_acceptance_changed(self, type, accepted):
        pass

    @event
    def package_data_changed(self):
        """Fire a package-data-changed event in the reactor of each client."""

    def broadcast_message(self, message):
        """Call the C{message} method of all the registered plugins.

        @see: L{register_plugin}.
        """
        results = []
        for client in self.get_clients():
            results.append(client.message(message))
        result = gather_results(results)
        return result.addCallback(self._message_delivered, message)

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
            self._exchanger.send(response, urgent=True)
