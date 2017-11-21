"""Bridge client side plugins to the C{MessageExchange}.

The C{BrokerServer} provides C{BrokerClient}s with a mechanism to send messages
to the server and, likewise, triggers those plugins to take action when a
exchange is impending or resynchronisaton is required.

Each C{BrokerClient} has to be registered using the
L{BrokerServer.register_client} method, after which two way communications is
possible between the C{BrokerServer} and the C{BrokerClient}.

Resynchronisation Sequence
==========================

See L{landscape.broker.exchange} sequence diagram for origin of the
"resynchronize-clients" event.

Diagram::


 1. [event 1]               --->  BrokerServer        : Event
                                                      : "resynchronize-clients"

 2. [event 2]               <---  BrokerServer        : Broadcast event
                                                      : "resynchronize"

 3. [optional: various L{BrowserClientPlugin}s respond
               to the "resynchronize" event to reset
               themselves and start report afresh.]
     (See: L{landscape.monitor.packagemonitor.PackageMonitor}
           L{landscape.monitor.plugin.MonitorPlugin}
           L{landscape.manager.keystonetoken.KeystoneToken}
           L{landscape.monitor.activeprocessinfo.ActiveProcessInfo} )


 4. [event 1]               ---> MessageExchange      : Event
    (NOTE, this is the same event as step 1           : "resynchronize-clients"
     it is handled by both BrokerServer and
     MessageExchange.
     See MessageExchange._resynchronize )

 5. MessageExchange         ---> MessageExchange      : Schedule urgent
                                                      : exchange

"""

import logging

from twisted.internet.defer import Deferred

from landscape.lib.twisted_util import gather_results
from landscape.client.amp import remote
from landscape.client.manager.manager import FAILED


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

    @param config: The L{BrokerConfiguration} used by the broker.
    @param reactor: The L{LandscapeReactor} driving the broker's events.
    @param exchange: The L{MessageExchange} to send messages with.
    @param registration: The {RegistrationHandler}.
    @param message_store: The broker's L{MessageStore}.
    """
    name = "broker"

    def __init__(self, config, reactor, exchange, registration,
                 message_store, pinger):
        from landscape.client.broker.amp import get_component_registry
        self.connectors_registry = get_component_registry()
        self._config = config
        self._reactor = reactor
        self._exchanger = exchange
        self._registration = registration
        self._message_store = message_store
        self._registered_clients = {}
        self._connectors = {}
        self._pinger = pinger

        reactor.call_on("message", self.broadcast_message)
        reactor.call_on("impending-exchange", self.impending_exchange)
        reactor.call_on("message-type-acceptance-changed",
                        self.message_type_acceptance_changed)
        reactor.call_on("server-uuid-changed", self.server_uuid_changed)
        reactor.call_on("package-data-changed", self.package_data_changed)
        reactor.call_on("resynchronize-clients", self.resynchronize)

    @remote
    def ping(self):
        """Return C{True}."""
        return True

    @remote
    def get_session_id(self, scope=None):
        """Get a unique session ID to be used when sending messages.

        Anything that wants to send a message to the server via the broker is
        required to first acquire a session ID with this method. Such session
        IDs must be passed to L{send_message} whenever sending a message.

        The broker keeps track of the session IDs that it hands out and will
        drop them when a re-synchronisation event occurs.  Further messages
        sent using expired IDs will be silently discarded.

        For example each L{BrokerClientPlugin} calls this method to get a
        session ID and use it when sending messages, until the plugin gets
        notified of a re-synchronisation event and then asks for a new one.

        This eliminates issues with out-of-date messages being delivered to the
        server after a re-synchronisation request. For example when the client
        re-registers and gets a new computer ID we don't want to deliver
        messages containing references to activity IDs of the old computer
        (e.g. a message with the result of a "change-packages" activity
        delivered before re-registering). See also #328005 and #1158822.

        """
        return self._message_store.get_session_id(scope=scope)

    @remote
    def register_client(self, name):
        """Register a broker client called C{name}.

        Various broker clients interact with the broker server, such as the
        monitor for example, using the L{BrokerServerConnector} for performing
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

    @remote
    def send_message(self, message, session_id, urgent=False):
        """Queue C{message} for delivery to the server at the next exchange.

        @param message: The message C{dict} to send to the server.  It must
            have a C{type} key and be compatible with C{landscape.lib.bpickle}.
        @param session_id: A session ID.  You should acquire this
            with C{get_session_id} before attempting to send a message.
        @param urgent: If C{True}, exchange urgently, otherwise exchange
            during the next regularly scheduled exchange.
        @return: The message identifier created when queuing C{message}.
        """
        if isinstance(session_id, bool) and message["type"] in (
                "operation-result", "change-packages-result"):
            # XXX This means we're performing a Landscape-driven upgrade and
            # we're being invoked by a package-changer or release-upgrader
            # process that is running code which doesn't know about the
            # session_id parameter, i.e. it was written against the old
            # signature:
            #
            #     def send_message(self, message, urgent=False):
            #
            # In this case we'll just let the message in. This transitional
            # code can be dropped once we stop supporting clients without
            # session IDs (i.e. with versions < 14.01).
            urgent = True
            session_id = self.get_session_id()

        if session_id is None:
            raise RuntimeError(
                "Session ID must be set before attempting to send a message")
        if self._message_store.is_valid_session_id(session_id):
            return self._exchanger.send(message, urgent=urgent)

    @remote
    def is_message_pending(self, message_id):
        """Indicate if a message with given C{message_id} is pending."""
        return self._message_store.is_pending(message_id)

    @remote
    def stop_clients(self):
        """Tell all the clients to exit."""
        results = []
        # FIXME: check whether the client are still alive
        for client in self.get_clients():
            results.append(client.exit())
        result = gather_results(results, consume_errors=True)
        return result.addCallback(lambda ignored: None)

    @remote
    def reload_configuration(self):
        """Reload the configuration file, and stop all clients."""
        self._config.reload()
        # Now we'll kill off everything else so that they can be restarted and
        # notice configuration changes.
        return self.stop_clients()

    @remote
    def register(self):
        """Attempt to register with the Landscape server.

        @see: L{RegistrationHandler.register}
        """
        return self._registration.register()

    @remote
    def get_accepted_message_types(self):
        """Return the message types accepted by the Landscape server."""
        return self._message_store.get_accepted_types()

    @remote
    def get_server_uuid(self):
        """Return the uuid of the Landscape server we're pointing at."""
        return self._message_store.get_server_uuid()

    @remote
    def register_client_accepted_message_type(self, type):
        """Register a new message type which can be accepted by this client.

        @param type: The message type to accept.
        """
        self._exchanger.register_client_accepted_message_type(type)

    @remote
    def fire_event(self, event_type):
        """Fire an event in the broker reactor."""
        self._reactor.fire(event_type)

    @remote
    def exit(self):
        """Request a graceful exit from the broker server.

        Before this method returns, all broker clients will be notified
        of the server broker's intention of exiting, so that they have
        the chance to stop whatever they're doing in a graceful way, and
        then exit themselves.

        This method will only return a result when all plugins returned
        their own results.
        """
        clients_stopped = self.stop_clients()

        def schedule_reactor_stop(ignored):
            # Stop the reactor with a short delay to give us a chance to reply
            # to the caller when this method is invoked over AMP (typically
            # by the watchdog, see landscape.watchdog.Watchdog.request_exit).
            #
            # Note that stopping the reactor will cause the Twisted machinery
            # to invoke BrokerService.stopService, which in turn will stop the
            # exchanger/pinger and cleanly close all AMP sockets.
            self._reactor.call_later(1, lambda: self._reactor.stop())

        return clients_stopped.addBoth(schedule_reactor_stop)

    @event
    def resynchronize(self):
        """Broadcast a C{resynchronize} event to the clients."""

    @event
    def impending_exchange(self):
        """Broadcast an C{impending-exchange} event to the clients."""

    @remote
    def listen_events(self, event_types):
        """
        Return a C{Deferred} that fires when the first event occurs among the
        given ones.
        """
        deferred = Deferred()
        calls = []

        def get_handler(event_type):

            def handler(**kwargs):
                for call in calls:
                    self._reactor.cancel_call(call)
                deferred.callback((event_type, kwargs))

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
        if (True not in results and
            opid is not None and
            message["type"] != "resynchronize"
            ):

            mtype = message["type"]
            logging.error("Nobody handled the %s message." % (mtype,))

            result_text = """\
Landscape client failed to handle this request (%s) because the
plugin which should handle it isn't available.  This could mean that the
plugin has been intentionally disabled, or that the client isn't running
properly, or you may be running an older version of the client that doesn't
support this feature.
""" % (mtype,)
            response = {
                "type": "operation-result",
                "status": FAILED,
                "result-text": result_text,
                "operation-id": opid}
            self._exchanger.send(response, urgent=True)

    @remote
    def stop_exchanger(self):
        """
        Stop exchaging messages with the message server.

        Eventually, it is required by the plugin that no more message exchanges
        are performed.
        For example, when a reboot process in running, the client stops
        accepting new messages so that no client action is running while the
        machine is rebooting.
        Also, some activities should be explicitly require that no more
        messages are exchanged so some level of serialization in the client
        could be achieved.
        """
        self._exchanger.stop()
        self._pinger.stop()
