from landscape.lib.amp import (
    Method, MethodCallProtocol, MethodCallFactory, RemoteObject,
    RemoteObjectCreator)


class BrokerServerProtocol(MethodCallProtocol):
    """
    Communication protocol between the broker server and its clients.
    """
    methods = [Method("ping"),
               Method("register_client", protocol=""),
               Method("send_message"),
               Method("is_message_pending"),
               Method("stop_clients"),
               Method("reload_configuration"),
               Method("register"),
               Method("get_accepted_message_types"),
               Method("get_server_uuid"),
               Method("register_client_accepted_message_type"),
               Method("exit")]


class BrokerServerFactory(MethodCallFactory):

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


class BrokerClientProtocol(MethodCallProtocol):
    """
    Communication protocol between the broker server and its clients.
    """
    """Communication protocol between a client and the broker."""

    methods = [Method("ping"),
               Method("message"),
               Method("fire_event"),
               Method("exit")]

    remote_factory = RemoteBroker


class RemoteBrokerCreator(RemoteObjectCreator):
    """Helper for creating connections with the L{BrokerServer}."""

    protocol = BrokerClientProtocol

    def __init__(self, reactor, config):
        """
        @param reactor: A L{TwistedReactor} object.
        @param socket: A L{Configuration} object.
        """
        super(RemoteBrokerCreator, self).__init__(
            reactor._reactor, config.broker_socket_filename)
