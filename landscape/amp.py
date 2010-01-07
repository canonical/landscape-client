import os
import logging

from landscape.lib.amp import (
    Method, MethodCallProtocol, MethodCallFactory, RemoteObjectCreator)


class LandscapeComponentProtocol(MethodCallProtocol):
    """
    Communication protocol between the various Landscape components.
    """
    methods = [Method("ping"),
               Method("exit")]


class LandscapeComponentProtocolFactory(MethodCallFactory):

    protocol = LandscapeComponentProtocol

    def __init__(self, reactor, component):
        """
        @param reactor: A L{TwistedReactor} object.
        @param component: The Landscape component to expose.
        """
        MethodCallFactory.__init__(self, reactor._reactor, component)


class RemoteLandscapeComponentCreator(RemoteObjectCreator):
    """Utility superclass for creating connections with a Landscape component.

    @cvar socket: The name of the socket to connect to, it must be set
        by sub-classes.
    """

    protocol = MethodCallProtocol
    retry_interval = 5
    max_retries = 10

    def __init__(self, reactor, config):
        """
        @param reactor: A L{TwistedReactor} object.
        @param config: A L{LandscapeConfiguration}.
        """
        socket = os.path.join(config.data_path, self.socket)
        super(RemoteLandscapeComponentCreator, self).__init__(
            reactor._reactor, socket)

    def connect(self):

        def log_error(failure):
            logging.error("Error while trying to connect %s", self.socket)
            return failure

        connected = super(RemoteLandscapeComponentCreator, self).connect(
            retry_interval=self.retry_interval, max_retries=self.max_retries)
        return connected.addErrback(log_error)
