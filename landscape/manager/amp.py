from landscape.amp import (
    RemoteLandscapeComponentCreator, LandscapeComponentProtocol)


class RemoteManagerCreator(RemoteLandscapeComponentCreator):
    """Helper for creating connections with the L{Monitor}."""

    protocol = LandscapeComponentProtocol
    socket = "manager.sock"
