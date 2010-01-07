from twisted.internet.defer import maybeDeferred, execute, succeed

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


class FakeRemoteBroker(object):
    """Looks like L{RemoteBroker}, but actually talks to local objects."""

    def __init__(self, exchanger, message_store):
        self.exchanger = exchanger
        self.message_store = message_store
        self.protocol = BrokerServerProtocol(None)

    def call_if_accepted(self, type, callable, *args):
        if type in self.message_store.get_accepted_types():
            return maybeDeferred(callable, *args)
        return succeed(None)

    def send_message(self, message, urgent=False):
        """Send to the previously given L{MessageExchange} object."""
        return execute(self.exchanger.send, message, urgent=urgent)

    def register_client_accepted_message_type(self, type):
        return execute(self.exchanger.register_client_accepted_message_type,
                       type)


class BrokerClientProtocol(LandscapeComponentProtocol):
    """Communication protocol between a client and the broker."""

    methods = (LandscapeComponentProtocol.methods +
               [Method("message"),
                Method("fire_event")])

    remote_factory = RemoteBroker


class RemoteBrokerCreator(RemoteLandscapeComponentCreator):
    """Helper for creating connections with the L{BrokerServer}."""

    protocol = BrokerClientProtocol
    socket = "broker.sock"
