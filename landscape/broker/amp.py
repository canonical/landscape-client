from twisted.protocols.amp import AMP, Command, String, Integer, Boolean
from twisted.internet.protocol import ServerFactory

from landscape.lib.amp import amp_rpc_responder, StringOrNone, BPickle, Hidden


class Message(BPickle):
    """Marker class for commands with message arguments."""


class Types(BPickle):
    """Marker class for commands with message type arguments."""


class Ping(Command):

    arguments = []
    response = [("result", Boolean())]


class RegisterClient(Command):

    arguments = [("name", String()), ("__amp_rpc_protocol", Hidden("."))]
    response = []


class SendMessage(Command):

    arguments = [("message", Message()), ("urgent", Boolean())]
    response = [("result", Integer())]


class IsMessagePending(Command):

    arguments = [("message_id", Integer())]
    response = [("result", Boolean())]


class StopClients(Command):

    arguments = []
    response = []


class ReloadConfiguration(Command):

    arguments = []
    response = []


class Register(Command):

    arguments = []
    response = []


class GetAcceptedMessageTypes(Command):

    arguments = []
    response = [("result", Types())]


class GetServerUuid(Command):

    arguments = []
    response = [("result", StringOrNone())]


class RegisterClientAcceptedMessageType(Command):

    arguments = [("type", String())]
    response = []


class Exit(Command):

    arguments = []
    response = []


class BrokerServerProtocol(AMP):
    """
    Communication protocol between the broker server and its clients.
    """

    __amp_rpc_model__ = ".factory.broker"

    @amp_rpc_responder
    def ping(self):
        """@see L{BrokerServer.ping}"""

    @amp_rpc_responder
    def register_client(self, name):
        """@see L{BrokerServer.register_client}"""

    @amp_rpc_responder
    def send_message(self, message, urgent):
        """@see L{BrokerServer.send_message}"""

    @amp_rpc_responder
    def is_message_pending(self, message_id):
        """@see L{BrokerServer.is_message_pending}"""

    @amp_rpc_responder
    def stop_clients(self):
        """@see L{BrokerServer.stop_clients}"""

    @amp_rpc_responder
    def reload_configuration(self):
        """@see L{BrokerServer.reload_configuration}"""

    @amp_rpc_responder
    def register(self):
        """@see L{BrokerServer.register}"""

    @amp_rpc_responder
    def get_accepted_message_types(self):
        """@see L{BrokerServer.get_accepted_message_types}"""

    @amp_rpc_responder
    def get_server_uuid(self):
        """@see L{BrokerServer.get_server_uuid}"""

    @amp_rpc_responder
    def register_client_accepted_message_type(self, type):
        """@see L{BrokerServer.register_client_accepted_message_type}"""

    @amp_rpc_responder
    def exit(self):
        """@see L{BrokerServer.exit}"""


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
