from landscape.lib.amp import RemoteObject
from landscape.amp import (
    LandscapeComponentServerProtocol, LandscapeComponentServerFactory,
    LandscapeComponentClientProtocol, LandscapeComponentClientFactory,
    RemoteLandscapeComponentCreator)


class BrokerServerProtocol(LandscapeComponentServerProtocol):
    """
    Communication protocol between the broker server and its clients.
    """
    methods = (LandscapeComponentServerProtocol.methods +
               ["register_client",
                "send_message",
                "is_message_pending",
                "stop_clients",
                "reload_configuration",
                "register",
                "get_accepted_message_types",
                "get_server_uuid",
                "register_client_accepted_message_type"])


class BrokerServerFactory(LandscapeComponentServerFactory):

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


class BrokerClientProtocol(LandscapeComponentClientProtocol):
    """Communication protocol between a client and the broker."""


class BrokerClientFactory(LandscapeComponentClientFactory):

    protocol = BrokerClientProtocol


class RemoteBrokerCreator(RemoteLandscapeComponentCreator):
    """Helper to create connections with the L{BrokerServer}."""

    factory = BrokerClientFactory
    remote = RemoteBroker
    socket = "broker.sock"


class RemoteClient(object):
    """A connected client utilizing features provided by a L{BrokerServer}."""

    def __init__(self, name):
        """
        @param name: Name of the broker client.
        @param protocol: A L{BrokerServerProtocol} connection with the broker
            server.
        """
        self.name = name
