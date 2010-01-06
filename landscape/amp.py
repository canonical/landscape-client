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
    """Helper to create connections with a Landscape component."""

    protocol = MethodCallProtocol

    def __init__(self, reactor, config, name):
        """
        @param reactor: A L{TwistedReactor} object.
        @param config: A L{LandscapeConfiguration}.
        @param name: The name of the Landscape service to connect to.
        """
        socket = os.path.join(config.data_path, name + ".sock")
        super(self.__class__, self).__init__(reactor._reactor, socket)
