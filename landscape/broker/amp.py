from landscape.lib.amp import RemoteObject
from landscape.amp import (
    LandscapeComponentProtocol, LandscapeComponentFactory,
    RemoteLandscapeComponentCreator, RemoteLandscapeComponentsRegistry)
from landscape.broker.server import BrokerServer
from landscape.broker.client import BrokerClient


class BrokerServerProtocol(LandscapeComponentProtocol):
    """
    Communication protocol between the broker server and its clients.
    """
    methods = (LandscapeComponentProtocol.methods +
               ["get_accepted_message_types",
                "get_server_uuid",
                "is_message_pending",
                "register",
                "register_client",
                "register_client_accepted_message_type",
                "reload_configuration",
                "send_message",
                "stop_clients"])


class BrokerServerFactory(LandscapeComponentFactory):

    protocol = BrokerServerProtocol


class RemoteBroker(RemoteObject):

    def call_if_accepted(self, type, callable, *args):
        """Call C{callable} if C{type} is an accepted message type."""
        deferred_types = self.get_accepted_message_types()

        def got_accepted_types(result):
            if type in result:
                return callable(*args)
        deferred_types.addCallback(got_accepted_types)
        return deferred_types


class BrokerClientProtocol(LandscapeComponentProtocol):
    """Communication protocol between a client and the broker."""

    methods = (LandscapeComponentProtocol.methods +
               ["fire_event", "message"])


class BrokerClientFactory(LandscapeComponentFactory):

    protocol = BrokerClientProtocol


class RemoteClient(RemoteObject):
    """A remote L{BrokerClient} connected to a L{BrokerServer}."""


class RemoteBrokerCreator(RemoteLandscapeComponentCreator):
    """Helper to create connections with the L{BrokerServer}."""

    factory = BrokerClientFactory
    remote = RemoteBroker
    component = BrokerServer


class RemoteClientCreator(RemoteLandscapeComponentCreator):
    """Helper to create connections with the L{BrokerServer}."""

    factory = BrokerServerFactory
    remote = RemoteClient
    component = BrokerClient


RemoteLandscapeComponentsRegistry.register(RemoteClientCreator)
