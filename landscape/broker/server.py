from landscape.lib.twisted_util import gather_results
from landscape.broker.amp import RemoteClient


class BrokerServer(object):
    """
    A broker server capable of handling messages from plugins connected using
    the L{BrokerProtocol}.
    """

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

    def ping(self):
        """Return C{True}."""
        return True

    def register_client(self, name, protocol):
        """Register a broker client called C{name} connected with C{protocol}.

        Various broker clients interact with the broker server, such as the
        monitor for example, using the L{BrokerProtocol} for communication.
        They establish connectivity with the broker by connecting and
        registering themselves.

        @param name: The name of the client, such a C{monitor} or C{manager}.
        @param protocol: The L{BrokerProtocol} over which the client is
            connected.
        """
        self._registered_clients[name] = RemoteClient(name, protocol)

    def get_clients(self):
        """Get L{BrokerPlugin} instances for registered plugins."""
        return self._registered_clients.values()

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
            self._reactor.fire("post-exit")

        return clients_stopped.addBoth(fire_post_exit)
