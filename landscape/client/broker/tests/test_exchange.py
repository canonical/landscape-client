import mock

from landscape import CLIENT_API
from landscape.lib.persist import Persist
from landscape.lib.fetch import HTTPCodeError, PyCurlError
from landscape.lib.hashlib import md5
from landscape.lib.schema import Int
from landscape.message_schemas.message import Message
from landscape.client.broker.config import BrokerConfiguration
from landscape.client.broker.exchange import (
        get_accepted_types_diff, MessageExchange)
from landscape.client.broker.transport import FakeTransport
from landscape.client.broker.store import MessageStore
from landscape.client.broker.ping import Pinger
from landscape.client.broker.registration import RegistrationHandler
from landscape.client.tests.helpers import (
        LandscapeTest, DEFAULT_ACCEPTED_TYPES)
from landscape.client.broker.tests.helpers import ExchangeHelper
from landscape.client.broker.server import BrokerServer


class MessageExchangeTest(LandscapeTest):

    helpers = [ExchangeHelper]

    def setUp(self):
        super(MessageExchangeTest, self).setUp()
        self.mstore.add_schema(Message("empty", {}))
        self.mstore.add_schema(Message("data", {"data": Int()}))
        self.mstore.add_schema(Message("holdme", {}))
        self.identity.secure_id = 'needs-to-be-set-for-tests-to-pass'

    def wait_for_exchange(self, urgent=False, factor=1, delta=0):
        if urgent:
            seconds = self.config.urgent_exchange_interval
        else:
            seconds = self.config.exchange_interval
        self.reactor.advance(seconds * factor + delta)

    def test_resynchronize_causes_urgent_exchange(self):
        """
        A 'resynchronize-clients' messages causes an urgent exchange
        to be scheduled.
        """
        self.assertFalse(self.exchanger.is_urgent())
        self.reactor.fire("resynchronize-clients")
        self.assertTrue(self.exchanger.is_urgent())

    def test_that_resynchronize_drops_session_ids(self):
        """
        When a resynchronisation event occurs with global scope all existing
        session IDs are expired, so any new messages being sent with those IDs
        will be discarded.
        """
        broker = BrokerServer(self.config, self.reactor,
                              self.exchanger, None,
                              self.mstore, None)

        disk_session_id = self.mstore.get_session_id(scope="disk")
        package_session_id = self.mstore.get_session_id(scope="package")
        self.mstore.set_accepted_types(["empty"])
        global_scope = []
        self.reactor.fire("resynchronize-clients", global_scope)
        broker.send_message({"type": "empty"}, disk_session_id)
        broker.send_message({"type": "empty"}, package_session_id)
        self.exchanger.exchange()
        messages = self.transport.payloads[0]["messages"]
        self.assertMessages(messages, [])

    def test_that_resynchronize_drops_scoped_session_ids_only(self):
        """
        When a resynchronisation event occurs with a scope existing session IDs
        for that scope are expired, all other session IDs are unaffected.
        """
        broker = BrokerServer(self.config, self.reactor,
                              self.exchanger, None,
                              self.mstore, None)

        disk_session_id = self.mstore.get_session_id(scope="disk")
        package_session_id = self.mstore.get_session_id(scope="package")
        self.mstore.set_accepted_types(["empty"])
        disk_scope = ["disk"]
        self.reactor.fire("resynchronize-clients", disk_scope)
        broker.send_message({"type": "empty"}, disk_session_id)
        broker.send_message({"type": "empty"}, package_session_id)
        self.exchanger.exchange()
        messages = self.transport.payloads[0]["messages"]
        self.assertMessages(messages, [{"type": "empty"}])

    def test_that_resynchronize_clears_message_blackhole(self):
        """
        When a resynchronisation event occurs the block on new messages
        being stored is lifted.
        """
        self.reactor.fire("resynchronize-clients", [])
        persist = Persist(filename=self.persist_filename)
        self.assertFalse(persist.get("blackhole-messages"))

    def test_send(self):
        """
        The send method should cause a message to show up in the next exchange.
        """
        self.mstore.set_accepted_types(["empty"])
        self.exchanger.send({"type": "empty"})
        self.exchanger.exchange()
        self.assertEqual(len(self.transport.payloads), 1)
        messages = self.transport.payloads[0]["messages"]
        self.assertEqual(messages, [{"type": "empty",
                                     "timestamp": 0,
                                     "api": b"3.2"}])

    def test_send_urgent(self):
        """
        Sending a message with the urgent flag should schedule an
        urgent exchange.
        """
        self.mstore.set_accepted_types(["empty"])
        self.exchanger.send({"type": "empty"}, urgent=True)
        self.wait_for_exchange(urgent=True)
        self.assertEqual(len(self.transport.payloads), 1)
        self.assertMessages(self.transport.payloads[0]["messages"],
                            [{"type": "empty"}])

    def test_send_urgent_wont_reschedule(self):
        """
        If an urgent exchange is already scheduled, adding another
        urgent message shouldn't reschedule the exchange forward.
        """
        self.mstore.set_accepted_types(["empty"])
        self.exchanger.send({"type": "empty"}, urgent=True)
        self.wait_for_exchange(urgent=True, factor=0.5)
        self.exchanger.send({"type": "empty"}, urgent=True)
        self.wait_for_exchange(urgent=True, factor=0.5)
        self.assertEqual(len(self.transport.payloads), 1)
        self.assertMessages(self.transport.payloads[0]["messages"],
                            [{"type": "empty"}, {"type": "empty"}])

    def test_send_returns_message_id(self):
        """
        The send method should return the message id, as returned by add().
        """
        self.mstore.set_accepted_types(["empty"])
        message_id = self.exchanger.send({"type": "empty"})
        self.assertTrue(self.mstore.is_pending(message_id))
        self.mstore.add_pending_offset(1)
        self.assertFalse(self.mstore.is_pending(message_id))

    def test_wb_include_accepted_types(self):
        """
        Every payload from the client needs to specify an ID which
        represents the types that we think the server wants.
        """
        payload = self.exchanger._make_payload()
        self.assertIn("accepted-types", payload)
        self.assertEqual(payload["accepted-types"], md5(b"").digest())

    def test_handle_message_sets_accepted_types(self):
        """
        An incoming "accepted-types" message should set the accepted
        types.
        """
        self.exchanger.handle_message(
            {"type": "accepted-types", "types": ["foo"]})
        self.assertEqual(self.mstore.get_accepted_types(), ["foo"])

    def test_message_type_acceptance_changed_event(self):
        stash = []

        def callback(type, accepted):
            stash.append((type, accepted))
        self.reactor.call_on("message-type-acceptance-changed", callback)
        self.exchanger.handle_message(
            {"type": "accepted-types", "types": ["a", "b"]})
        self.exchanger.handle_message(
            {"type": "accepted-types", "types": ["b", "c"]})
        self.assertCountEqual(stash, [("a", True), ("b", True),
                                      ("a", False), ("c", True)])

    def test_wb_accepted_types_roundtrip(self):
        """
        Telling the client to set the accepted types with a message
        should affect its future payloads.
        """
        self.exchanger.handle_message(
            {"type": "accepted-types", "types": ["ack", "bar"]})
        payload = self.exchanger._make_payload()
        self.assertIn("accepted-types", payload)
        self.assertEqual(payload["accepted-types"],
                         md5(b"ack;bar").digest())

    def test_accepted_types_causes_urgent_if_held_messages_exist(self):
        """
        If an accepted-types message makes available a type for which we
        have a held message, an urgent exchange should occur.
        """
        self.exchanger.send({"type": "holdme"})
        self.assertEqual(self.mstore.get_pending_messages(), [])
        self.exchanger.handle_message(
            {"type": "accepted-types", "types": ["holdme"]})
        self.wait_for_exchange(urgent=True)
        self.assertEqual(len(self.transport.payloads), 1)
        self.assertMessages(self.transport.payloads[0]["messages"],
                            [{"type": "holdme"}])

    def test_accepted_types_no_urgent_without_held(self):
        """
        If an accepted-types message does *not* "unhold" any exist messages,
        then no urgent exchange should occur.
        """
        self.exchanger.send({"type": "holdme"})
        self.assertEqual(self.transport.payloads, [])
        self.reactor.fire("message",
                          {"type": "accepted-types", "types": ["irrelevant"]})
        self.assertEqual(len(self.transport.payloads), 0)

    def test_sequence_is_committed_immediately(self):
        """
        The MessageStore should be committed by the MessageExchange as soon as
        possible after setting the pending offset and sequence.
        """
        self.mstore.set_accepted_types(["empty"])

        # We'll check that the message store has been saved by the time a
        # message handler gets called.
        self.transport.responses.append([{"type": "inbound"}])
        self.exchanger.send({"type": "empty"})

        handled = []

        def handler(message):
            persist = Persist(filename=self.persist_filename)
            store = MessageStore(persist, self.config.message_store_path)
            self.assertEqual(store.get_pending_offset(), 1)
            self.assertEqual(store.get_sequence(), 1)
            handled.append(True)

        self.exchanger.register_message("inbound", handler)
        self.exchanger.exchange()
        self.assertEqual(handled, [True], self.logfile.getvalue())

    def test_messages_from_server_commit(self):
        """
        The Exchange should commit the message store after processing each
        message.
        """
        self.transport.responses.append([{"type": "inbound"}] * 3)
        handled = []
        self.message_counter = 0

        def handler(message):
            Persist(filename=self.persist_filename)
            store = MessageStore(self.persist, self.config.message_store_path)
            self.assertEqual(store.get_server_sequence(),
                             self.message_counter)
            self.message_counter += 1
            handled.append(True)

        self.exchanger.register_message("inbound", handler)
        self.exchanger.exchange()
        self.assertEqual(handled, [True] * 3, self.logfile.getvalue())

    def test_messages_from_server_causing_urgent_exchanges(self):
        """
        If a message from the server causes an urgent message to be
        queued, an urgent exchange should happen again after the
        running exchange.
        """
        self.transport.responses.append([{"type": "foobar"}])
        self.mstore.set_accepted_types(["empty"])

        def handler(message):
            self.exchanger.send({"type": "empty"}, urgent=True)

        self.exchanger.register_message("foobar", handler)

        self.exchanger.exchange()

        self.assertEqual(len(self.transport.payloads), 1)

        self.wait_for_exchange(urgent=True)

        self.assertEqual(len(self.transport.payloads), 2)
        self.assertMessages(self.transport.payloads[1]["messages"],
                            [{"type": "empty"}])

    def test_server_expects_older_messages(self):
        """
        If the server expects an old message, the exchanger should be
        marked as urgent.
        """
        self.mstore.set_accepted_types(["data"])
        self.mstore.add({"type": "data", "data": 0})
        self.mstore.add({"type": "data", "data": 1})
        self.exchanger.exchange()
        self.assertEqual(self.mstore.get_sequence(), 2)

        self.mstore.add({"type": "data", "data": 2})
        self.mstore.add({"type": "data", "data": 3})

        # next one, server will respond with 1!
        def desynched_send_data(*args, **kwargs):
            self.transport.next_expected_sequence = 1
            return {"next-expected-sequence": 1}

        self.transport.exchange = desynched_send_data
        self.exchanger.exchange()
        self.assertEqual(self.mstore.get_sequence(), 1)
        del self.transport.exchange

        exchanged = []

        def exchange_callback():
            exchanged.append(True)

        self.reactor.call_on("exchange-done", exchange_callback)
        self.wait_for_exchange(urgent=True)
        self.assertEqual(exchanged, [True])

        payload = self.transport.payloads[-1]
        self.assertMessages(payload["messages"],
                            [{"type": "data", "data": 1},
                             {"type": "data", "data": 2},
                             {"type": "data", "data": 3}])
        self.assertEqual(payload["sequence"], 1)
        self.assertEqual(payload["next-expected-sequence"], 0)

    def test_start_with_urgent_exchange(self):
        """
        Immediately after registration, an urgent exchange should be scheduled.
        """
        transport = FakeTransport()
        exchanger = MessageExchange(self.reactor, self.mstore, transport,
                                    self.identity, self.exchange_store,
                                    self.config)
        exchanger.start()
        self.wait_for_exchange(urgent=True)
        self.assertEqual(len(transport.payloads), 1)

    def test_reschedule_after_exchange(self):
        """
        Under normal operation, after an exchange has finished another
        exchange should be scheduled for after the normal delay.
        """
        self.exchanger.schedule_exchange(urgent=True)

        self.wait_for_exchange(urgent=True)
        self.assertEqual(len(self.transport.payloads), 1)

        self.wait_for_exchange()
        self.assertEqual(len(self.transport.payloads), 2)

        self.wait_for_exchange()
        self.assertEqual(len(self.transport.payloads), 3)

    def test_leave_urgent_exchange_mode_after_exchange(self):
        """
        After an urgent exchange, assuming no messages are left to be
        exchanged, urgent exchange should not remain scheduled.
        """
        self.mstore.set_accepted_types(["empty"])
        self.exchanger.send({"type": "empty"}, urgent=True)
        self.wait_for_exchange(urgent=True)
        self.assertEqual(len(self.transport.payloads), 1)
        self.wait_for_exchange(urgent=True)
        self.assertEqual(len(self.transport.payloads), 1)  # no change

    def test_successful_exchange_records_success(self):
        """
        When a successful exchange occurs, that success is recorded in the
        message store.
        """
        mock_record_success = mock.Mock()
        self.mstore.record_success = mock_record_success

        exchanger = MessageExchange(
            self.reactor, self.mstore, self.transport,
            self.identity, self.exchange_store, self.config)
        exchanger.exchange()

        mock_record_success.assert_called_with(mock.ANY)
        self.assertTrue(
            type(mock_record_success.call_args[0][0]) is int)

    def test_ancient_causes_resynchronize(self):
        """
        If the server asks for messages that we no longer have, the message
        exchange plugin should send a message to the server indicating that a
        resynchronization is occuring and then fire a "resynchronize-clients"
        reactor message, so that plugins can generate new data -- if the server
        got out of synch with the client, then we're best off synchronizing
        everything back to it.
        """
        self.mstore.set_accepted_types(["empty", "data", "resynchronize"])
        # Do three generations of messages, so we "lose" the 0th message
        for i in range(3):
            self.mstore.add({"type": "empty"})
            self.exchanger.exchange()
        # the server loses some data
        self.transport.next_expected_sequence = 0

        def resynchronize(scopes=None):
            # We'll add a message to the message store here, since this is what
            # is commonly done in a resynchronize callback. This message added
            # should come AFTER the "resynchronize" message that is generated
            # by the exchange code itself.
            self.mstore.add({"type": "data", "data": 999})
        self.reactor.call_on("resynchronize-clients", resynchronize)

        # This exchange call will notice the server is asking for an old
        # message and fire the event:
        self.exchanger.exchange()
        self.assertMessages(self.mstore.get_pending_messages(),
                            [{"type": "empty"},
                             {"type": "resynchronize"},
                             {"type": "data", "data": 999}])

    def test_resynchronize_msg_causes_resynchronize_response_then_event(self):
        """
        If a message of type 'resynchronize' is received from the
        server, the exchanger should *first* send a 'resynchronize'
        message back to the server and *then* fire a
        'resynchronize-clients' event.
        """
        self.mstore.set_accepted_types(["empty", "resynchronize"])

        def resynchronized(scopes=None):
            self.mstore.add({"type": "empty"})
        self.reactor.call_on("resynchronize-clients", resynchronized)

        self.transport.responses.append([{"type": "resynchronize",
                                          "operation-id": 123}])
        self.exchanger.exchange()
        self.assertMessages(self.mstore.get_pending_messages(),
                            [{"type": "resynchronize",
                              "operation-id": 123},
                             {"type": "empty"}])

    def test_scopes_are_copied_from_incoming_resynchronize_messages(self):
        """
        If an incoming message of type 'reysnchronize' contains a 'scopes' key,
        then it's value is copied into the "resynchronize-clients" event.
        """
        fired_scopes = []
        self.mstore.set_accepted_types(["reysnchronize"])

        def resynchronized(scopes=None):
            fired_scopes.extend(scopes)

        self.reactor.call_on("resynchronize-clients", resynchronized)

        self.transport.responses.append([{"type": "resynchronize",
                                          "operation-id": 123,
                                          "scopes": ["disk", "users"]}])
        self.exchanger.exchange()
        self.assertEqual(["disk", "users"], fired_scopes)

    def test_no_urgency_when_server_expects_current_message(self):
        """
        When the message the server expects is the same as the first
        pending message sequence, the client should not go into urgent
        exchange mode.

        This means the server handler is likely blowing up and the client and
        the server are in a busy loop constantly asking for the same message,
        breaking, setting urgent exchange mode, sending the same message and
        then breaking in a fast loop.  In this case, urgent exchange mode
        should not be set. (bug #138135)
        """
        # We set the server sequence to some non-0 value to ensure that the
        # server and client sequences aren't the same to ensure the code is
        # looking at the correct sequence number. :(
        self.mstore.set_server_sequence(3300)
        self.mstore.set_accepted_types(["data"])
        self.mstore.add({"type": "data", "data": 0})

        def desynched_send_data(*args, **kwargs):
            self.transport.next_expected_sequence = 0
            return {"next-expected-sequence": 0}

        self.transport.exchange = desynched_send_data
        self.exchanger.exchange()

        self.assertEqual(self.mstore.get_sequence(), 0)
        del self.transport.exchange

        exchanged = []

        def exchange_callback():
            exchanged.append(True)

        self.reactor.call_on("exchange-done", exchange_callback)
        self.wait_for_exchange(urgent=True)
        self.assertEqual(exchanged, [])
        self.wait_for_exchange()
        self.assertEqual(exchanged, [True])

    def test_old_sequence_id_does_not_cause_resynchronize(self):
        resynchronized = []
        self.reactor.call_on("resynchronize",
                             lambda: resynchronized.append(True))

        self.mstore.set_accepted_types(["empty"])
        self.mstore.add({"type": "empty"})
        self.exchanger.exchange()
        # the server loses some data, but not too much
        self.transport.next_expected_sequence = 0

        self.exchanger.exchange()
        self.assertEqual(resynchronized, [])

    def test_per_api_payloads(self):
        """
        When sending messages to the server, the exchanger should split
        messages with different APIs in different payloads, and deliver
        them to the right API on the server.
        """
        types = ["a", "b", "c", "d", "e", "f"]
        self.mstore.set_accepted_types(types)
        for t in types:
            self.mstore.add_schema(Message(t, {}))

        self.exchanger.exchange()

        # No messages queued yet.  Server API should default to
        # the client API.
        payload = self.transport.payloads[-1]
        self.assertMessages(payload["messages"], [])
        self.assertEqual(payload.get("client-api"), CLIENT_API)
        self.assertEqual(payload.get("server-api"), b"3.2")
        self.assertEqual(self.transport.message_api, b"3.2")

        self.mstore.add({"type": "a", "api": b"1.0"})
        self.mstore.add({"type": "b", "api": b"1.0"})
        self.mstore.add({"type": "c", "api": b"1.1"})
        self.mstore.add({"type": "d", "api": b"1.1"})

        self.exchanger.exchange()

        payload = self.transport.payloads[-1]
        self.assertMessages(payload["messages"],
                            [{"type": "a", "api": b"1.0"},
                             {"type": "b", "api": b"1.0"}])
        self.assertEqual(payload.get("client-api"), CLIENT_API)
        self.assertEqual(payload.get("server-api"), b"1.0")
        self.assertEqual(self.transport.message_api, b"1.0")

        self.exchanger.exchange()

        payload = self.transport.payloads[-1]
        self.assertMessages(payload["messages"],
                            [{"type": "c", "api": b"1.1"},
                             {"type": "d", "api": b"1.1"}])
        self.assertEqual(payload.get("client-api"), CLIENT_API)
        self.assertEqual(payload.get("server-api"), b"1.1")
        self.assertEqual(self.transport.message_api, b"1.1")

    def test_exchange_token(self):
        """
        When sending messages to the server, the exchanger provides the
        token that the server itself gave it during the former exchange.
        """
        self.exchanger.exchange()
        self.assertIs(None, self.transport.exchange_token)
        exchange_token = self.mstore.get_exchange_token()
        self.assertIsNot(None, exchange_token)
        self.exchanger.exchange()
        self.assertEqual(exchange_token, self.transport.exchange_token)

    def test_reset_exchange_token_on_failure(self):
        """
        If an exchange fails we set the value of the next exchange token to
        C{None}, so we can authenticate ourselves even if we couldn't receive
        a valid token.
        """
        self.mstore.set_exchange_token("abcd-efgh")
        self.mstore.commit()
        self.transport.exchange = lambda *args, **kwargs: None
        self.exchanger.exchange()
        # Check that the change was persisted
        persist = Persist(filename=self.persist_filename)
        store = MessageStore(persist, self.config.message_store_path)
        self.assertIs(None, store.get_exchange_token())

    def test_include_total_messages_none(self):
        """
        The payload includes the total number of messages that the client has
        pending for the server.
        """
        self.mstore.set_accepted_types(["empty"])
        self.exchanger.exchange()
        self.assertEqual(self.transport.payloads[0]["total-messages"], 0)

    def test_include_total_messages_some(self):
        """
        If there are no more messages than those that are sent in the exchange,
        the total-messages is equivalent to the number of messages sent.
        """
        self.mstore.set_accepted_types(["empty"])
        self.mstore.add({"type": "empty"})
        self.exchanger.exchange()
        self.assertEqual(self.transport.payloads[0]["total-messages"], 1)

    def test_include_total_messages_more(self):
        """
        If there are more messages than those that are sent in the exchange,
        the total-messages is equivalent to the total number of messages
        pending.
        """
        exchanger = MessageExchange(self.reactor, self.mstore, self.transport,
                                    self.identity, self.exchange_store,
                                    self.config, max_messages=1)
        self.mstore.set_accepted_types(["empty"])
        self.mstore.add({"type": "empty"})
        self.mstore.add({"type": "empty"})
        exchanger.exchange()
        self.assertEqual(self.transport.payloads[0]["total-messages"], 2)

    def test_impending_exchange(self):
        """
        A reactor event is emitted shortly (10 seconds) before an exchange
        occurs.
        """
        self.exchanger.schedule_exchange()
        events = []
        self.reactor.call_on("impending-exchange", lambda: events.append(True))
        self.wait_for_exchange(delta=-11)
        self.assertEqual(events, [])
        self.reactor.advance(1)
        self.assertEqual(events, [True])

    def test_impending_exchange_on_urgent(self):
        """
        The C{impending-exchange} event is fired 10 seconds before urgent
        exchanges.
        """
        # We create our own MessageExchange because the one set up by the text
        # fixture has an urgent exchange interval of 10 seconds, which makes
        # testing this awkward.
        self.config.urgent_exchange_interval = 20
        exchanger = MessageExchange(self.reactor, self.mstore, self.transport,
                                    self.identity, self.exchange_store,
                                    self.config)
        exchanger.schedule_exchange(urgent=True)
        events = []
        self.reactor.call_on("impending-exchange", lambda: events.append(True))
        self.reactor.advance(9)
        self.assertEqual(events, [])
        self.reactor.advance(1)
        self.assertEqual(events, [True])

    def test_impending_exchange_gets_reschudeled_with_urgent_reschedule(self):
        """
        When an urgent exchange is scheduled after a regular exchange was
        scheduled but before it executed, the old C{impending-exchange} event
        should be cancelled and a new one should be scheduled for 10 seconds
        before the new urgent exchange.
        """
        self.config.exchange_interval = 60 * 60
        self.config.urgent_exchange_interval = 20
        exchanger = MessageExchange(self.reactor, self.mstore, self.transport,
                                    self.identity, self.exchange_store,
                                    self.config)
        events = []
        self.reactor.call_on("impending-exchange", lambda: events.append(True))
        # This call will:
        # * schedule the exchange for an hour from now
        # * schedule impending-exchange to be fired an hour - 10 seconds from
        #   now
        exchanger.schedule_exchange()
        # And this call will:
        # * hopefully cancel those previous calls
        # * schedule an exchange for 20 seconds from now
        # * schedule impending-exchange to be fired in 10 seconds
        exchanger.schedule_exchange(urgent=True)
        self.reactor.advance(10)
        self.assertEqual(events, [True])
        self.reactor.advance(10)
        self.assertEqual(len(self.transport.payloads), 1)
        # Now the urgent exchange should be fired, which should automatically
        # schedule a regular exchange.
        # Let's make sure that that *original* impending-exchange event has
        # been cancelled:
        TIME_UNTIL_EXCHANGE = 60 * 60
        TIME_UNTIL_NOTIFY = 10
        TIME_ADVANCED = 20  # time that we've already advanced
        self.reactor.advance(TIME_UNTIL_EXCHANGE -
                             (TIME_UNTIL_NOTIFY + TIME_ADVANCED))
        self.assertEqual(events, [True])
        # Ok, so no new events means that the original call was
        # cancelled. great.
        # Just a bit more sanity checking:
        self.reactor.advance(20)
        self.assertEqual(events, [True, True])
        self.reactor.advance(10)
        self.assertEqual(len(self.transport.payloads), 2)

    def test_pre_exchange_event(self):
        reactor_mock = mock.Mock()
        self.exchanger._reactor = reactor_mock
        self.exchanger.exchange()
        reactor_mock.fire.assert_called_once_with("pre-exchange")

    def test_schedule_exchange(self):
        self.exchanger.schedule_exchange()
        self.wait_for_exchange(urgent=True)
        self.assertFalse(self.transport.payloads)
        self.wait_for_exchange()
        self.assertTrue(self.transport.payloads)

    def test_schedule_urgent_exchange(self):
        self.exchanger.schedule_exchange(urgent=True)
        self.wait_for_exchange(urgent=True)
        self.assertTrue(self.transport.payloads)

    def test_exchange_failed_fires_correctly(self):
        """
        Ensure that the exchange-failed event is fired if the
        exchanger raises an exception.
        """

        def failed_send_data(*args, **kwargs):
            return None

        self.transport.exchange = failed_send_data

        exchanged = []

        def exchange_failed_callback():
            exchanged.append(True)

        self.reactor.call_on("exchange-failed", exchange_failed_callback)
        self.exchanger.exchange()
        self.assertEqual(exchanged, [True])

    def test_stop(self):
        self.exchanger.schedule_exchange()
        self.exchanger.stop()
        self.wait_for_exchange()
        self.assertFalse(self.transport.payloads)

    def test_stop_twice_doesnt_break(self):
        self.exchanger.schedule_exchange()
        self.exchanger.stop()
        self.exchanger.stop()
        self.wait_for_exchange()
        self.assertFalse(self.transport.payloads)

    def test_set_intervals(self):
        """
        When a C{set-intervals} message is received, the runtime attributes of
        the L{MessageExchange} are changed, the configuration values as well,
        and the configuration is written to disk to be persisted.
        """
        server_message = [{"type": "set-intervals",
                           "urgent-exchange": 1234, "exchange": 5678}]
        self.transport.responses.append(server_message)

        self.exchanger.exchange()

        self.assertEqual(self.config.exchange_interval, 5678)
        self.assertEqual(self.config.urgent_exchange_interval, 1234)

        new_config = BrokerConfiguration()
        new_config.load_configuration_file(self.config_filename)
        self.assertEqual(new_config.exchange_interval, 5678)
        self.assertEqual(new_config.urgent_exchange_interval, 1234)

    def test_set_intervals_with_urgent_exchange_only(self):
        server_message = [{"type": "set-intervals", "urgent-exchange": 1234}]
        self.transport.responses.append(server_message)

        self.exchanger.exchange()

        # Let's make sure it works.
        self.exchanger.schedule_exchange(urgent=True)
        self.reactor.advance(1233)
        self.assertEqual(len(self.transport.payloads), 1)
        self.reactor.advance(1)
        self.assertEqual(len(self.transport.payloads), 2)

    def test_set_intervals_with_exchange_only(self):
        server_message = [{"type": "set-intervals", "exchange": 5678}]
        self.transport.responses.append(server_message)

        self.exchanger.exchange()

        # Let's make sure it works.
        self.reactor.advance(5677)
        self.assertEqual(len(self.transport.payloads), 1)
        self.reactor.advance(1)
        self.assertEqual(len(self.transport.payloads), 2)

    def test_register_message(self):
        """
        The exchanger expsoses a mechanism for subscribing to messages
        of a particular type.
        """
        messages = []
        self.exchanger.register_message("type-A", messages.append)
        msg = {"type": "type-A", "whatever": 5678}
        server_message = [msg]
        self.transport.responses.append(server_message)
        self.exchanger.exchange()
        self.assertEqual(messages, [msg])

    def test_register_multiple_message_handlers(self):
        """
        Registering multiple handlers for the same type will cause
        each handler to be called in the order they were registered.
        """
        messages = []

        def handler1(message):
            messages.append(("one", message))

        def handler2(message):
            messages.append(("two", message))

        self.exchanger.register_message("type-A", handler1)
        self.exchanger.register_message("type-A", handler2)

        msg = {"type": "type-A", "whatever": 5678}
        server_message = [msg]
        self.transport.responses.append(server_message)
        self.exchanger.exchange()
        self.assertEqual(messages, [("one", msg), ("two", msg)])

    def test_server_api_with_old_server(self):
        """
        If a server doesn't indicate which is its highest server-api, it
        will be 3.2 for sure.
        """
        self.transport.extra.pop("server-api", None)
        self.exchanger.exchange()
        self.assertEqual(b"3.2", self.mstore.get_server_api())

    def test_wb_client_with_older_api_and_server_with_newer(self):
        """
        If a server notifies us that it case use a very new API, but we
        don't know how to speak it, we keep using ours.
        """
        self.exchanger._api = b"3.3"
        self.transport.extra["server-api"] = b"3.4"
        self.exchanger.exchange()
        self.assertEqual(b"3.3", self.mstore.get_server_api())

    def test_wb_client_with_newer_api_and_server_with_older(self):
        """
        If a server notifies us that it can use an API which is older
        than the one we support, we'll just use the server API.
        """
        self.exchanger._api = b"3.4"
        self.transport.extra["server-api"] = b"3.3"
        self.exchanger.exchange()
        self.assertEqual(b"3.3", self.mstore.get_server_api())

    def test_server_uuid_is_stored_on_message_store(self):
        self.transport.extra["server-uuid"] = b"first-uuid"
        self.exchanger.exchange()
        self.assertEqual(self.mstore.get_server_uuid(), "first-uuid")
        self.transport.extra["server-uuid"] = b"second-uuid"
        self.exchanger.exchange()
        self.assertEqual(self.mstore.get_server_uuid(), "second-uuid")

    def test_server_uuid_change_cause_event(self):
        called = []

        def server_uuid_changed(old_uuid, new_uuid):
            called.append((old_uuid, new_uuid))
        self.reactor.call_on("server-uuid-changed", server_uuid_changed)

        # Set it for the first time, and it should emit the event
        # letting the system know about the change.
        self.transport.extra["server-uuid"] = "first-uuid"
        self.exchanger.exchange()
        self.assertEqual(len(called), 1)
        self.assertEqual(called[-1], (None, "first-uuid"))

        # Using the same one again, nothing should happen:
        self.transport.extra["server-uuid"] = "first-uuid"
        self.exchanger.exchange()
        self.assertEqual(len(called), 1)

        # Changing it, we should get an event again:
        self.transport.extra["server-uuid"] = "second-uuid"
        self.exchanger.exchange()
        self.assertEqual(len(called), 2)
        self.assertEqual(called[-1], ("first-uuid", "second-uuid"))

        # And then, it shouldn't emit it once more, since it continues
        # to be the same.
        self.transport.extra["server-uuid"] = "second-uuid"
        self.exchanger.exchange()
        self.assertEqual(len(called), 2)

    def test_server_uuid_event_not_emitted_with_matching_stored_uuid(self):
        """
        If the UUID in the message store is the same as the current UUID,
        the event is not emitted.
        """
        called = []

        def server_uuid_changed(old_uuid, new_uuid):
            called.append((old_uuid, new_uuid))
        self.reactor.call_on("server-uuid-changed", server_uuid_changed)

        self.mstore.set_server_uuid("the-uuid")
        self.transport.extra["server-uuid"] = "the-uuid"
        self.exchanger.exchange()
        self.assertEqual(called, [])

    def test_server_uuid_change_is_logged(self):
        self.transport.extra["server-uuid"] = "the-uuid"
        self.exchanger.exchange()

        self.assertIn("INFO: Server UUID changed (old=None, new=the-uuid).",
                      self.logfile.getvalue())

        # An exchange with the same UUID shouldn't be logged.
        self.logfile.truncate(0)
        self.transport.extra["server-uuid"] = "the-uuid"
        self.exchanger.exchange()

        self.assertNotIn("INFO: Server UUID changed", self.logfile.getvalue())

    def test_return_messages_have_their_context_stored(self):
        """
        Incoming messages with an 'operation-id' key will have the secure id
        stored in the L{ExchangeStore}.
        """
        messages = []
        self.exchanger.register_message("type-R", messages.append)
        msg = {"type": "type-R", "whatever": 5678, "operation-id": 123456}
        server_message = [msg]
        self.transport.responses.append(server_message)
        self.exchanger.exchange()
        [message] = messages
        self.assertIsNot(
            None,
            self.exchange_store.get_message_context(message['operation-id']))
        message_context = self.exchange_store.get_message_context(
            message['operation-id'])
        self.assertEqual(message_context.operation_id, 123456)
        self.assertEqual(message_context.message_type, "type-R")

    def test_one_way_messages_do_not_have_their_context_stored(self):
        """
        Incoming messages without an 'operation-id' key will *not* have the
        secure id stored in the L{ExchangeStore}.
        """
        ids_before = self.exchange_store.all_operation_ids()

        msg = {"type": "type-R", "whatever": 5678}
        server_message = [msg]
        self.transport.responses.append(server_message)
        self.exchanger.exchange()

        ids_after = self.exchange_store.all_operation_ids()
        self.assertEqual(ids_before, ids_after)

    def test_obsolete_response_messages_are_discarded(self):
        """
        An obsolete response message will be discarded as opposed to being
        sent to the server.

        A response message is considered obsolete if the secure ID changed
        since the request message was received.
        """
        # Receive the message below from the server.
        msg = {"type": "type-R", "whatever": 5678, "operation-id": 234567}
        server_message = [msg]
        self.transport.responses.append(server_message)
        self.exchanger.exchange()

        # Change the secure ID so that the response message gets discarded.
        self.identity.secure_id = 'brand-new'
        ids_before = self.exchange_store.all_operation_ids()

        self.mstore.set_accepted_types(["resynchronize"])
        message_id = self.exchanger.send(
            {"type": "resynchronize", "operation-id": 234567})
        self.exchanger.exchange()
        self.assertEqual(2, len(self.transport.payloads))
        messages = self.transport.payloads[1]["messages"]
        self.assertEqual([], messages)
        self.assertIs(None, message_id)
        expected_log_entry = (
            "Response message with operation-id 234567 was discarded because "
            "the client's secure ID has changed in the meantime")
        self.assertIn(expected_log_entry, self.logfile.getvalue())

        # The MessageContext was removed after utilisation.
        ids_after = self.exchange_store.all_operation_ids()
        self.assertEqual(len(ids_after), len(ids_before) - 1)
        self.assertNotIn('234567', ids_after)

    def test_error_exchanging_causes_failed_exchange(self):
        """
        If a traceback occurs whilst exchanging, the 'exchange-failed'
        event should be fired.
        """
        events = []

        def failed_exchange(ssl_error=False):
            events.append(None)

        self.reactor.call_on("exchange-failed", failed_exchange)
        self.transport.responses.append(RuntimeError("Failed to communicate."))
        self.exchanger.exchange()
        self.assertEqual([None], events)

    def test_SSL_error_exchanging_causes_failed_exchange(self):
        """
        If an SSL error occurs when exchanging, the 'exchange-failed'
        event should be fired with the optional "ssl_error" flag set to True.
        """
        self.log_helper.ignore_errors("Message exchange failed: Failed to "
                                      "communicate.")
        events = []

        def failed_exchange(ssl_error):
            if ssl_error:
                events.append(None)

        self.reactor.call_on("exchange-failed", failed_exchange)
        self.transport.responses.append(PyCurlError(60,
                                                    "Failed to communicate."))
        self.exchanger.exchange()
        self.assertEqual([None], events)

    def test_pycurl_error_exchanging_causes_failed_exchange(self):
        """
        If an undefined PyCurl error is raised during exchange, (not an SSL
        error), the 'exchange-failed' event should be fired with the ssl_error
        flag set to False.
        """
        events = []

        def failed_exchange(ssl_error):
            if not ssl_error:
                events.append(None)

        self.reactor.call_on("exchange-failed", failed_exchange)
        self.transport.responses.append(PyCurlError(10,  # Not 60
                                                    "Failed to communicate."))
        self.exchanger.exchange()
        self.assertEqual([None], events)

    def test_wb_error_exchanging_records_failure_in_message_store(self):
        """
        If a traceback occurs whilst exchanging, the failure is recorded
        in the message store.
        """
        self.reactor.advance(123)
        self.transport.responses.append(RuntimeError("Failed to communicate."))
        self.exchanger.exchange()
        self.assertEqual(123, self.mstore._persist.get("first-failure-time"))

    def test_error_exchanging_marks_exchange_complete(self):
        """
        If a traceback occurs whilst exchanging, the exchange is still
        marked as complete.
        """
        events = []

        def exchange_done():
            events.append(None)

        self.reactor.call_on("exchange-done", exchange_done)
        self.transport.responses.append(RuntimeError("Failed to communicate."))
        self.exchanger.exchange()
        self.assertEqual([None], events)

    def test_error_exchanging_logs_failure(self):
        """
        If a traceback occurs whilst exchanging, the failure is logged.
        """
        self.transport.responses.append(RuntimeError("Failed to communicate."))
        self.exchanger.exchange()
        self.assertIn("Message exchange failed.", self.logfile.getvalue())

    def test_exchange_error_with_404_downgrades_server_api(self):
        """
        If we get a 404, we try to donwgrade our server API version.
        """
        self.mstore.set_server_api(b"3.3")
        self.transport.responses.append(HTTPCodeError(404, ""))
        self.exchanger.exchange()
        self.assertEqual(b"3.2", self.mstore.get_server_api())


class AcceptedTypesMessageExchangeTest(LandscapeTest):

    helpers = [ExchangeHelper]

    def setUp(self):
        super(AcceptedTypesMessageExchangeTest, self).setUp()
        self.pinger = Pinger(self.reactor, self.identity, self.exchanger,
                             self.config)
        # The __init__ method of RegistrationHandler registers a few default
        # message types that we want to catch as well
        self.handler = RegistrationHandler(
            self.config, self.identity, self.reactor, self.exchanger,
            self.pinger, self.mstore)

    def test_register_accepted_message_type(self):
        self.exchanger.register_client_accepted_message_type("type-B")
        self.exchanger.register_client_accepted_message_type("type-A")
        self.exchanger.register_client_accepted_message_type("type-C")
        self.exchanger.register_client_accepted_message_type("type-A")
        types = self.exchanger.get_client_accepted_message_types()
        self.assertEqual(types,
                         sorted(["type-A", "type-B", "type-C"] +
                                DEFAULT_ACCEPTED_TYPES))

    def test_exchange_sends_message_type_when_no_hash(self):
        self.exchanger.register_client_accepted_message_type("type-A")
        self.exchanger.register_client_accepted_message_type("type-B")
        self.exchanger.exchange()
        self.assertEqual(
            self.transport.payloads[0]["client-accepted-types"],
            sorted(["type-A", "type-B"] + DEFAULT_ACCEPTED_TYPES))

    def test_exchange_does_not_send_message_types_when_hash_matches(self):
        self.exchanger.register_client_accepted_message_type("type-A")
        self.exchanger.register_client_accepted_message_type("type-B")
        types = sorted(["type-A", "type-B"] + DEFAULT_ACCEPTED_TYPES)
        accepted_types_digest = md5(";".join(types).encode("ascii")).digest()
        self.transport.extra["client-accepted-types-hash"] = \
            accepted_types_digest
        self.exchanger.exchange()
        self.exchanger.exchange()
        self.assertNotIn("client-accepted-types", self.transport.payloads[1])

    def test_exchange_continues_sending_message_types_on_no_hash(self):
        """
        If the server does not respond with a hash of client accepted message
        types, the client will continue to send the accepted types.
        """
        self.exchanger.register_client_accepted_message_type("type-A")
        self.exchanger.register_client_accepted_message_type("type-B")
        self.exchanger.exchange()
        self.exchanger.exchange()
        self.assertEqual(
            self.transport.payloads[1]["client-accepted-types"],
            sorted(["type-A", "type-B"] + DEFAULT_ACCEPTED_TYPES))

    def test_exchange_sends_new_accepted_types_hash(self):
        """
        If the accepted types on the client change between exchanges, the
        client will send a new list to the server.
        """
        self.exchanger.register_client_accepted_message_type("type-A")
        types_hash = md5(b"type-A").digest()
        self.transport.extra["client-accepted-types-hash"] = types_hash
        self.exchanger.exchange()
        self.exchanger.register_client_accepted_message_type("type-B")
        self.exchanger.exchange()
        self.assertEqual(
            self.transport.payloads[1]["client-accepted-types"],
            sorted(["type-A", "type-B"] + DEFAULT_ACCEPTED_TYPES))

    def test_exchange_sends_new_types_when_server_screws_up(self):
        """
        If the server suddenly and without warning changes the hash of
        accepted client types that it sends to the client, the client will
        send a new list of types.
        """
        self.exchanger.register_client_accepted_message_type("type-A")
        types_hash = md5(b"type-A").digest()
        self.transport.extra["client-accepted-types-hash"] = types_hash
        self.exchanger.exchange()
        self.transport.extra["client-accepted-types-hash"] = "lol"
        self.exchanger.exchange()
        self.exchanger.exchange()
        self.assertEqual(
            self.transport.payloads[2]["client-accepted-types"],
            sorted(["type-A"] + DEFAULT_ACCEPTED_TYPES))

    def test_register_message_adds_accepted_type(self):
        """
        Using the C{register_message} method of the exchanger causes
        the registered message to be included in the accepted types of
        the client that are sent to the server.
        """
        self.exchanger.register_message("typefoo", lambda m: None)
        types = self.exchanger.get_client_accepted_message_types()
        self.assertEqual(types, sorted(["typefoo"] + DEFAULT_ACCEPTED_TYPES))


class GetAcceptedTypesDiffTest(LandscapeTest):

    def test_diff_empty(self):
        self.assertEqual(get_accepted_types_diff([], []), "")

    def test_diff_add(self):
        self.assertEqual(get_accepted_types_diff([], ["wubble"]), "+wubble")

    def test_diff_remove(self):
        self.assertEqual(get_accepted_types_diff(["wubble"], []), "-wubble")

    def test_diff_no_change(self):
        self.assertEqual(get_accepted_types_diff(["ooga"], ["ooga"]), "ooga")

    def test_diff_complex(self):
        self.assertEqual(get_accepted_types_diff(["foo", "bar"],
                                                 ["foo", "ooga"]),
                         "+ooga foo -bar")
