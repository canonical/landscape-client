import mock

from landscape.lib.amp import MethodCallError
from landscape.client.tests.helpers import (
        LandscapeTest, DEFAULT_ACCEPTED_TYPES)
from landscape.client.broker.tests.helpers import (
    RemoteBrokerHelper, RemoteClientHelper)


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
        self.broker.register_client = mock.Mock(return_value=None)
        result = self.remote.register_client("client")
        self.successResultOf(result)
        self.broker.register_client.assert_called_once_with("client")

    def test_send_message(self):
        """
        The L{RemoteBroker.send_message} method calls the C{send_message}
        method of the remote L{BrokerServer} instance and returns its result
        with a L{Deferred}.
        """
        message = {"type": "test"}
        self.mstore.set_accepted_types(["test"])

        session_id = self.successResultOf(self.remote.get_session_id())
        message_id = self.successResultOf(
            self.remote.send_message(message, session_id))

        self.assertTrue(isinstance(message_id, int))
        self.assertTrue(self.mstore.is_pending(message_id))
        self.assertFalse(self.exchanger.is_urgent())
        self.assertMessages(self.mstore.get_pending_messages(),
                            [message])

    def test_send_message_with_urgent(self):
        """
        The L{RemoteBroker.send_message} method honors the urgent argument.
        """
        message = {"type": "test"}
        self.mstore.set_accepted_types(["test"])
        session_id = self.successResultOf(self.remote.get_session_id())
        message_id = self.successResultOf(self.remote.send_message(
            message, session_id, urgent=True))
        self.assertTrue(isinstance(message_id, int))
        self.assertTrue(self.exchanger.is_urgent())

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
        # This should make the registration succeed
        self.transport.responses.append([{"type": "set-id", "id": "abc",
                                          "insecure-id": "def"}])
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
            self.assertEqual(response, None)
            self.assertEqual(
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

    def test_call_if_accepted(self):
        """
        The L{RemoteBroker.call_if_accepted} method calls a function if the
        given message type is accepted.
        """
        self.mstore.set_accepted_types(["test"])
        function = mock.Mock(return_value="cool")
        result = self.remote.call_if_accepted("test", function, 123)
        self.assertEqual("cool", self.successResultOf(result))
        function.assert_called_once_with(123)

    def test_call_if_accepted_with_not_accepted(self):
        """
        The L{RemoteBroker.call_if_accepted} method doesn't do anything if the
        given message type is not accepted.
        """
        function = (lambda: 1 / 0)
        result = self.remote.call_if_accepted("test", function)
        return self.assertSuccess(result, None)

    def test_listen_events(self):
        """
        L{RemoteBroker.listen_events} returns a deferred which fires when
        the first of the given events occurs in the broker reactor.
        """
        deferred = self.remote.listen_events(["event1", "event2"])
        self.reactor.call_later(0.05, self.reactor.fire, "event2")
        self.reactor.advance(0.05)
        self.remote._factory.fake_connection.flush()
        self.assertEqual(("event2", {}), self.successResultOf(deferred))

    def test_call_on_events(self):
        """
        L{RemoteBroker.call_on_events} fires the given callback when the
        first of the given events occurs in the broker reactor.
        """
        callback1 = mock.Mock()
        callback2 = mock.Mock(return_value=123)
        deferred = self.remote.call_on_event({"event1": callback1,
                                              "event2": callback2})
        self.reactor.call_later(0.05, self.reactor.fire, "event2")
        self.reactor.advance(0.05)
        self.remote._factory.fake_connection.flush()
        self.assertEqual(123, self.successResultOf(deferred))
        callback1.assert_not_called()
        callback2.assert_called_once_with()

    def test_fire_event(self):
        """
        The L{RemoteBroker.fire_event} method fires an event in the broker
        reactor.
        """
        callback = mock.Mock()
        self.reactor.call_on("event", callback)
        self.successResultOf(self.remote.fire_event("event"))
        callback.assert_called_once_with()

    def test_method_call_error(self):
        """
        Trying to call an non-exposed broker method results in a failure.
        """
        deferred = self.remote.get_clients()
        self.failureResultOf(deferred).trap(MethodCallError)


class RemoteClientTest(LandscapeTest):

    helpers = [RemoteClientHelper]

    def test_ping(self):
        """
        The L{RemoteClient.ping} method calls the C{ping} method of the
        remote L{BrokerClient} instance and returns its result with a
        L{Deferred}.
        """
        result = self.remote_client.ping()
        return self.assertSuccess(result, True)

    def test_message(self):
        """
        The L{RemoteClient.message} method calls the C{message} method of
        the remote L{BrokerClient} instance and returns its result with
        a L{Deferred}.
        """
        handler = mock.Mock()
        with mock.patch.object(self.client.broker,
                               "register_client_accepted_message_type") as m:
            # We need to register a test message handler to let the dispatch
            # message method call succeed
            self.client.register_message("test", handler)
            result = self.remote_client.message({"type": "test"})
            self.successResultOf(result)
            m.assert_called_once_with("test")
        handler.assert_called_once_with({"type": "test"})

    def test_fire_event(self):
        """
        The L{RemoteClient.fire_event} method calls the C{fire_event} method of
        the remote L{BrokerClient} instance and returns its result with a
        L{Deferred}.
        """
        callback = mock.Mock(return_value=None)
        self.client_reactor.call_on("event", callback)
        result = self.remote_client.fire_event("event", True, kwarg=2)
        self.assertEqual([None], self.successResultOf(result))
        callback.assert_called_once_with(True, kwarg=2)

    def test_exit(self):
        """
        The L{RemoteClient.exit} method calls the C{exit} method of the remote
        L{BrokerClient} instance and returns its result with a L{Deferred}.
        """
        result = self.remote_client.exit()
        return self.assertSuccess(result, None)

    def test_method_call_error(self):
        """
        Trying to call an non-exposed client method results in a failure.
        """
        deferred = self.remote_client.get_plugins()
        self.failureResultOf(deferred).trap(MethodCallError)
