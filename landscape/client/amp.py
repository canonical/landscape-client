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

import errno
import logging
import os
import socket as socket_module

from twisted.internet import error as tw_error

from landscape.lib.amp import (
    MethodCallClientFactory,
    MethodCallServerFactory,
    RemoteObject,
)


class ComponentPublisher:
    """Publish a Landscape client component using a UNIX socket.

    Other Landscape client processes can then connect to the socket and invoke
    methods on the component remotely, using L{MethodCall} commands.

    @param component: The component to publish. It can be any Python object
        implementing the methods listed in the C{methods} class variable.
    @param reactor: The L{LandscapeReactor} used to listen to the socket.
    @param config: The L{Configuration} object used to build the socket path.
    """

    factory = MethodCallServerFactory

    def __init__(self, component, reactor, config):
        self._reactor = reactor
        self._config = config
        self._component = component
        self._port = None
        self.methods = get_remote_methods(type(component)).keys()

    def start(self):
        """Start accepting connections.

        If a previous instance of this component died without cleaning up
        (e.g. it was SIGKILLed by the watchdog), its socket file may be left
        behind with no live listener on it, which makes the bind fail with
        C{EADDRINUSE}. In that case we remove the stale socket and retry once,
        rather than crash and let the watchdog give up restarting us. A socket
        that still has a live listener is left untouched and the error is
        re-raised, so a genuine duplicate process is still refused.
        """
        factory = MethodCallServerFactory(self._component, self.methods)
        socket_path = _get_socket_path(self._component, self._config)
        self._port = self._listen_recovering_stale(socket_path, factory)

    def _listen_recovering_stale(self, socket_path, factory):
        try:
            return self._reactor.listen_unix(socket_path, factory)
        except tw_error.CannotListenError as error:
            if not (
                _is_addr_in_use(error) and _socket_has_no_live_listener(socket_path)
            ):
                raise
            logging.warning(
                "Removing stale socket %s left behind by a dead process, "
                "retrying listen.",
                socket_path,
            )
            _remove_socket_file(socket_path)
            return self._reactor.listen_unix(socket_path, factory)

    def stop(self):
        """Stop accepting connections."""
        return self._port.stopListening()


def get_remote_methods(klass):
    """Get all the remote methods declared on a class.

    @param klass: A class to search for AMP-exposed methods.
    """
    remote_methods = {}
    for attribute_name in dir(klass):
        potential_method = getattr(klass, attribute_name)
        name = getattr(potential_method, "amp_exposed", None)
        if name is not None:
            remote_methods[name] = potential_method
    return remote_methods


def remote(method):
    """
    A decorator for marking a method as remotely accessible as a method on a
    component.
    """
    method.amp_exposed = method.__name__
    return method


class ComponentConnector:
    """Utility superclass for creating connections with a Landscape component.

    @cvar component: The class of the component to connect to, it is expected
        to define a C{name} class attribute, which will be used to find out
        the socket to use. It must be defined by sub-classes.
    @cvar factory: The factory class to use for building protocols.
    @cvar remote: The L{RemoteObject} class or sub-class used for building
        remote objects.

    @param reactor: A L{LandscapeReactor} object.
    @param config: A L{LandscapeConfiguration}.
    @param retry_on_reconnect: If C{True} the remote object built by this
        connector will retry L{MethodCall}s that failed due to lost
        connections.

    @see: L{MethodCallClientFactory}.
    """

    factory = MethodCallClientFactory
    component = None  # Must be defined by sub-classes
    remote = RemoteObject

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
        factory = self.factory(self._reactor._reactor)
        factory.initialDelay = factory.delay = 0.05
        factory.retryOnReconnect = self._retry_on_reconnect
        factory.remote = self.remote
        factory.maxRetries = max_retries
        if factor:
            factory.factor = factor

        def fire_reconnect(ignored):
            self._reactor.fire(f"{self.component.name}-reconnect")

        def connected(remote):
            factory.notifyOnConnect(fire_reconnect)
            return remote

        def log_error(failure):
            logging.error(f"Error while connecting to {self.component.name}")
            return failure

        socket_path = _get_socket_path(self.component, self._config)
        deferred = factory.getRemoteObject()
        self._connector = self._reactor.connect_unix(socket_path, factory)

        if not quiet:
            deferred.addErrback(log_error)

        return deferred.addCallback(connected)

    def disconnect(self):
        """Disconnect the L{RemoteObject} that we have created."""
        if self._connector is not None:
            factory = self._connector.factory
            factory.stopTrying()
            self._connector.disconnect()
            self._connector = None


def _get_socket_path(component, config):
    return os.path.join(config.sockets_path, component.name + ".sock")


def _is_addr_in_use(cannot_listen_error):
    """Return True if C{CannotListenError} was caused by the address being busy.

    The underlying socket error is available as C{socketError}; on Linux a
    leftover unix socket yields C{EADDRINUSE}, and a leftover lock or
    restrictive permissions can surface as C{EACCES}.
    """
    socket_error = getattr(cannot_listen_error, "socketError", None)
    return isinstance(socket_error, OSError) and socket_error.errno in (
        errno.EADDRINUSE,
        errno.EACCES,
    )


def _socket_has_no_live_listener(path):
    """Return True if nothing is accepting connections on the unix socket.

    A stale socket file left by a dead process refuses connections
    (C{ECONNREFUSED}) or is simply absent (C{ENOENT}); a live process accepts
    the connection. We only treat the former as safe to remove, so we never
    delete a socket a running component is genuinely serving.
    """
    if not os.path.exists(path):
        return True
    probe = socket_module.socket(socket_module.AF_UNIX, socket_module.SOCK_STREAM)
    try:
        probe.connect(path)
    except OSError:
        return True
    finally:
        probe.close()
    return False


def _remove_socket_file(path):
    """Remove a stale socket path, tolerating a non-socket inode left behind."""
    if os.path.isdir(path) and not os.path.islink(path):
        os.rmdir(path)
    else:
        os.unlink(path)
