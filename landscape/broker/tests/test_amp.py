from twisted.internet.defer import DeferredList

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

    def assert_responder(self, protocol, name, args, kwargs, result, object):
        """
        Send a L{MethodCall} over the given C{protocol} and with the given
        parameters, asserting that the proper C{object} method gets actually
        called and the correct C{result} returned.

        @param protocol: the L{AMP} protocol to send the L{MethodCall} over
        @param name: The C{name} parameter of the L{MethodCall}
        @param args: The C{args} parameter of the L{MethodCall}
        @param kwargs: The C{kwargs} parameter of the L{MethodCall}
        @param result: The expected result value or type
        @param object: The target object the to invoke methods on
        """
        calls = []
        self._create_method_wrapper(object, name, calls)

        def assert_response(response):
            self.assertEquals(calls, [True])
            if isinstance(result, type):
                self.assertTrue(isinstance(response["result"], result))
            else:
                self.assertEquals(response, {"result": result})

        performed = protocol.callRemote(MethodCall, name=name, args=args,
                                        kwargs=kwargs)
        return performed.addCallback(assert_response)


class BrokerServerProtocolTest(LandscapeTest, MethodCallTestMixin):

    helpers = [BrokerProtocolHelper]

    def test_commands(self):
        """
        All accepted L{MethodCall} commands issued by a connected client
        are correctly performed.  The appropriate L{BrokerServer} methods
        are called with the correct arguments.
        """
        # We need this in order to make the message store happy
        self.mstore.set_accepted_types(["test"])

        calls = {"ping": {"result": True},
                 "register_client": {"args": ["client"],
                                     "kwargs": {"_protocol": ""}},
                 "send_message": {"args": [{"type": "test"}],
                                  "result": int},
                 "is_message_pending": {"args": [1234567],
                                        "result": False},
                 "stop_clients": {},
                 "reload_configuration": {},
                 "register": {},
                 "get_accepted_message_types": {"result": list},
                 "get_server_uuid": {"result": None},
                 "register_client_accepted_message_type": {"args": ["test"]},
                 "exit": {}}

        performed = []
        for name in calls:
            call = calls[name]
            performed.append(self.assert_responder(self.protocol,
                                                   name,
                                                   call.get("args", []),
                                                   call.get("kwargs", {}),
                                                   call.get("result", None),
                                                   self.broker))
        return DeferredList(performed, fireOnOneErrback=True)

    def test_register_client(self):
        """
        The L{RegisterComponent} command of the L{BrokerServerProtocol}
        forwards a registration request to the broker object of the protocol
        factory.
        """

        def assert_response(response):
            self.assertEquals(response, {"result": None})
            [client] = self.broker.get_clients()
            self.assertEquals(client.name, "client")
            self.assertTrue(isinstance(client._protocol, BrokerServerProtocol))

        performed = self.protocol.callRemote(MethodCall,
                                             name="register_client",
                                             args=["client"],
                                             kwargs={"_protocol": ""})
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

        performed = self.protocol.callRemote(MethodCall,
                                             name="send_message",
                                             args=[message],
                                             kwargs={"urgent": True})
        return performed.addCallback(assert_response)

    def test_is_pending_message(self):
        """
        The L{RegisterComponent} command of the forwards a registration
        request to the broker object of the protocol factory.
        """

        def assert_response(response):
            self.assertEquals(response, {"result": False})

        performed = self.protocol.callRemote(MethodCall,
                                             name="is_message_pending",
                                             args=[3], kwargs={})
        return performed.addCallback(assert_response)

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

        performed = self.protocol.callRemote(MethodCall,
                                             name="register_client_accepted_"
                                                  "message_type",
                                             args=["type"], kwargs={})
        return performed.addCallback(assert_response)

    def test_method_call_error(self):
        """
        Trying to call an non-exposed broker method results in a failure.
        """
        performed = self.protocol.callRemote(MethodCall, name="get_clients",
                                             args=[], kwargs={})
        return self.assertFailure(performed, MethodCallError)
