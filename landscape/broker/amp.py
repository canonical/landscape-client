from twisted.protocols.amp import String, Integer, Boolean
from twisted.internet.protocol import ServerFactory

from landscape.lib.amp import (
    MethodCallProtocol, MethodCall, StringOrNone, BPickle, ProtocolAttribute)


class Message(BPickle):
    """Marker class for commands with message arguments."""


class Types(BPickle):
    """Marker class for commands with message type arguments."""


class Ping(MethodCall):

    arguments = []
    response = [("result", Boolean())]


class RegisterClient(MethodCall):

    arguments = [("name", String()), ("__protocol_attribute_protocol",
                                      ProtocolAttribute(""))]
    response = []


class SendMessage(MethodCall):

    arguments = [("message", Message()), ("urgent", Boolean())]
    response = [("result", Integer())]


class IsMessagePending(MethodCall):

    arguments = [("message_id", Integer())]
    response = [("result", Boolean())]


class StopClients(MethodCall):

    arguments = []
    response = []


class ReloadConfiguration(MethodCall):

    arguments = []
    response = []


class Register(MethodCall):

    arguments = []
    response = []


class GetAcceptedMessageTypes(MethodCall):

    arguments = []
    response = [("result", Types())]


class GetServerUuid(MethodCall):

    arguments = []
    response = [("result", StringOrNone())]


class RegisterClientAcceptedMessageType(MethodCall):

    arguments = [("type", String())]
    response = []


class Exit(MethodCall):

    arguments = []
    response = []


BROKER_SERVER_METHOD_CALLS = [
    Ping, RegisterClient, SendMessage, IsMessagePending, StopClients,
    ReloadConfiguration, Register, GetAcceptedMessageTypes, GetServerUuid,
    RegisterClientAcceptedMessageType, Exit]


class BrokerServerProtocol(MethodCallProtocol):
    """
    Communication protocol between the broker server and its clients.
    """

    @property
    def _object(self):
        return self.factory.broker

    @Ping.responder
    def _ping(self):
        """@see L{BrokerServer.ping}"""

    @RegisterClient.responder
    def _register_client(self, name):
        """@see L{BrokerServer.register_client}"""

    @SendMessage.responder
    def _send_message(self, message, urgent):
        """@see L{BrokerServer.send_message}"""

    @IsMessagePending.responder
    def _is_message_pending(self, message_id):
        """@see L{BrokerServer.is_message_pending}"""

    @StopClients.responder
    def _stop_clients(self):
        """@see L{BrokerServer.stop_clients}"""

    @ReloadConfiguration.responder
    def _reload_configuration(self):
        """@see L{BrokerServer.reload_configuration}"""

    @Register.responder
    def _register(self):
        """@see L{BrokerServer.register}"""

    @GetAcceptedMessageTypes.responder
    def _get_accepted_message_types(self):
        """@see L{BrokerServer.get_accepted_message_types}"""

    @GetServerUuid.responder
    def _get_server_uuid(self):
        """@see L{BrokerServer.get_server_uuid}"""

    @RegisterClientAcceptedMessageType.responder
    def _register_client_accepted_message_type(self, type):
        """@see L{BrokerServer.register_client_accepted_message_type}"""

    @Exit.responder
    def _exit(self):
        """@see L{BrokerServer.exit}"""


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

    @Ping.sender
    def ping(self):
        """@see L{BrokerServer.ping}"""

    @RegisterClient.sender
    def register_client(self, name):
        """@see L{BrokerServer.register_client}"""

    @SendMessage.sender
    def send_message(self, message, urgent):
        """@see L{BrokerServer.send_message}"""

    @IsMessagePending.sender
    def is_message_pending(self, message_id):
        """@see L{BrokerServer.is_message_pending}"""

    @StopClients.sender
    def stop_clients(self):
        """@see L{BrokerServer.stop_clients}"""

    @ReloadConfiguration.sender
    def reload_configuration(self):
        """@see L{BrokerServer.reload_configuration}"""

    @Register.sender
    def register(self):
        """@see L{BrokerServer.register}"""

    @GetAcceptedMessageTypes.sender
    def get_accepted_message_types(self):
        """@see L{BrokerServer.get_accepted_message_types}"""

    @GetServerUuid.sender
    def get_server_uuid(self):
        """@see L{BrokerServer.get_server_uuid}"""

    @RegisterClientAcceptedMessageType.sender
    def register_client_accepted_message_type(self, type):
        """@see L{BrokerServer.register_client_accepted_message_type}"""

    @Exit.sender
    def exit(self):
        """@see L{BrokerServer.exit}"""


class DispatchMessage(MethodCall):

    arguments = [("message", Message())]
    response = [("result", Boolean())]


class Exchange(MethodCall):

    arguments = []
    response = []


BROKER_CLIENT_METHOD_CALLS = [
    Ping, DispatchMessage, Exchange, Exit]


class BrokerClientProtocol(MethodCallProtocol):
    """
    Communication protocol between the a broker client and its server.
    """

    @property
    def _object(self):
        return self.client

    @Ping.responder
    def _ping(self):
        """@see L{BrokerClient.ping}"""

    @DispatchMessage.responder
    def _dispatch_message(self):
        """@see L{BrokerClient.dispatch_message}"""

    @Exchange.responder
    def _exchange(self):
        """@see L{BrokerClient.exchange}"""

    @Exit.responder
    def _exit(self):
        """@see L{BrokerClient.exit}"""


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

    @Ping.sender
    def ping(self):
        """@see L{BrokerClient.ping}"""

    @DispatchMessage.sender
    def dispatch_message(self):
        """@see L{BrokerClient.dispatch_message}"""

    @Exchange.sender
    def exchange(self):
        """@see L{BrokerClient.exchange}"""

    @Exit.sender
    def exit(self):
        """@see L{BrokerClient.exit}"""
