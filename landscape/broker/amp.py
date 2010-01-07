from landscape.lib.amp import Method, RemoteObject
from landscape.amp import (
    LandscapeComponentProtocol, LandscapeComponentProtocolFactory,
    RemoteLandscapeComponentCreator)


class BrokerServerProtocol(LandscapeComponentProtocol):
    """
    Communication protocol between the broker server and its clients.
    """
    methods = (LandscapeComponentProtocol.methods +
               [Method("register_client", protocol=""),
                Method("send_message"),
                Method("is_message_pending"),
                Method("stop_clients"),
                Method("reload_configuration"),
                Method("register"),
                Method("get_accepted_message_types"),
                Method("get_server_uuid"),
                Method("register_client_accepted_message_type")])


class BrokerProtocolFactory(LandscapeComponentProtocolFactory):

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
               [Method("message"),
                Method("fire_event")])

    remote_factory = RemoteBroker


class RemoteBrokerCreator(RemoteLandscapeComponentCreator):
    """Helper to create connections with the L{BrokerServer}."""

    protocol = BrokerClientProtocol
    socket = "broker.sock"
