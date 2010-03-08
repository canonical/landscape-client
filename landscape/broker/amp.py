from landscape.lib.amp import RemoteObject
from landscape.amp import (
    ComponentProtocol, ComponentProtocolFactory, RemoteComponentCreator)
from landscape.broker.server import BrokerServer


class BrokerServerProtocol(ComponentProtocol):
    """
    Communication protocol between the broker server and its clients.
    """
    methods = (ComponentProtocol.methods +
               ["get_accepted_message_types",
                "get_server_uuid",
                "is_message_pending",
                "register",
                "register_client",
                "register_client_accepted_message_type",
                "reload_configuration",
                "send_message",
                "stop_clients"])


class BrokerServerProtocolFactory(ComponentProtocolFactory):

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


class BrokerClientProtocol(ComponentProtocol):
    """Communication protocol between a client and the broker."""


class BrokerClientProtocolFactory(ComponentProtocolFactory):

    protocol = BrokerClientProtocol


class RemoteBrokerCreator(RemoteComponentCreator):
    """Helper to create connections with the L{BrokerServer}."""

    factory = BrokerClientProtocolFactory
    remote = RemoteBroker
    component = BrokerServer


class RemoteClient(object):
    """A connected client utilizing features provided by a L{BrokerServer}."""

    def __init__(self, name):
        """
        @param name: Name of the broker client.
        """
        self.name = name
