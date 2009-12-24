from twisted.protocols.amp import AMP
from twisted.internet.protocol import ServerFactory

from landscape.lib.amp import MethodCall


class BrokerServerProtocol(AMP):
    """
    Communication protocol between the broker server and its clients.
    """

    _broker_method_calls = ["ping",
                            "register_client",
                            "send_message",
                            "is_message_pending",
                            "stop_clients",
                            "reload_configuration",
                            "register",
                            "get_accepted_message_types",
                            "get_server_uuid",
                            "register_client_accepted_message_type",
                            "exit"]

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


class RemoteBroker(object):
    """A connected broker utilizing features provided by a L{BrokerServer}."""

    def __init__(self, protocol):
        """
        @param protocol: A L{BrokerServerProtocol} connection with a remote
            broker server.
        """
        self._protocol = protocol

    def _set_client(self, client):
        """Set a reference to the connected L{BrokerClient}."""
        self._protocol.client = client

    client = property(None, _set_client)

    @MethodCall.sender
    def ping(self):
        """@see L{BrokerServer.ping}"""

    @MethodCall.sender
    def register_client(self, name, _protocol=""):
        """@see L{BrokerServer.register_client}"""

    @MethodCall.sender
    def send_message(self, message, urgent):
        """@see L{BrokerServer.send_message}"""

    @MethodCall.sender
    def is_message_pending(self, message_id):
        """@see L{BrokerServer.is_message_pending}"""

    @MethodCall.sender
    def stop_clients(self):
        """@see L{BrokerServer.stop_clients}"""

    @MethodCall.sender
    def reload_configuration(self):
        """@see L{BrokerServer.reload_configuration}"""

    @MethodCall.sender
    def register(self):
        """@see L{BrokerServer.register}"""

    @MethodCall.sender
    def get_accepted_message_types(self):
        """@see L{BrokerServer.get_accepted_message_types}"""

    @MethodCall.sender
    def get_server_uuid(self):
        """@see L{BrokerServer.get_server_uuid}"""

    @MethodCall.sender
    def register_client_accepted_message_type(self, type):
        """@see L{BrokerServer.register_client_accepted_message_type}"""

    @MethodCall.sender
    def exit(self):
        """@see L{BrokerServer.exit}"""


class BrokerClientProtocol(AMP):
    """
    Communication protocol between the broker server and its clients.
    """

    _broker_client_calls = ["ping",
                            "dispatch_message",
                            "fire_event",
                            "exit"]

    @MethodCall.responder
    def _get_client_method(self, name):
        if name in self._broker_client_calls:
            return getattr(self.client, name)


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

    @MethodCall.sender
    def ping(self):
        """@see L{BrokerClient.ping}"""

    @MethodCall.sender
    def dispatch_message(self):
        """@see L{BrokerClient.dispatch_message}"""

    @MethodCall.sender
    def fire_event(self):
        """@see L{BrokerClient.fire_event}"""

    @MethodCall.sender
    def exit(self):
        """@see L{BrokerClient.exit}"""
