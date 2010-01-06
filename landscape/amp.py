import os

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
    """Helper to create connections with a Landscape component.

    @cvar socket: The name of the socket to connect to, it must be set
        by the subclasses.
    """

    protocol = MethodCallProtocol
    socket = "landscape"

    def __init__(self, reactor, config):
        """
        @param reactor: A L{TwistedReactor} object.
        @param config: A L{LandscapeConfiguration}.
        """
        socket = os.path.join(config.data_path, self.socket + ".sock")
        super(RemoteLandscapeComponentCreator, self).__init__(
            reactor._reactor, socket)
