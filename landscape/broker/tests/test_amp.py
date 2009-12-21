import re

from twisted.internet.defer import Deferred
from twisted.internet import reactor
from twisted.internet.protocol import ClientCreator
from twisted.protocols.amp import AMP, String, Integer, Boolean


from landscape.lib.amp import Hidden, StringOrNone
from landscape.broker.amp import (
    BrokerServerProtocol, BrokerServerProtocolFactory, Message, Types,
    RegisterClient, SendMessage, RegisterClientAcceptedMessageType,
    IsMessagePending, StopClients, ReloadConfiguration, Register,
    GetAcceptedMessageTypes, GetServerUuid,
    Ping, Exit)
from landscape.tests.helpers import (
    LandscapeTest, BrokerServerHelper, DEFAULT_ACCEPTED_TYPES)


class BrokerServerProtocolFactoryTest(LandscapeTest):

    def test_provides_protocol_type(self):
        """
        The L{BrokerServerProtocolFactory} instantiates protocols objects of
        type L{BrokerServerProtocol}.
        """
        self.assertEquals(BrokerServerProtocolFactory.protocol,
                          BrokerServerProtocol)

    def test_provides_broker_object(self):
        """
        Instances of the L{BrokerServerProtocolFactory} class have a C{broker}
        attribute references the broker object they were instantiated with.
        """
        stub_broker = object()
        factory = BrokerServerProtocolFactory(stub_broker)
        self.assertEquals(factory.broker, stub_broker)


class BrokerServerProtocolTest(LandscapeTest):

    helpers = [BrokerServerHelper]

    def setUp(self):
        super(BrokerServerProtocolTest, self).setUp()
        socket = self.makeFile()
        factory = BrokerServerProtocolFactory(self.broker)
        self.port = reactor.listenUNIX(socket, factory)

        def set_protocol(protocol):
            self.protocol = protocol

        connector = ClientCreator(reactor, AMP)
        connected = connector.connectUNIX(socket)
        return connected.addCallback(set_protocol)

    def tearDown(self):
        super(BrokerServerProtocolTest, self).tearDown()
        self.port.loseConnection()
        self.protocol.transport.loseConnection()

    def assert_amp_rpc(self, command, model):
        """
        Assert that an C{AMP.callRemote} invocation against the given
        C{command}, actually calls the appropriate C{model} method.
        """
        kwargs = {}

        # Figure out the model method associated with the given command
        words = re.findall("[A-Z][a-z]+", command.__name__)
        method = "_".join(word.lower() for word in words)

        # Wrap the model method with one that will keep track of its calls
        calls = []
        original_method = getattr(model, method)

        def method_wrapper(*args, **kwargs):
            calls.append(True)
            result = original_method(*args, **kwargs)
            setattr(model, method, original_method)
            return result

        setattr(model, method, method_wrapper)

        # Some sample arguments for every agrument type
        argument_to_value = {String: "some_sring",
                             Boolean: True,
                             Integer: 123,
                             Message: {"type": "test"}}

        response_to_type = {String: str,
                            Boolean: bool,
                            Integer: int,
                            Message: dict,
                            Types: list}

        for name, kind in command.arguments:
            if kind.__class__ is Hidden:
                # Skip hidden arguments
                continue
            kwargs[name] = argument_to_value[kind.__class__]

        def assert_response(response):
            self.assertEquals(calls, [True])
            if command.response:
                name, kind = command.response[0]
                result = response[name]
                if isinstance(kind, StringOrNone):
                    if result is not None:
                        self.assertTrue(isinstance(result, str))
                else:
                    self.assertTrue(
                        isinstance(result, response_to_type[kind.__class__]))

        performed = self.protocol.callRemote(command, **kwargs)
        return performed.addCallback(assert_response)

    def test_amp_rpc_commands(self):
        """
        All accepted L{BrokerServerProtocol} commands issued by a connected
        client are correctly performed.  The appropriate L{BrokerServer}
        methods are called with the correct arguments.
        """
        # We need this in order to make the message store happy
        self.mstore.set_accepted_types(["test"])
        doit = Deferred()
        for command in [RegisterClient, SendMessage, IsMessagePending,
                        StopClients, ReloadConfiguration, Register,
                        GetAcceptedMessageTypes, GetServerUuid,
                        RegisterClientAcceptedMessageType, Ping, Exit]:
            doit.addCallback(lambda x: self.assert_amp_rpc(command,
                                                           self.broker))
        doit.callback(None)
        return doit

    def test_send_message_amp_rpc(self):
        """Test that C{SendMessage} commands a correctly performed."""
        self.mstore.set_accepted_types(["test"])
        return self.assert_amp_rpc(SendMessage, self.broker)

    def test_register_client(self):
        """
        The L{RegisterComponent} command of the L{BrokerServerProtocol}
        forwards a registration request to the broker object of the protocol
        factory.
        """

        def assert_response(response):
            self.assertEquals(response, {})
            [client] = self.broker.get_clients()
            self.assertEquals(client.name, "client")
            self.assertTrue(isinstance(client._protocol, BrokerServerProtocol))

        performed = self.protocol.callRemote(RegisterClient, name="client")
        return performed.addCallback(assert_response)

    def test_send_message(self):
        """
        The L{SendComponent} command of the L{BrokerServerProtocol} forwards
        a message for the Landscape server to the broker object of the
        protocol factory.
        """
        message = {"type": "test"}
        self.mstore.set_accepted_types(["test"])

        def assert_response(response):
            self.assertTrue(self.mstore.is_pending(response["result"]))
            self.assertMessages(self.mstore.get_pending_messages(),
                                [message])

        performed = self.protocol.callRemote(SendMessage, message=message,
                                             urgent=True)
        return performed.addCallback(assert_response)

    def test_is_pending_message(self):
        """
        The L{RegisterComponent} command of the forwards a registration
        request to the broker object of the protocol factory.
        """

        def assert_response(response):
            self.assertEquals(response, {"result": False})

        performed = self.protocol.callRemote(IsMessagePending, message_id=3)
        return performed.addCallback(assert_response)

    def test_register_client_accepted_message_type(self):
        """
        The L{RegisterClientAccpetedMessageType} command of the broker protocol
        forwards to the broker the request to register a new message type that
        can be accepted by the client.
        """

        def assert_response(response):
            self.assertEquals(response, {})
            self.assertEquals(
                self.exchanger.get_client_accepted_message_types(),
                sorted(["type"] + DEFAULT_ACCEPTED_TYPES))

        performed = self.protocol.callRemote(RegisterClientAcceptedMessageType,
                                             type="type")
        return performed.addCallback(assert_response)
