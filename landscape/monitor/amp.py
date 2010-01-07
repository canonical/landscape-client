from landscape.amp import (
    RemoteLandscapeComponentCreator, LandscapeComponentProtocol)


class RemoteMonitorCreator(RemoteLandscapeComponentCreator):
    """Helper for creating connections with the L{Monitor}."""

    protocol = LandscapeComponentProtocol
    socket = "monitor.sock"
