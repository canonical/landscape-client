from logging import info, exception

from twisted.internet.defer import maybeDeferred

from landscape.log import format_object
from landscape.lib.twisted_util import gather_results


class HandlerNotFoundError(Exception):
    """A handler for the given message type was not found."""


class BrokerClientPlugin(object):
    """A convenience for writing L{BrokerClient} plugins.

    This provides a register method which will set up a bunch of
    reactor handlers in the idiomatic way.

    If C{run} is defined on subclasses, it will be called every C{run_interval}
    seconds after being registered.

    @cvar run_interval: The interval, in seconds, to execute the C{run} method.
        If set to C{None}, then C{run} will not be scheduled.
    """

    run_interval = 5

    def register(self, client):
        self.client = client
        if hasattr(self, "run") and self.run_interval is not None:
            self.client.reactor.call_every(self.run_interval, self.run)


class BrokerClient(object):
    """Basic plugin registry for clients that have to deal with the broker.

    This knows about the needs of a client when dealing with the Landscape
    broker, including interest in messages of a particular type delivered
    by the broker to the client.

    @cvar name: The name used when registering to the broker, it must be
        defined by sub-classes.
    @ivar broker: A reference to a connected L{RemoteBroker}, it must be set
        by the connecting machinery at service startup.
    """
    name = "client"

    def __init__(self, reactor):
        """
        @param reactor: A L{TwistedReactor}.
        """
        super(BrokerClient, self).__init__()
        self.reactor = reactor
        self.broker = None
        self._registered_messages = {}
        self._plugins = []
        self._plugin_names = {}

        # Register event handlers
        self.reactor.call_on("impending-exchange", self.notify_exchange)
        self.reactor.call_on("broker-reconnect", self.handle_reconnect)

    def ping(self):
        """Return C{True}"""
        return True

    def add(self, plugin):
        """Add a plugin.

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
        """Run the handler registered for the type of the given message.

        @return: The return value of the handler, if found.
        @raises: HandlerNotFoundError if the handler was not found
        """
        type = message["type"]
        handler = self._registered_messages.get(type)
        if handler is None:
            raise HandlerNotFoundError(type)
        try:
            return handler(message)
        except:
            exception("Error running message handler for type %r: %r"
                      % (type, handler))

    def message(self, message):
        """Call C{dispatch_message} for the given C{message}.

        @return: A boolean indicating if an handler for the message was found.
        """
        try:
            self.dispatch_message(message)
            return True
        except HandlerNotFoundError:
            return False

    def exchange(self):
        """Call C{exchange} on all plugins."""
        for plugin in self.get_plugins():
            if hasattr(plugin, "exchange"):
                try:
                    plugin.exchange()
                except:
                    exception("Error during plugin exchange")

    def notify_exchange(self):
        """Notify all plugins about an impending exchange."""
        info("Got notification of impending exchange. Notifying all plugins.")
        self.exchange()

    def fire_event(self, event_type, *args, **kwargs):
        """Fire an event of a given type.

        @return: A L{Deferred} resulting in a list of return values of
            the fired event handlers, in the order they were fired.
        """
        if event_type == "message-type-acceptance-changed":
            message_type = args[0]
            acceptance = args[1]
            results = self.reactor.fire((event_type, message_type), acceptance)
        else:
            results = self.reactor.fire(event_type, *args, **kwargs)
        return gather_results([
            maybeDeferred(lambda x: x, result) for result in results])

    def handle_reconnect(self):
        """Called when the connection with the broker is established again.

        Re-register any previously registered message types when the broker
        restarts.
        """
        for type in self._registered_messages:
            self.broker.register_client_accepted_message_type(type)

    def exit(self):
        """Stop the reactor and exit the process."""
        self.reactor.stop()
