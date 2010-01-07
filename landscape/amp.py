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

    def __init__(self, reactor, config):
        """
        @param reactor: A L{TwistedReactor} object.
        @param config: A L{LandscapeConfiguration}.
        """
        socket = os.path.join(config.data_path, self.socket)
        super(RemoteLandscapeComponentCreator, self).__init__(
            reactor._reactor, socket)

    def connect(self, retry_interval=5, max_retries=None, log_errors=False):
        """Connect to the remote Landscape component.

        @param retry_interval: Retry interval in seconds
        @param max_retries: Maximum number of retries, C{None} (the default)
            means keep trying indefinitely.
        @param log_errors: Whether an error should be logged in case of
            failure.
        """

        def log_error(failure):
            logging.error("Error while trying to connect %s", self.socket)
            return failure

        connected = super(RemoteLandscapeComponentCreator, self).connect(
            retry_interval=retry_interval, max_retries=max_retries)
        if log_errors:
            connected.addErrback(log_error)
        return connected
