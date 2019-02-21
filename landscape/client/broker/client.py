from logging import info, exception, error, debug
import sys
import random

from twisted.internet.defer import maybeDeferred, succeed

from landscape.lib.format import format_object
from landscape.lib.twisted_util import gather_results
from landscape.client.amp import remote


class HandlerNotFoundError(Exception):
    """A handler for the given message type was not found."""


class BrokerClientPlugin(object):
    """A convenience for writing L{BrokerClient} plugins.

    This provides a register method which will set up a bunch of
    reactor handlers in the idiomatic way.

    If C{run} is defined on subclasses, it will be called every C{run_interval}
    +seconds after being registered.

    @cvar run_interval: The interval, in seconds, to execute the C{run} method.
        If set to C{None}, then C{run} will not be scheduled.
    @cvar run_immediately: If C{True} the plugin will be run immediately after
        it is registered.
    @ivar _session_id: the session id to be passed when sending messages via
        the broker.  This variable is set by the C{register} method and
        should only need to be renewed when a re-synchronisation request is
        sent. See L{landscape.broker.server.BrokerServer.send_message} for
        more details.
    """
    run_interval = 5
    run_immediately = False
    scope = None  # Global scope
    _session_id = None
    _loop = None

    def register(self, client):
        self.client = client
        self.client.reactor.call_on("resynchronize", self._resynchronize)
        deferred = self.client.broker.get_session_id(scope=self.scope)
        deferred.addCallback(self._got_session_id)

    @property
    def registry(self):
        """An alias for the C{client} attribute."""
        return self.client

    def call_on_accepted(self, type, callable, *args, **kwargs):
        """
        Register a callback fired upon a C{message-type-acceptance-changed}.
        """

        def acceptance_changed(acceptance):
            if acceptance:
                return callable(*args, **kwargs)

        self.client.reactor.call_on(("message-type-acceptance-changed", type),
                                    acceptance_changed)

    def _resynchronize(self, scopes=None):
        """
        Handle the 'resynchronize' event.  Subclasses should do any clear-down
        operations specific to their state within an implementation of the
        L{_reset} method.
        """
        if not (scopes is None or self.scope in scopes):
            # This resynchronize event is out of scope for us. Do nothing
            return succeed(None)

        # Because the broker will drop session IDs already associated to scope
        # of the resynchronisation, it isn't safe to send messages until the
        # client has received a new session ID.  Therefore we pause any calls
        # to L{run} by cancelling L{_loop}, this will be restarted in
        # L{_got_session_id}.
        if self._loop is not None:
            self.client.reactor.cancel_call(self._loop)

        # Do any state clean up required by the plugin.
        self._reset()

        deferred = self.client.broker.get_session_id(scope=self.scope)
        deferred.addCallback(self._got_session_id)
        return deferred

    def _reset(self):
        """
        Reset plugin specific state.

        Sub-classes should override this method to clear down data for
        resynchronisation.  Sub-classes with no state can simply ignore this.
        """

    def _got_session_id(self, session_id):
        """Save the session ID and invoke the C{run} method.

        We set the C{_session_id} attribute on the instance because it's
        required in order to send messages.  See
        L{BrokerService.get_session_id}.
        """
        self._session_id = session_id
        if getattr(self, "run", None) is not None:
            if self.run_immediately:
                self._run_with_error_log()
            if self.run_interval is not None:
                delay = (random.random() * self.run_interval *
                         self.client.config.stagger_launch)
                debug("delaying start of %s for %d seconds",
                      format_object(self), delay)
                self._loop = self.client.reactor.call_later(
                    delay, self._start_loop)

    def _start_loop(self):
        """Launch the client loop."""
        self._loop = self.client.reactor.call_every(
            self.run_interval,
            self._run_with_error_log)

    def _run_with_error_log(self):
        """Wrap self.run in a Deferred with a logging error handler."""
        deferred = maybeDeferred(self.run)
        return deferred.addErrback(self._error_log)

    def _error_log(self, failure):
        """Errback to log and reraise uncaught run errors."""
        msg = "{} raised an uncaught exception".format(type(self).__name__)
        if sys.exc_info() == (None, None, None):
            error(msg)
        else:
            exception(msg)
        return failure


class BrokerClient(object):
    """Basic plugin registry for clients that have to deal with the broker.

    This knows about the needs of a client when dealing with the Landscape
    broker, including interest in messages of a particular type delivered
    by the broker to the client.

    @cvar name: The name used when registering to the broker, it must be
        defined by sub-classes.
    @ivar broker: A reference to a connected L{RemoteBroker}, it must be set
        by the connecting machinery at service startup.

    @param reactor: A L{LandscapeReactor}.
    """
    name = "client"

    def __init__(self, reactor, config):
        super(BrokerClient, self).__init__()
        self.reactor = reactor
        self.broker = None
        self.config = config
        self._registered_messages = {}
        self._plugins = []
        self._plugin_names = {}

        # Register event handlers
        self.reactor.call_on("impending-exchange", self.notify_exchange)
        self.reactor.call_on("broker-reconnect", self.handle_reconnect)

    @remote
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
        return self._plugins[:]

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
        except Exception:
            exception("Error running message handler for type %r: %r"
                      % (type, handler))

    @remote
    def message(self, message):
        """Call C{dispatch_message} for the given C{message}.

        @return: A boolean indicating if a handler for the message was found.
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
                except Exception:
                    exception("Error during plugin exchange")

    def notify_exchange(self):
        """Notify all plugins about an impending exchange."""
        info("Got notification of impending exchange. Notifying all plugins.")
        self.exchange()

    @remote
    def fire_event(self, event_type, *args, **kwargs):
        """Fire an event of a given type.

        @return: A L{Deferred} resulting in a list of returns values of
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

        The following needs to be done:

          - Re-register any previously registered message types, so the broker
            knows we have interest on them.

          - Re-register ourselves as client, so the broker knows we exist and
            will talk to us firing events and dispatching messages.
        """
        for type in self._registered_messages:
            self.broker.register_client_accepted_message_type(type)
        self.broker.register_client(self.name)

    @remote
    def exit(self):
        """Stop the reactor and exit the process."""
        # Stop with a short delay to give a chance to reply to the caller when
        # this method is invoked over AMP (typically by the broker, see also
        # landscape.broker.server.BrokerServer.exit).
        self.reactor.call_later(0.1, self.reactor.stop)
