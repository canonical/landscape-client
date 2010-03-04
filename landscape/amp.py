import os
import logging

from landscape.lib.amp import (
    MethodCallServerProtocol, MethodCallServerFactory,
    MethodCallClientProtocol, MethodCallClientFactory, RemoteObjectCreator)


class LandscapeComponentServerProtocol(MethodCallServerProtocol):
    """
    Communication protocol between the various Landscape components.
    """
    methods = ["ping", "exit"]


class LandscapeComponentServerFactory(MethodCallServerFactory):

    protocol = LandscapeComponentServerProtocol


class LandscapeComponentClientProtocol(MethodCallClientProtocol):

    timeout = 60


class LandscapeComponentClientFactory(MethodCallClientFactory):

    protocol = MethodCallClientProtocol


class RemoteLandscapeComponentCreator(RemoteObjectCreator):
    """Utility superclass for creating connections with a Landscape component.

    @cvar component: The class of the component to connect to, it is expected
        to define a C{name} class attribute, which will be used to find out
        the socket to use. It must be defined by sub-classes.
    """

    factory = LandscapeComponentClientFactory

    def __init__(self, reactor, config, *args, **kwargs):
        """
        @param reactor: A L{TwistedReactor} object.
        @param config: A L{LandscapeConfiguration}.
        @param args: Positional arguments for protocol factory constructor.
        @param kwargs: Keyword arguments for protocol factory constructor.

        @see: L{MethodCallClientFactory}.
        """
        self._twisted_reactor = reactor
        socket = os.path.join(config.data_path, self.component.name + ".sock")
        super(RemoteLandscapeComponentCreator, self).__init__(
            self._twisted_reactor._reactor, socket, *args, **kwargs)

    def connect(self, max_retries=None):
        """Connect to the remote Landscape component.

        If the connection is lost after having been established, and then
        it is established again by the reconnect mechanism, an event will
        be fired.

        @param max_retries: If given, the connector will keep trying to connect
            up to that number of times, if the first connection attempt fails.
        """

        def fire_reconnected(remote):
            self._twisted_reactor.fire("%s-reconnected" %
                                       self.component.name)

        def connected(remote):
            self._factory.add_notifier(fire_reconnected)
            return remote

        def log_error(failure):
            logging.error("Error while connecting to %s", self.component.name)
            return failure

        result = super(RemoteLandscapeComponentCreator, self).connect(
            max_retries=max_retries)
        result.addErrback(log_error)
        result.addCallback(connected)
        return result
