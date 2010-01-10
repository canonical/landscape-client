import os
import logging

from landscape.lib.amp import (
    MethodCallServerProtocol, MethodCallServerFactory,
    MethodCallClientProtocol, MethodCallClientFactory, RemoteObjectCreator)


class LandscapeComponentServerProtocol(MethodCallServerProtocol):
    """
    Communication protocol between the various Landscape components.
    """
    methods = ["ping",
               "exit"]


class LandscapeComponentServerFactory(MethodCallServerFactory):

    protocol = LandscapeComponentServerProtocol


class LandscapeComponentClientProtocol(MethodCallClientProtocol):

    timeout = 60


class LandscapeComponentClientFactory(MethodCallClientFactory):

    protocol = MethodCallClientProtocol


class RemoteLandscapeComponentCreator(RemoteObjectCreator):
    """Utility superclass for creating connections with a Landscape component.

    @cvar socket: The name of the socket to connect to, it must be set
        by sub-classes.
    """

    factory = LandscapeComponentClientFactory

    def __init__(self, reactor, config, *args, **kwargs):
        """
        @param reactor: A L{TwistedReactor} object.
        @param config: A L{LandscapeConfiguration}.
        """
        socket = os.path.join(config.data_path, self.socket)
        super(RemoteLandscapeComponentCreator, self).__init__(
            reactor._reactor, socket, *args, **kwargs)

    def connect(self, max_retries=None):

        def log_error(failure):
            logging.error("Error while trying to connect %s", self.socket)
            return failure

        connected = super(RemoteLandscapeComponentCreator, self).connect(
            max_retries=max_retries)
        return connected.addErrback(log_error)
