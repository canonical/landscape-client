from logging import info, exception

from landscape.log import format_object


class HandlerNotFoundError(Exception):
    """A handler for the given message type was not found."""


class BrokerClient(object):
    """Basic plugin registry for clients that have to deal with the broker.

    This knows about the needs of a client when dealing with the Landscape
    broker, including interest in messages of a particular type delivered
    by the broker to the client.
    """

    def __init__(self, broker, reactor):
        """
        @param broker: A connected L{RemoteBroker} instance.
        """
        super(BrokerClient, self).__init__()
        self.broker = broker
        self.reactor = reactor
        self._registered_messages = {}
        self._plugins = []
        self._plugin_names = {}

    def ping(self):
        """Return C{True}"""
        return True

    def register_plugin(self, plugin):
        """Register a plugin.

        The plugin's C{register} method will be called with this broker client
        as its argument.

        If the plugin has a C{plugin_name} attribute, it will be possible to
        look up the plugin later with L{get_plugin}.
        """
        info("Registering plugin %s.", format_object(plugin))
        self._plugins.append(plugin)
        if hasattr(plugin, 'plugin_name'):
            self._plugin_names[plugin.plugin_name] = plugin
        plugin.register(self)

    def get_plugins(self):
        """Get the list of plugins."""
        return self._plugins

    def get_plugin(self, name):
        """Get a particular plugin by name."""
        return self._plugin_names[name]

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

    def dispatch_message(self, message):
        """Run the handler registered for the type of the given message."""
        type = message["type"]
        handler = self._registered_messages.get(type)
        if handler is None:
            raise HandlerNotFoundError(type)
        try:
            return handler(message)
        except:
            exception("Error running message handler for type %r: %r"
                      % (type, handler))

    def exchange(self):
        """Call C{exchange} on all plugins."""
        info("Got notification of impending exchange. Notifying all plugins.")
        for plugin in self.get_plugins():
            if hasattr(plugin, "exchange"):
                try:
                    plugin.exchange()
                except:
                    exception("Error during plugin exchange")

    def broker_started(self):
        """
        Re-register any previously registered message types when the broker
        restarts.
        """
        for type in self._registered_messages:
            self.broker.register_client_accepted_message_type(type)

    def exit(self):
        """Stop the reactor and exit the process."""
        self.reactor.stop()
