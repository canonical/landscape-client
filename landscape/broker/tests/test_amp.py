from landscape.lib.amp import MethodCall, MethodCallError
from landscape.broker.amp import (
    BrokerServerProtocol, BrokerServerProtocolFactory)
from landscape.tests.helpers import LandscapeTest, DEFAULT_ACCEPTED_TYPES
from landscape.broker.tests.helpers import BrokerProtocolHelper


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

    helpers = [BrokerProtocolHelper]

    def test_ping(self):
        """
        When sent a L{MethodCall} command with C{ping} as parameter, the
        L{BrokerServerProtocol} forwards the request to the L{BrokerServer}
        instance of its protocol factory.
        """
        result = self.protocol.callRemote(MethodCall,
                                          name="ping",
                                          args=[],
                                          kwargs={})
        return self.assertSuccess(result, {"result": True})

    def test_register_client(self):
        """
        When sent a L{MethodCall} command with C{register_client} as parameter,
        the L{BrokerServerProtocol} forwards the registration request to the
        broker object of the protocol factory.
        """

        def assert_response(response):
            self.assertEquals(response, {"result": None})
            [client] = self.broker.get_clients()
            self.assertEquals(client.name, "client")
            self.assertTrue(isinstance(client._protocol, BrokerServerProtocol))

        result = self.protocol.callRemote(MethodCall,
                                          name="register_client",
                                          args=["client"],
                                          kwargs={"_protocol": ""})
        return result.addCallback(assert_response)

    def test_send_message(self):
        """
        When sent a L{MethodCall} command with C{send_message} as parameter,
        the L{BrokerServerProtocol} forwards the request to the L{BrokerServer}
        instance of its protocol factory.
        """
        message = {"type": "test"}
        self.mstore.set_accepted_types(["test"])

        def assert_response(response):
            self.assertTrue(self.mstore.is_pending(response["result"]))
            self.assertMessages(self.mstore.get_pending_messages(),
                                [message])

        result = self.protocol.callRemote(MethodCall,
                                          name="send_message",
                                          args=[message],
                                          kwargs={"urgent": True})
        return result.addCallback(assert_response)

    def test_is_pending_message(self):
        """
        When sent a L{MethodCall} command with C{is_pending_message} as
        parameter, the L{BrokerServerProtocol} forwards the request to
        the L{BrokerServer} instance of its protocol factory.
        """
        result = self.protocol.callRemote(MethodCall,
                                          name="is_message_pending",
                                          args=[3],
                                          kwargs={})
        return self.assertSuccess(result, {"result": False})

    def test_stop_clients(self):
        """
        When sent a L{MethodCall} command with C{stop_clients} as parameter,
        the L{BrokerServerProtocol} forwards the request to the L{BrokerServer}
        instance of its protocol factory.
        """
        result = self.protocol.callRemote(MethodCall,
                                          name="stop_clients",
                                          args=[],
                                          kwargs={})
        return self.assertSuccess(result, {"result": None})

    def test_reload_configuration(self):
        """
        When sent a L{MethodCall} command with C{reload_configuration} as
        parameter, the L{BrokerServerProtocol} forwards the request to
        the L{BrokerServer} instance of its protocol factory.
        """
        result = self.protocol.callRemote(MethodCall,
                                          name="reload_configuration",
                                          args=[],
                                          kwargs={})
        return self.assertSuccess(result, {"result": None})

    def test_register(self):
        """
        When sent a L{MethodCall} command with C{register} as parameter,
        the L{BrokerServerProtocol} forwards the request to the L{BrokerServer}
        instance of its protocol factory.
        """
        result = self.protocol.callRemote(MethodCall,
                                          name="register",
                                          args=[],
                                          kwargs={})
        return self.assertSuccess(result, {"result": None})

    def test_get_accepted_message_types(self):
        """
        When sent a L{MethodCall} command with C{get_accepted_message_types} as
        parameter, the L{BrokerServerProtocol} forwards the request to the
        L{BrokerServer} instance of its protocol factory.
        """
        result = self.protocol.callRemote(MethodCall,
                                          name="get_accepted_message_types",
                                          args=[],
                                          kwargs={})
        return self.assertSuccess(result, {"result":
                                           self.mstore.get_accepted_types()})

    def test_get_server_uuid(self):
        """
        When sent a L{MethodCall} command with C{get_server_uuid} as
        parameter, the L{BrokerServerProtocol} forwards the request to the
        L{BrokerServer} instance of its protocol factory.
        """
        self.mstore.set_server_uuid("abcde")
        result = self.protocol.callRemote(MethodCall,
                                          name="get_server_uuid",
                                          args=[],
                                          kwargs={})
        return self.assertSuccess(result, {"result": "abcde"})

    def test_register_client_accepted_message_type(self):
        """
        The L{RegisterClientAccpetedMessageType} command of the broker protocol
        forwards to the broker the request to register a new message type that
        can be accepted by the client.
        """

        def assert_response(response):
            self.assertEquals(response, {"result": None})
            self.assertEquals(
                self.exchanger.get_client_accepted_message_types(),
                sorted(["type"] + DEFAULT_ACCEPTED_TYPES))

        result = self.protocol.callRemote(MethodCall,
                                          name="register_client_accepted_"
                                               "message_type",
                                          args=["type"],
                                          kwargs={})
        return result.addCallback(assert_response)

    def test_exit(self):
        """
        When sent a L{MethodCall} command with C{exit} as parameter, the
        L{BrokerServerProtocol} forwards the request to the L{BrokerServer}
        instance of its protocol factory.
        """
        result = self.protocol.callRemote(MethodCall,
                                          name="exit",
                                          args=[],
                                          kwargs={})
        return self.assertSuccess(result, {"result": None})

    def test_method_call_error(self):
        """
        Trying to call an non-exposed broker method results in a failure.
        """
        result = self.protocol.callRemote(MethodCall,
                                          name="get_clients",
                                          args=[],
                                          kwargs={})
        return self.assertFailure(result, MethodCallError)
