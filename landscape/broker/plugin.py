from logging import exception

from landscape.plugin import PluginRegistry


class HandlerNotFoundError(Exception):
    """A handler for the given message type was not found."""


class BrokerClientPluginRegistry(PluginRegistry):
    """Basic plugin registry for clients that have to deal with the broker.

    This knows about the needs of a client when dealing with the Landscape
    broker, including interest in messages of a particular type delivered
    by the broker to the client.
    """

    def __init__(self, broker):
        """
        @param broker: A connected L{RemoteBroker} instance.
        """
        super(BrokerClientPluginRegistry, self).__init__()
        self._registered_messages = {}
        self.broker = broker

    def register_message(self, type, handler):
        """
        Register interest in a particular type of Landscape server->client
        message.

        @param type: The type of message to register C{handler} for.
        @param handler: A callable taking a message as a parameter, called
            when messages of C{type} are received.
        @return: A C{Deferred} that will fire when registration completes.
        """
        self._registered_messages[type] = handler
        return self.broker.register_client_accepted_message_type(type)

    def broker_started(self):
        """
        Re-register any previously registered message types when the broker
        restarts.
        """
        for type in self._registered_messages:
            self.broker.register_client_accepted_message_type(type)

    def dispatch_message(self, message):
        """Run the handler registered for the type of the given message."""
        type = message["type"]
        handler = self._registered_messages.get(type)
        if handler is not None:
            try:
                return handler(message)
            except:
                exception("Error running message handler for type %r: %r"
                          % (type, handler))
        else:
            raise HandlerNotFoundError(type)

    def exchange(self):
        """Call C{exchange} on all plugins."""
        for plugin in self._plugins:
            if hasattr(plugin, "exchange"):
                try:
                    plugin.exchange()
                except:
                    exception("Error during plugin exchange")
