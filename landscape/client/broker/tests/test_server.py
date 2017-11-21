import random

from configobj import ConfigObj
from mock import Mock
from twisted.internet.defer import succeed, fail

from landscape.client.manager.manager import FAILED
from landscape.client.tests.helpers import (
        LandscapeTest, DEFAULT_ACCEPTED_TYPES)
from landscape.client.broker.tests.helpers import (
    BrokerServerHelper, RemoteClientHelper)
from landscape.client.broker.tests.test_ping import FakePageGetter


class FakeClient(object):
    pass


class FakeCreator(object):

    def __init__(self, reactor, config):
        pass

    def connect(self):
        return succeed(FakeClient())


class BrokerServerTest(LandscapeTest):

    helpers = [BrokerServerHelper]

    def test_ping(self):
        """
        The L{BrokerServer.ping} simply returns C{True}.
        """
        self.assertTrue(self.broker.ping())

    def test_get_session_id(self):
        """
        The L{BrokerServer.get_session_id} method gets the same
        session ID from the L{MessageStore} until it is dropped.
        """
        session_id1 = self.broker.get_session_id()
        session_id2 = self.broker.get_session_id()
        self.assertEqual(session_id1, session_id2)
        self.mstore.drop_session_ids()
        session_id3 = self.broker.get_session_id()
        self.assertNotEqual(session_id1, session_id3)

    def test_get_session_id_with_scope(self):
        """
        The L{BrokerServer.get_session_id} method gets the same session ID from
        the L{MessageStore} for the same scope, but a new session ID for a new
        scope.
        """
        disk_session_id1 = self.broker.get_session_id(scope="disk")
        disk_session_id2 = self.broker.get_session_id(scope="disk")
        users_session_id = self.broker.get_session_id(scope="users")
        self.assertEqual(disk_session_id1, disk_session_id2)
        self.assertNotEqual(disk_session_id1, users_session_id)

    def test_send_message(self):

        """
        The L{BrokerServer.send_message} method forwards a message to the
        broker's exchanger.
        """
        message = {"type": "test"}
        self.mstore.set_accepted_types(["test"])
        session_id = self.broker.get_session_id()
        self.broker.send_message(message, session_id)
        self.assertMessages(self.mstore.get_pending_messages(), [message])
        self.assertFalse(self.exchanger.is_urgent())

    def test_send_message_with_urgent(self):
        """
        The L{BrokerServer.send_message} can optionally specify the urgency
        of the message.
        """
        message = {"type": "test"}
        self.mstore.set_accepted_types(["test"])
        session_id = self.broker.get_session_id()
        self.broker.send_message(message, session_id, urgent=True)
        self.assertMessages(self.mstore.get_pending_messages(), [message])
        self.assertTrue(self.exchanger.is_urgent())

    def test_send_message_wont_send_with_invalid_session_id(self):
        """
        The L{BrokerServer.send_message} call will silently drop messages
        that have invalid session ids as they must have been generated
        prior to the last resync request - this guards against out of
        context data being sent to the server.
        """
        message = {"type": "test"}
        self.mstore.set_accepted_types(["test"])
        self.broker.send_message(message, "Not Valid")
        self.assertMessages(self.mstore.get_pending_messages(), [])

    def test_send_message_with_none_as_session_id_raises(self):
        """
        We should never call C{send_message} without first obtaining a session
        id.  Attempts to do so should raise to alert the developer to their
        mistake.
        """
        message = {"type": "test"}
        self.mstore.set_accepted_types(["test"])
        self.assertRaises(
            RuntimeError, self.broker.send_message, message, None)

    def test_send_message_with_old_release_upgrader(self):
        """
        If we receive a message from an old release-upgrader process that
        doesn't know about session IDs, we just let the message in.
        """
        message = {"type": "operation-result", "operation-id": 99, "status": 5}
        self.mstore.set_accepted_types(["operation-result"])
        self.broker.send_message(message, True)
        self.assertMessages(self.mstore.get_pending_messages(), [message])
        self.assertTrue(self.exchanger.is_urgent())

    def test_send_message_with_old_package_changer(self):
        """
        If we receive a message from an old package-changer process that
        doesn't know about session IDs, we just let the message in.
        """
        message = {"type": "change-packages-result", "operation-id": 99,
                   "result-code": 123}
        self.mstore.set_accepted_types(["change-packages-result"])
        self.broker.send_message(message, True)
        self.assertMessages(self.mstore.get_pending_messages(), [message])
        self.assertTrue(self.exchanger.is_urgent())

    def test_is_pending(self):
        """
        The L{BrokerServer.is_pending} method indicates if a message with
        the given id is pending waiting for delivery in the message store.
        """
        self.assertFalse(self.broker.is_message_pending(123))
        message = {"type": "test"}
        self.mstore.set_accepted_types(["test"])
        session_id = self.broker.get_session_id()
        message_id = self.broker.send_message(message, session_id)
        self.assertTrue(self.broker.is_message_pending(message_id))

    def test_register_client(self):
        """
        The L{BrokerServer.register_client} method can be used to register
        client components that need to communicate with the server. After
        the registration they can be fetched with L{BrokerServer.get_clients}.
        """
        self.assertEqual(len(self.broker.get_clients()), 0)
        self.assertEqual(self.broker.get_client("test"), None)
        self.assertEqual(len(self.broker.get_connectors()), 0)
        self.assertEqual(self.broker.get_connector("test"), None)

        def assert_registered(ignored):
            self.assertEqual(len(self.broker.get_clients()), 1)
            self.assertEqual(len(self.broker.get_connectors()), 1)
            self.assertTrue(
                isinstance(self.broker.get_client("test"), FakeClient))
            self.assertTrue(
                isinstance(self.broker.get_connector("test"), FakeCreator))

        self.broker.connectors_registry = {"test": FakeCreator}
        result = self.broker.register_client("test")
        return result.addCallback(assert_registered)

    def test_stop_clients(self):
        """
        The L{BrokerServer.stop_clients} method calls the C{exit} method
        of each registered client, and returns a deferred resulting in C{None}
        if all C{exit} calls were successful.
        """
        self.broker.connectors_registry = {"foo": FakeCreator,
                                           "bar": FakeCreator}
        self.broker.register_client("foo")
        self.broker.register_client("bar")
        for client in self.broker.get_clients():
            client.exit = Mock(return_value=succeed(None))
        return self.assertSuccess(self.broker.stop_clients())

    def test_stop_clients_with_failure(self):
        """
        The L{BrokerServer.stop_clients} method calls the C{exit} method of
        each registered client, and raises an exception if any calls fail.
        """
        self.broker.connectors_registry = {"foo": FakeCreator,
                                           "bar": FakeCreator}
        self.broker.register_client("foo")
        self.broker.register_client("bar")
        [client1, client2] = self.broker.get_clients()
        client1.exit = Mock(return_value=succeed(None))
        client2.exit = Mock(return_value=fail(Exception()))
        return self.assertFailure(self.broker.stop_clients(), Exception)

    def test_reload_configuration(self):
        """
        The L{BrokerServer.reload_configuration} method forces the config
        file associated with the broker server to be reloaded.
        """
        config_obj = ConfigObj(self.config_filename)
        config_obj["client"]["computer_title"] = "New Title"
        config_obj.write()
        result = self.broker.reload_configuration()
        result.addCallback(lambda x: self.assertEqual(
            self.config.computer_title, "New Title"))
        return result

    def test_reload_configuration_stops_clients(self):
        """
        The L{BrokerServer.reload_configuration} method forces the config
        file associated with the broker server to be reloaded.
        """
        self.broker.connectors_registry = {"foo": FakeCreator,
                                           "bar": FakeCreator}
        self.broker.register_client("foo")
        self.broker.register_client("bar")
        for client in self.broker.get_clients():
            client.exit = Mock(return_value=succeed(None))
        return self.assertSuccess(self.broker.reload_configuration())

    def test_register(self):
        """
        The L{BrokerServer.register} method attempts to register with the
        Landscape server and waits for a C{set-id} message from it.
        """
        registered = self.broker.register()
        # This should callback the deferred.
        self.exchanger.handle_message({"type": "set-id", "id": "abc",
                                       "insecure-id": "def"})
        return self.assertSuccess(registered)

    def test_get_accepted_types_empty(self):
        """
        The L{BrokerServer.get_accepted_message_types} returns an empty list
        if no message types are accepted by the Landscape server.
        """
        self.mstore.set_accepted_types([])
        self.assertEqual(self.broker.get_accepted_message_types(), [])

    def test_get_accepted_message_types(self):
        """
        The L{BrokerServer.get_accepted_message_types} returns the list of
        message types accepted by the Landscape server.
        """
        self.mstore.set_accepted_types(["foo", "bar"])
        self.assertEqual(sorted(self.broker.get_accepted_message_types()),
                         ["bar", "foo"])

    def test_get_server_uuid_with_unset_uuid(self):
        """
        The L{BrokerServer.get_server_uuid} method returns C{None} if the uuid
        of the Landscape server we're pointing at is unknown.
        """
        self.assertEqual(self.broker.get_server_uuid(), None)

    def test_get_server_uuid(self):
        """
        The L{BrokerServer.get_server_uuid} method returns the uuid of the
        Landscape server we're pointing at.
        """
        self.mstore.set_server_uuid("the-uuid")
        self.assertEqual(self.broker.get_server_uuid(), "the-uuid")

    def test_register_client_accepted_message_type(self):
        """
        The L{BrokerServer.register_client_accepted_message_type} method can
        register new message types accepted by this Landscape client.
        """
        self.broker.register_client_accepted_message_type("type1")
        self.broker.register_client_accepted_message_type("type2")
        self.assertEqual(self.exchanger.get_client_accepted_message_types(),
                         sorted(["type1", "type2"] + DEFAULT_ACCEPTED_TYPES))

    def test_fire_event(self):
        """
        The L{BrokerServer.fire_event} method fires an event in the broker
        reactor.
        """
        callback = Mock()
        self.reactor.call_on("event", callback)
        self.broker.fire_event("event")

    def test_exit(self):
        """
        The L{BrokerServer.exit} method stops all registered clients.
        """
        self.broker.connectors_registry = {"foo": FakeCreator,
                                           "bar": FakeCreator}
        self.broker.register_client("foo")
        self.broker.register_client("bar")
        for client in self.broker.get_clients():
            client.exit = Mock(return_value=succeed(None))
        return self.assertSuccess(self.broker.exit())

    def test_exit_exits_when_other_daemons_blow_up(self):
        """
        If a broker client blow up in its exit() methods, exit should ignore
        the error and exit anyway.
        """
        self.broker.connectors_registry = {"foo": FakeCreator}
        self.broker.register_client("foo")
        [client] = self.broker.get_clients()
        client.exit = Mock(return_value=fail(ZeroDivisionError()))

        def assert_event(ignored):
            self.reactor.advance(1)

        result = self.broker.exit()
        return result.addCallback(assert_event)

    def test_exit_fires_reactor_events(self):
        """
        The L{BrokerServer.exit} method stops the reactor after having
        requested all broker clients to shutdown.
        """
        self.broker.connectors_registry = {"foo": FakeCreator}
        self.broker.register_client("foo")
        [client] = self.broker.get_clients()

        client.exit = Mock(return_value=fail(ZeroDivisionError()))
        self.reactor.stop = Mock()
        self.broker.stop_exchanger()
        self.reactor.stop()

        def assert_stopped(ignored):
            self.reactor.advance(1)

        result = self.broker.exit()
        return result.addCallback(assert_stopped)

    def test_listen_events(self):
        """
        The L{BrokerServer.listen_events} method returns a deferred which is
        fired when the first of the given events occurs.
        """
        deferred = self.broker.listen_events(["event1", "event2"])
        self.reactor.fire("event2")
        result = self.successResultOf(deferred)
        self.assertTrue(result is not None)

    def test_listen_events_with_payload(self):
        """
        The L{BrokerServer.listen_events} method returns a deferred which is
        fired when the first of the given events occurs. The result of the
        deferred is a 2-tuple with name of the event and any keyword arguments
        passed when the event was fired.
        """
        deferred = self.broker.listen_events(["event1", "event2"])
        self.reactor.fire("event2", foo=123)
        result = self.successResultOf(deferred)
        self.assertEqual(("event2", {"foo": 123}), result)

    def test_listen_event_only_once(self):
        """
        The L{BrokerServer.listen_events} listens only to one occurrence of
        the given events.
        """
        deferred = self.broker.listen_events(["event"])
        self.assertEqual(self.reactor.fire("event"), [None])
        self.assertEqual(self.reactor.fire("event"), [])
        result = self.successResultOf(deferred)
        self.assertEqual("event", result[0])

    def test_listen_events_call_cancellation(self):
        """
        The L{BrokerServer.listen_events} cleanly cancels event calls for
        unfired events, without interfering with unrelated handlers.
        """
        self.broker.listen_events(["event"])
        self.reactor.call_on("event", lambda: 123)  # Unrelated handler
        self.assertEqual(self.reactor.fire("event"), [None, 123])

    def test_stop_exchanger(self):
        """
        The L{BrokerServer.stop_exchanger} stops the exchanger so no further
        messages are sent or consumed.
        """
        self.pinger.start()
        self.exchanger.schedule_exchange()
        self.broker.stop_exchanger()

        self.reactor.advance(self.config.exchange_interval)
        self.assertFalse(self.transport.payloads)

    def test_stop_exchanger_stops_pinger(self):
        """
        The L{BrokerServer.stop_exchanger} stops the pinger and no further
        pings are performed.
        """
        url = "http://example.com/mysuperping"
        page_getter = FakePageGetter(None)
        self.pinger.start()
        self.config.ping_url = url
        self.pinger._ping_client.get_page = page_getter.get_page
        self.identity.insecure_id = 23

        self.broker.stop_exchanger()
        self.reactor.advance(self.config.exchange_interval)
        self.assertEqual([], page_getter.fetches)


class EventTest(LandscapeTest):

    helpers = [RemoteClientHelper]

    def test_resynchronize(self):
        """
        The L{BrokerServer.resynchronize} method broadcasts a C{resynchronize}
        event to all connected clients.
        """
        callback = Mock(return_value="foo")
        self.client_reactor.call_on("resynchronize", callback)
        return self.assertSuccess(self.broker.resynchronize(["foo"]),
                                  [["foo"]])

    def test_impending_exchange(self):
        """
        The L{BrokerServer.impending_exchange} method broadcasts an
        C{impending-exchange} event to all connected clients.
        """
        plugin = Mock()
        plugin.register = Mock()
        plugin.exchange = Mock()
        self.client.add(plugin)

        def assert_called(ignored):
            plugin.register.assert_called_once_with(self.client)
            plugin.exchange.assert_called_once_with()

        deferred = self.assertSuccess(
            self.broker.impending_exchange(), [[None]])
        deferred.addCallback(assert_called)
        return deferred

    def test_broker_started(self):
        """
        The L{BrokerServer.broker_started} method broadcasts a
        C{broker-started} event to all connected clients, which makes them
        re-registered any previously registered accepted message type.
        """

        def assert_broker_started(ignored):
            self.remote.register_client_accepted_message_type = Mock()
            self.remote.register_client = Mock()

            def assert_called_made(ignored):
                self.remote.register_client_accepted_message_type\
                    .assert_called_once_with("type")
                self.remote.register_client.assert_called_once_with("client")

            deferred = self.assertSuccess(
                self.broker.broker_reconnect(), [[None]])
            return deferred.addCallback(assert_called_made)

        registered = self.client.register_message("type", lambda x: None)
        return registered.addCallback(assert_broker_started)

    def test_server_uuid_changed(self):
        """
        The L{BrokerServer.server_uuid_changed} method broadcasts a
        C{server-uuid-changed} event to all connected clients.
        """
        return_value = random.randint(1, 100)
        callback = Mock(return_value=return_value)

        def assert_called(ignored):
            callback.assert_called_once_with(None, "abc")

        self.client_reactor.call_on("server-uuid-changed", callback)
        deferred = self.assertSuccess(
            self.broker.server_uuid_changed(None, "abc"), [[return_value]])
        return deferred.addCallback(assert_called)

    def test_message_type_acceptance_changed(self):
        """
        The L{BrokerServer.message_type_acceptance_changed} method broadcasts
        a C{message-type-acceptance-changed} event to all connected clients.
        """
        return_value = random.randint(1, 100)
        callback = Mock(return_value=return_value)
        self.client_reactor.call_on(
            ("message-type-acceptance-changed", "type"), callback)
        result = self.broker.message_type_acceptance_changed("type", True)
        return self.assertSuccess(result, [[return_value]])

    def test_package_data_changed(self):
        """
        The L{BrokerServer.package_data_changed} method broadcasts a
        C{package-data-changed} event to all connected clients.
        """
        return_value = random.randint(1, 100)
        callback = Mock(return_value=return_value)
        self.client_reactor.call_on("package-data-changed", callback)
        return self.assertSuccess(
            self.broker.package_data_changed(), [[return_value]])


class HandlersTest(LandscapeTest):

    helpers = [BrokerServerHelper]

    def setUp(self):
        super(HandlersTest, self).setUp()
        self.broker.connectors_registry = {"test": FakeCreator}
        self.broker.register_client("test")
        self.client = self.broker.get_client("test")

    def test_message(self):
        """
        The L{BrokerServer} calls the C{message} method on all
        registered plugins when messages are received from the server.
        """
        message = {"type": "foobar", "value": 42}
        self.client.message = Mock(return_value=succeed(True))
        self.transport.responses.append([{"type": "foobar", "value": 42}])
        self.exchanger.exchange()
        self.client.message.assert_called_once_with(message)

    def test_message_failed_operation_without_plugins(self):
        """
        When there are no broker plugins available to handle a message, an
        operation-result message should be sent back to the server indicating a
        failure.
        """
        self.log_helper.ignore_errors("Nobody handled the foobar message.")
        self.mstore.set_accepted_types(["operation-result"])
        message = {"type": "foobar", "operation-id": 4}
        self.client.message = Mock(return_value=succeed(False))
        result = self.reactor.fire("message", message)
        result = [i for i in result if i is not None][0]

        class StartsWith(object):

            def __eq__(self, other):
                return other.startswith(
                    "Landscape client failed to handle this request (foobar)")

        def broadcasted(ignored):
            self.client.message.assert_called_once_with(message)
            self.assertMessages(
                self.mstore.get_pending_messages(),
                [{"type": "operation-result", "status": FAILED,
                  "result-text": StartsWith(), "operation-id": 4}])

        result.addCallback(broadcasted)
        return result

    def test_impending_exchange(self):
        """
        When an C{impending-exchange} event is fired by the reactor, the
        broker broadcasts it to its clients.
        """
        self.client.fire_event = Mock(return_value=succeed(None))
        self.reactor.fire("impending-exchange")
        self.client.fire_event.assert_called_once_with("impending-exchange")

    def test_message_type_acceptance_changed(self):
        """
        When a C{message-type-acceptance-changed} event is fired by the
        reactor, the broker broadcasts it to its clients.
        """
        self.client.fire_event = Mock(return_value=succeed(None))
        self.reactor.fire("message-type-acceptance-changed", "test", True)
        self.client.fire_event.assert_called_once_with(
            "message-type-acceptance-changed", "test", True)

    def test_server_uuid_changed(self):
        """
        When a C{server-uuid-changed} event is fired by the reactor, the
        broker broadcasts it to its clients.
        """
        self.client.fire_event = Mock(return_value=succeed(None))
        self.reactor.fire("server-uuid-changed", None, 123)
        self.client.fire_event.assert_called_once_with(
            "server-uuid-changed", None, 123)

    def test_package_data_changed(self):
        """
        When a C{package-data-changed} event is fired by the reactor, the
        broker broadcasts it to its clients.
        """
        self.client.fire_event = Mock(return_value=succeed(None))
        self.reactor.fire("package-data-changed")
        self.client.fire_event.assert_called_once_with("package-data-changed")

    def test_resynchronize_clients(self):
        """
        When a C{resynchronize} event is fired by the reactor, the
        broker broadcasts it to its clients.
        """
        self.client.fire_event = Mock(return_value=succeed(None))
        self.reactor.fire("resynchronize-clients")
        self.client.fire_event.assert_called_once_with("resynchronize")
