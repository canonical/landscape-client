from landscape.lib.amp import MethodCall, MethodCallError
from landscape.broker.amp import (
    BrokerServerProtocol, BrokerServerProtocolFactory)
from landscape.tests.helpers import LandscapeTest, DEFAULT_ACCEPTED_TYPES
from landscape.broker.tests.helpers import (
    BrokerProtocolHelper, RemoteBrokerHelper)


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


class RemoteBrokerTest(LandscapeTest):

    helpers = [RemoteBrokerHelper]

    def test_ping(self):
        """
        The L{RemoteBroker.ping} method calls the C{ping} method of the
        remote L{BrokerServer} instance and returns its result with a
        L{Deferred}.
        """
        result = self.remote.ping()
        return self.assertSuccess(result, True)

    def test_register_client(self):
        """
        The L{RemoteBroker.register_client} method forwards a registration
        request to the remote L{BrokerServer} object.
        """

        def assert_result(result):
            self.assertEquals(result, None)
            [client] = self.broker.get_clients()
            self.assertEquals(client.name, "client")

        sent = self.remote.register_client("client")
        return sent.addCallback(assert_result)

    def test_send_message(self):
        """
        The L{RemoteBroker.send_message} method calls the C{send_message}
        method of the remote L{BrokerServer} instance and returns its result
        with a L{Deferred}.
        """
        message = {"type": "test"}
        self.mstore.set_accepted_types(["test"])

        def assert_response(message_id):
            self.assertTrue(isinstance(message_id, int))
            self.assertTrue(self.mstore.is_pending(message_id))
            self.assertMessages(self.mstore.get_pending_messages(),
                                [message])

        result = self.remote.send_message(message, urgent=True)
        return result.addCallback(assert_response)

    def test_is_message_pending(self):
        """
        The L{RemoteBroker.is_message_pending} method calls the
        C{is_message_pending} method of the remote L{BrokerServer} instance
        and returns its result with a L{Deferred}.
        """
        result = self.remote.is_message_pending(1234)
        return self.assertSuccess(result, False)

    def test_stop_clients(self):
        """
        The L{RemoteBroker.stop_clients} method calls the C{stop_clients}
        method of the remote L{BrokerServer} instance and returns its result
        with a L{Deferred}.
        """
        result = self.remote.stop_clients()
        return self.assertSuccess(result, None)

    def test_reload_configuration(self):
        """
        The L{RemoteBroker.reload_configuration} method calls the
        C{reload_configuration} method of the remote L{BrokerServer}
        instance and returns its result with a L{Deferred}.
        """
        result = self.remote.reload_configuration()
        return self.assertSuccess(result, None)

    def test_register(self):
        """
        The L{RemoteBroker.register} method calls the C{register} method
        of the remote L{BrokerServer} instance and returns its result with
        a L{Deferred}.
        """
        result = self.remote.register()
        return self.assertSuccess(result, None)

    def test_get_accepted_message_types(self):
        """
        The L{RemoteBroker.get_accepted_message_types} method calls the
        C{get_accepted_message_types} method of the remote L{BrokerServer}
        instance and returns its result with a L{Deferred}.
        """
        result = self.remote.get_accepted_message_types()
        return self.assertSuccess(result, self.mstore.get_accepted_types())

    def test_get_server_uuid(self):
        """
        The L{RemoteBroker.get_server_uuid} method calls the C{get_server_uuid}
        method of the remote L{BrokerServer} instance and returns its result
        with a L{Deferred}.
        """
        self.mstore.set_server_uuid("abcde")
        result = self.remote.get_server_uuid()
        return self.assertSuccess(result, "abcde")

    def test_register_client_accepted_message_type(self):
        """
        The L{RemoteBroker.register_client_accepted_message_type} method calls
        the C{register_client_accepted_message_type} method of the remote
        L{BrokerServer} instance and returns its result with a L{Deferred}.
        """

        def assert_response(response):
            self.assertEquals(response, None)
            self.assertEquals(
                self.exchanger.get_client_accepted_message_types(),
                sorted(["type"] + DEFAULT_ACCEPTED_TYPES))

        result = self.remote.register_client_accepted_message_type("type")
        return result.addCallback(assert_response)

    def test_exit(self):
        """
        The L{RemoteBroker.exit} method calls the C{exit} method of the remote
        L{BrokerServer} instance and returns its result with a L{Deferred}.
        """
        result = self.remote.exit()
        return self.assertSuccess(result, None)
