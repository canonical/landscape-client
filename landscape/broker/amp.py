from twisted.protocols.amp import AMP
from twisted.internet.protocol import ServerFactory
from twisted.internet.defer import succeed

from landscape.lib.amp import MethodCall


class BrokerServerProtocol(AMP):
    """
    Communication protocol between the broker server and its clients.
    """

    _broker_method_calls = ("ping",
                            "register_client",
                            "send_message",
                            "is_message_pending",
                            "stop_clients",
                            "reload_configuration",
                            "register",
                            "get_accepted_message_types",
                            "get_server_uuid",
                            "register_client_accepted_message_type",
                            "exit")

    @MethodCall.responder
    def _get_broker_method(self, name):
        if name in self._broker_method_calls:
            return getattr(self.factory.broker, name)


class BrokerServerProtocolFactory(ServerFactory):
    """A protocol factory for the L{BrokerProtocol}."""

    protocol = BrokerServerProtocol

    def __init__(self, broker):
        """
        @param: The L{BrokerServer} the connections will talk to.
        """
        self.broker = broker


class RemoteClient(object):
    """A connected client utilizing features provided by a L{BrokerServer}."""

    def __init__(self, name, protocol):
        """
        @param name: Name of the broker client.
        @param protocol: A L{BrokerServerProtocol} connection with the broker
            server.
        """
        self.name = name
        self._protocol = protocol

    def exit(self):
        """Placeholder to make tests pass, it will be replaced later."""
        return succeed(None)
