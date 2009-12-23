from twisted.internet.defer import DeferredList, succeed
from twisted.protocols.amp import String, Integer, Boolean


from landscape.lib.amp import ProtocolAttribute, StringOrNone
from landscape.broker.amp import (
    BrokerServerProtocol, BrokerServerProtocolFactory, Message, Types,
    RegisterClient, BROKER_SERVER_METHOD_CALLS, SendMessage,
    RegisterClientAcceptedMessageType, IsMessagePending, DispatchMessage,
    BROKER_CLIENT_METHOD_CALLS, RemoteClient)
from landscape.tests.helpers import LandscapeTest, DEFAULT_ACCEPTED_TYPES
from landscape.broker.tests.helpers import (
    BrokerProtocolHelper, RemoteBrokerHelper, BrokerClientHelper)

ARGUMENT_SAMPLES = {String: "some_sring",
                    Boolean: True,
                    Integer: 123,
                    Message: {"type": "test"}}

ARGUMENT_TYPES = {String: str,
                  Boolean: bool,
                  Integer: int,
                  Message: dict,
                  Types: list}


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


class MethodCallTestMixin(object):

    def _create_method_wrapper(self, object, method_name, calls):
        """
        Replace the method named C{method_name} of the given C{object} with a
        wrapper which will behave exactly as the original method but will also
        append a C{True} element to the given C{calls} list upon invokation.

        After the wrapper is called, it's replaced back with the original
        object's method
        """
        original_method = getattr(object, method_name)

        def method_wrapper(*args, **kwargs):
            calls.append(True)
            result = original_method(*args, **kwargs)
            setattr(object, method_name, original_method)
            return result

        setattr(object, method_name, method_wrapper)

    def assert_responder(self, protocol, method_call, object):
        """
        Assert that an C{AMP.callRemote} invocation on the given C{protocol}
        against the given AMP c{method_call}, actually calls the appropriate
        target method of the given C{object).
        """
        kwargs = {}
        method_name = method_call.get_method_name()

        # Wrap the object method with one that will keep track of its calls
        calls = []
        self._create_method_wrapper(object, method_name, calls)

        for name, kind in method_call.arguments:
            if kind.__class__ is ProtocolAttribute:
                # Skip protocol attribute arguments
                continue
            kwargs[name] = ARGUMENT_SAMPLES[kind.__class__]

        def assert_response(response):
            self.assertEquals(calls, [True])
            if method_call.response:
                name, kind = method_call.response[0]
                result = response[name]
                if isinstance(kind, StringOrNone):
                    if result is not None:
                        self.assertTrue(isinstance(result, str))
                else:
                    self.assertTrue(
                        isinstance(result, ARGUMENT_TYPES[kind.__class__]))

        performed = protocol.callRemote(method_call, **kwargs)
        return performed.addCallback(assert_response)

    def assert_sender(self, remote, method_call, object):
        """
        Assert that the C{remote}'s method decorated with C{method_call.sender}
        sends the appropriate AMP command and the matching target C{object}'s
        method eventually gets called with the proper arguments.
        """
        args = []

        # Wrap the object method with one that will keep track of its calls
        method_name = method_call.get_method_name()
        calls = []
        self._create_method_wrapper(object, method_name, calls)

        for name, kind in method_call.arguments:
            if kind.__class__ is ProtocolAttribute:
                # Skip hidden arguments
                continue
            args.append(ARGUMENT_SAMPLES[kind.__class__])

        def assert_result(result):
            self.assertEquals(calls, [True])
            if method_call.response:
                name, kind = method_call.response[0]
                if isinstance(kind, StringOrNone):
                    if result is not None:
                        self.assertTrue(isinstance(result, str))
                else:
                    self.assertTrue(
                        isinstance(result, ARGUMENT_TYPES[kind.__class__]))

        performed = getattr(remote, method_name)(*args)
        return performed.addCallback(assert_result)


class BrokerServerProtocolTest(LandscapeTest, MethodCallTestMixin):

    helpers = [BrokerProtocolHelper]

    def test_responders(self):
        """
        All accepted L{BrokerServerProtocol} commands issued by a connected
        client are correctly performed.  The appropriate L{BrokerServer}
        methods are called with the correct arguments.
        """
        # We need this in order to make the message store happy
        self.mstore.set_accepted_types(["test"])

        # Mock the remote client's exit methods
        remote_client_mock = self.mocker.patch(RemoteClient)
        remote_client_mock.exit()
        self.mocker.result(succeed(None))
        self.mocker.count(1, None)
        self.mocker.replay()

        performed = []
        for method_call in BROKER_SERVER_METHOD_CALLS:
            performed.append(self.assert_responder(self.protocol, method_call,
                                                   self.broker))
        return DeferredList(performed, fireOnOneErrback=True)

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


class RemoteBrokerTest(LandscapeTest, MethodCallTestMixin):

    helpers = [RemoteBrokerHelper]

    def test_wb_set_client(self):
        """
        The C{client} attribute of a L{RemoteBroker} passes a references to
        the connected L{BrokerClient} to the underlying protocol.
        """
        client = object()
        self.remote.client = client
        self.assertIdentical(self.remote._protocol.client, client)

    def test_senders(self):
        """
        The L{BrokerClientProtocol} methods decorated with C{MethodCall.sender}
        can be used to call methods on the remote broker object.
        """
        # We need this in order to make the message store happy
        self.mstore.set_accepted_types(["test"])
        sent = []

        # Mock the remote client's exit methods
        remote_client_mock = self.mocker.patch(RemoteClient)
        remote_client_mock.exit()
        self.mocker.result(succeed(None))
        self.mocker.count(1, None)
        self.mocker.replay()

        for method_call in BROKER_SERVER_METHOD_CALLS:
            sent.append(self.assert_sender(self.remote, method_call,
                                           self.broker))
        return DeferredList(sent, fireOnOneErrback=True)

    def test_register_client(self):
        """
        The L{BrokerClientProtocol.register_client} method forwards a
        registration request to the broker object.
        """

        def assert_result(result):
            self.assertEquals(result, None)
            [client] = self.broker.get_clients()
            self.assertEquals(client.name, "client")

        sent = self.remote.register_client("client")
        return sent.addCallback(assert_result)


class BrokerClientProtocolTest(LandscapeTest, MethodCallTestMixin):

    helpers = [BrokerClientHelper]

    def setUp(self):

        def register_client(ignored):

            def set_client_protocol(ignored):
                [remote_client] = self.broker.get_clients()
                self.client_protocol = remote_client._protocol

            registered = self.remote.register_client("test")
            return registered.addCallback(set_client_protocol)

        connected = super(BrokerClientProtocolTest, self).setUp()
        return connected.addCallback(register_client)

    def test_responders(self):
        """
        The L{BrokerClientProtocol} methods decorated with the
        L{MethodCall.responder} decorator response to the associated AMP
        commands and call the proper L{BrokerClient} methods.
        """

        def assert_responders(ignored):

            performed = []
            for method_call in BROKER_CLIENT_METHOD_CALLS:
                performed.append(self.assert_responder(self.client_protocol,
                                                       method_call,
                                                       self.client))
            return DeferredList(performed, fireOnOneErrback=True)

        # We need to register a test message handler to let the DispatchMessage
        # method call succeed
        registered = self.client.register_message("test", lambda x: object())
        return registered.addCallback(assert_responders)

    def test_dispatch_message_with_handler_not_found(self):
        """
        If a L{BrokerClient} can't find a handler for the given message,
        the L{Dispatch} method call returns C{False} as its result.
        """

        def assert_result(result):
            self.assertEquals(result, {"result": False})

        sent = self.client_protocol.callRemote(DispatchMessage,
                                               message={"type": "test"})
        return sent.addCallback(assert_result)


class RemoteClientTest(LandscapeTest, MethodCallTestMixin):

    helpers = [BrokerClientHelper]

    def setUp(self):

        def register_client(ignored):

            def set_remote_client(ignored):
                [remote_client] = self.broker.get_clients()
                self.remote_client = remote_client

            registered = self.remote.register_client("test")
            return registered.addCallback(set_remote_client)

        connected = super(RemoteClientTest, self).setUp()
        return connected.addCallback(register_client)

    def test_senders(self):
        """
        The L{RemoteClient} methods decorated with the L{MethodCall.responder}
        decorator send the associated AMP commands and eventually call the
        proper L{BrokerClient} methods.
        """

        def assert_senders(ignored):

            sent = []
            for method_call in BROKER_CLIENT_METHOD_CALLS:
                sent.append(self.assert_sender(self.remote_client,
                                               method_call, self.client))
            return DeferredList(sent, fireOnOneErrback=True)

        # We need to register a test message handler to let the DispatchMessage
        # method call succeed
        registered = self.client.register_message("test", lambda x: object())
        return registered.addCallback(assert_senders)

    def test_dispatch_message_with_handler_not_found(self):
        """
        The L{RemoteClient.dispatch_message} method results in C{False} if
        no handler for the given message was defined.
        """

        def assert_result(result):
            self.assertEquals(result, False)

        sent = self.remote_client.dispatch_message({"type": "test"})
        return sent.addCallback(assert_result)
