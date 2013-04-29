"""Communication between components in different services via twisted AMP.

The Landscape client is composed by several processes that need to talk to
each other. For example the monitor and manager processes need to talk to
the broker in order to ask it to add new messages to the outgoing queue, and
the broker needs to talk to them in order to dispatch them incoming messages
from the server.

This module implements a few conveniences built around L{landscape.lib.amp} to
let the various services connect to each other in an easy and idiomatic way,
and have them respond to standard requests like "ping" or "exit".
"""
import os
import logging

from landscape.lib.amp import (
    MethodCallClientFactory, MethodCallServerFactory, RemoteObject)


class ComponentProtocolClientFactory(MethodCallClientFactory):

    initialDelay = 0.05


class ComponentPublisher(object):
    """Publish a Landscape client component using a UNIX socket.

    Other Landscape client processes can then connect to the socket and invoke
    methods on the component remotely, using L{MethodCall} commands.

    @param component: The component to publish. It can be any Python object
        implementing the methods listed in the C{methods} class variable.
    @param reactor: The L{TwistedReactor} used to listen to the socket.
    @param config: The L{Configuration} object used to build the socket path.
    """

    methods = ("ping", "exit")

    def __init__(self, component, reactor, config):
        self._reactor = reactor
        self._config = config
        self._component = component
        self._port = None

    def start(self):
        """Start accepting connections."""
        factory = MethodCallServerFactory(self._component, self.methods)
        socket_path = _get_socket_path(self._component, self._config)
        self._port = self._reactor.listen_unix(socket_path, factory)

    def stop(self):
        """Stop accepting connections."""
        return self._port.stopListening()


class RemoteComponentConnector(object):
    """Utility superclass for creating connections with a Landscape component.

    @cvar component: The class of the component to connect to, it is expected
        to define a C{name} class attribute, which will be used to find out
        the socket to use. It must be defined by sub-classes.
    @cvar factory: The factory class to use for building protocols.
    @cvar remote: The L{RemoteObject} class or sub-class used for building
        remote objects.

    @param reactor: A L{TwistedReactor} object.
    @param config: A L{LandscapeConfiguration}.
    @param retry_on_reconnect: If C{True} the remote object built by this
        connector will retry L{MethodCall}s that failed due to lost
        connections.

    @see: L{MethodCallClientFactory}.
    """
    component = None  # Must be defined by sub-classes
    factory = ComponentProtocolClientFactory

    def __init__(self, reactor, config, retry_on_reconnect=False):
        self._reactor = reactor
        self._config = config
        self._retry_on_reconnect = retry_on_reconnect
        self._connector = None

    def connect(self, max_retries=None, factor=None, quiet=False):
        """Connect to the remote Landscape component.

        If the connection is lost after having been established, and then
        it is established again by the reconnect mechanism, an event will
        be fired.

        @param max_retries: If given, the connector will keep trying to connect
            up to that number of times, if the first connection attempt fails.
        @param factor: Optionally a float indicating by which factor the
            delay between subsequent retries should increase. Smaller values
            result in a faster reconnection attempts pace.
        @param quiet: A boolean indicating whether to log errors.
        """
        reactor = self._reactor._reactor
        factory = self.factory(reactor)
        factory.retryOnReconnect = self._retry_on_reconnect
        factory.remote = self.remote

        def fire_reconnect(ignored):
            self._reactor.fire("%s-reconnect" % self.component.name)

        def connected(remote):
            factory.notifyOnConnect(fire_reconnect)
            return remote

        def log_error(failure):
            logging.error("Error while connecting to %s", self.component.name)
            return failure

        factory.maxRetries = max_retries
        if factor:
            factory.factor = factor
        socket_path = _get_socket_path(self.component, self._config)
        self._connector = reactor.connectUNIX(socket_path, factory)
        deferred = factory.getRemoteObject()

        if not quiet:
            deferred.addErrback(log_error)

        return deferred.addCallback(connected)

    def disconnect(self):
        """Disconnect the L{RemoteObject} that we have created."""
        if self._connector is not None:
            factory = self._connector.factory
            factory.stopTrying()
            # XXX we should be using self._connector.disconnect() here
            remote = factory._remote
            if remote:
                if remote._sender.protocol.transport:
                    remote._sender.protocol.transport.loseConnection()


class RemoteComponentsRegistry(object):
    """
    A global registry for looking up Landscape component connectors by name.
    """

    _by_name = {}

    @classmethod
    def get(cls, name):
        """Get the connector class for the given Landscape component.

        @param name: Name of the Landscape component we want to connect to, for
           instance C{monitor} or C{manager}.
        """
        return cls._by_name[name]

    @classmethod
    def register(cls, connector_class):
        """Register a connector for a Landscape component.

        @param connector_class: A sub-class of L{RemoteComponentConnector}
            that can be used to connect to a certain component.
        """
        cls._by_name[connector_class.component.name] = connector_class


def _get_socket_path(component, config):
    return os.path.join(config.sockets_path, component.name + ".sock")
