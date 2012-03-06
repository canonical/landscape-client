"""The part of the broker which deals with communications with the server."""
import time
import logging
from landscape.lib.hashlib import md5

from twisted.internet.defer import succeed

from landscape.lib.message import got_next_expected, ANCIENT
from landscape.log import format_delta
from landscape import SERVER_API, CLIENT_API


class MessageExchange(object):
    """
    The Message Exchange is the place where messages are sent to go
    out to the Landscape server.

    The Message Exchange will accumulate messages in its message store
    and periodically deliver them to the server.
    """

    plugin_name = "message-exchange"

    def __init__(self, reactor, store, transport, registration_info,
                 exchange_store,
                 config,
                 monitor_interval=None,
                 max_messages=100,
                 create_time=time.time):
        """
        @param reactor: A L{TwistedReactor} used to fire events in response
            to messages received by the server.
        @param store: A L{MessageStore} used to queue outgoing messages.
        @param transport: A L{HTTPTransport} used to deliver messages.
        @param exchange_interval: time interval between subsequent
            exchanges of non-urgent messages.
        @param urgent_exchange_interval: time interval between subsequent
            exchanges of urgent messages.
        """
        self._reactor = reactor
        self._message_store = store
        self._create_time = create_time
        self._transport = transport
        self._registration_info = registration_info
        self._config = config
        self._exchange_interval = config.exchange_interval
        self._urgent_exchange_interval = config.urgent_exchange_interval
        self._max_messages = max_messages
        self._notification_id = None
        self._exchange_id = None
        self._exchanging = False
        self._urgent_exchange = False
        self._client_accepted_types = set()
        self._client_accepted_types_hash = None
        self._message_handlers = {}
        self._exchange_store = exchange_store

        self.register_message("accepted-types", self._handle_accepted_types)
        self.register_message("resynchronize", self._handle_resynchronize)
        self.register_message("set-intervals", self._handle_set_intervals)
        reactor.call_on("resynchronize-clients", self._resynchronize)
        reactor.call_on("pre-exit", self.stop)

    def get_exchange_intervals(self):
        """Return a binary tuple with urgent and normal exchange intervals."""
        return (self._urgent_exchange_interval, self._exchange_interval)

    def _message_is_obsolete(self, message):
        """Returns C{True} if message is obsolete.

        A message is considered obsolete if the secure ID changed since it was
        received.
        """
        if 'operation-id' not in message:
            return False

        operation_id = message['operation-id']
        context = self._exchange_store.get_message_context(operation_id)
        if context is None:
            logging.warning(
                "No message context for message with operation-id: %s"
                % operation_id)
            return False

        # Compare the current secure ID with the one that was in effect when
        # the request message was received.
        result = self._registration_info.secure_id != context.secure_id
        context.remove()

        return result

    def send(self, message, urgent=False):
        """Include a message to be sent in an exchange.

        If urgent is True, an exchange with the server will be
        scheduled urgently.

        @param message: Same as in L{MessageStore.add}.
        """
        if self._message_is_obsolete(message):
            logging.info(
                "Response message with operation-id %s was discarded "
                "because the client's secure ID has changed in the meantime"
                % message.get('operation-id'))
            return None

        if "timestamp" not in message:
            message["timestamp"] = int(self._reactor.time())
        message_id = self._message_store.add(message)
        if urgent:
            self.schedule_exchange(urgent=True)
        return message_id

    def send_at(self, offset, messages):
        self._exchange_id = self._reactor.call_later(
            offset, self.exchange, messages)

    def start(self):
        """Start scheduling exchanges. The first one will be urgent."""
        self.schedule_exchange(urgent=True)

    def stop(self):
        if self._exchange_id is not None:
            self._reactor.cancel_call(self._exchange_id)
            self._exchange_id = None
        if self._notification_id is not None:
            self._reactor.cancel_call(self._notification_id)
            self._notification_id = None

    def _handle_accepted_types(self, message):
        """
        When the server updates us about the types of message it
        accepts, update our message store.

        If this makes existing held messages available for sending,
        urgently exchange messages.

        If new types are made available or old types are dropped a
        C{("message-type-acceptance-changed", type, bool)} reactor
        event will be fired.
        """
        old_types = set(self._message_store.get_accepted_types())
        new_types = set(message["types"])
        diff = get_accepted_types_diff(old_types, new_types)
        self._message_store.set_accepted_types(new_types)
        logging.info("Accepted types changed: %s", diff)
        if self._message_store.get_pending_messages(1):
            self.schedule_exchange(urgent=True)
        for type in old_types - new_types:
            self._reactor.fire("message-type-acceptance-changed", type, False)
        for type in new_types - old_types:
            self._reactor.fire("message-type-acceptance-changed", type, True)

    def _handle_resynchronize(self, message):
        opid = message["operation-id"]
        self._message_store.add({"type": "resynchronize",
                                 "operation-id": opid})
        self._reactor.fire("resynchronize-clients")

    def _resynchronize(self):
        self.schedule_exchange(urgent=True)

    def _handle_set_intervals(self, message):
        if "exchange" in message:
            self._exchange_interval = message["exchange"]
            self._config.exchange_interval = self._exchange_interval
            logging.info("Exchange interval set to %d seconds." %
                         self._exchange_interval)
        if "urgent-exchange" in message:
            self._urgent_exchange_interval = message["urgent-exchange"]
            self._config.urgent_exchange_interval = \
                self._urgent_exchange_interval
            logging.info("Urgent exchange interval set to %d seconds." %
                         self._urgent_exchange_interval)
        self._config.write()

    def exchange(self, messages=None):
        """Send pending messages to the server and process responses.

        An C{pre-exchange} reactor event will be emitted just before the
        actual exchange takes place.

        An C{exchange-done} or C{exchange-failed} reactor event will be
        emitted after a successful or failed exchange.

        @return: A L{Deferred} that is fired when exchange has completed.

        XXX Actually that is a lie right now. It returns before exchange is
        actually complete.
        """
        if self._exchanging:
            return

        self._exchanging = True

        self._reactor.fire("pre-exchange")

        payload = self.make_payload(messages)

        start_time = self._create_time()
        if self._urgent_exchange:
            logging.info("Starting urgent message exchange with %s."
                         % self._transport.get_url())
        else:
            logging.info("Starting message exchange with %s."
                         % self._transport.get_url())

        def handle_result(result):
            self._exchanging = False
            if result:
                if self._urgent_exchange:
                    logging.info("Switching to normal exchange mode.")
                    self._urgent_exchange = False
                self._handle_result(payload, result)
            else:
                self._reactor.fire("exchange-failed")
                logging.info("Message exchange failed.")

            self.schedule_exchange(force=True)
            self._reactor.fire("exchange-done")
            logging.info("Message exchange completed in %s.",
                         format_delta(self._create_time() - start_time))

        self._reactor.call_in_thread(handle_result, None,
                                     self._transport.exchange, payload,
                                     self._registration_info.secure_id,
                                     payload.get("server-api"))
        # exchange will eventually return a Deferred, especially when
        # mp-better-transport-factoring is merged.
        return succeed(None)

    def is_urgent(self):
        """Return a bool showing whether there is an urgent exchange scheduled.
        """
        return self._urgent_exchange

    def schedule_exchange(self, urgent=False, force=False):
        """Schedule an exchange to happen.

        The exchange will occur after some time based on whether C{urgent} is
        True. An C{impending-exchange} reactor event will be emitted
        approximately 10 seconds before the exchange is started.

        @param urgent: If true, ensure an exchange happens within the
            urgent interval.  This will reschedule the exchange if necessary.
            If another urgent exchange is already scheduled, nothing happens.
        @param force: If true, an exchange will necessarily be scheduled,
            even if it was already scheduled before.
        """
        # The 'not self._exchanging' check below is currently untested.
        # It's a bit tricky to test as it is preventing rehooking 'exchange'
        # while there's a background thread doing the exchange itself.
        if (not self._exchanging and
            (force or self._exchange_id is None or
             urgent and not self._urgent_exchange)):
            if urgent:
                self._urgent_exchange = True
            if self._exchange_id:
                self._reactor.cancel_call(self._exchange_id)

            if self._urgent_exchange:
                interval = self._urgent_exchange_interval
            else:
                interval = self._exchange_interval

            if self._notification_id is not None:
                self._reactor.cancel_call(self._notification_id)
            notification_interval = interval - 10
            self._notification_id = self._reactor.call_later(
                notification_interval, self._notify_impending_exchange)

            self._exchange_id = self._reactor.call_later(interval,
                                                         self.exchange)

    def _notify_impending_exchange(self):
        self._reactor.fire("impending-exchange")

    def make_payload(self, messages=None):
        """Return a dict representing the complete exchange payload.

        The payload will contain all pending messages eligible for
        delivery, up to a maximum of C{max_messages} as passed to
        the L{__init__} method.
        """
        store = self._message_store
        accepted_types_digest = self._hash_types(store.get_accepted_types())
        if messages is None:
            messages = store.get_pending_messages(self._max_messages)
            total_messages = store.count_pending_messages()
        else:
            total_messages = len(messages)
        if messages:
            # Each message is tagged with the API that the client was
            # using at the time the message got added to the store.  The
            # logic below will make sure that all messages which are added
            # to the payload being built will have the same api, and any
            # other messages will be postponed to the next exchange.
            server_api = messages[0].get("api")
            for i, message in enumerate(messages):
                if message.get("api") != server_api:
                    break
            else:
                i = None
            if i is not None:
                del messages[i:]

            # DEPRECATED Remove this once API 2.0 is gone:
            if server_api is None:
                # The per-message API logic was introduced on API 2.1, so a
                # missing API must be 2.0.
                server_api = "2.0"
        else:
            server_api = SERVER_API
        payload = {"server-api": server_api,
                   "client-api": CLIENT_API,
                   "sequence": store.get_sequence(),
                   "messages": messages,
                   "total-messages": total_messages,
                   "next-expected-sequence": store.get_server_sequence(),
                   "accepted-types": accepted_types_digest,
                  }
        accepted_client_types = self.get_client_accepted_message_types()
        accepted_client_types_hash = self._hash_types(accepted_client_types)
        if accepted_client_types_hash != self._client_accepted_types_hash:
            payload["client-accepted-types"] = accepted_client_types
        return payload

    def _hash_types(self, types):
        accepted_types_str = ";".join(types)
        return md5(accepted_types_str).digest()

    def _handle_result(self, payload, result):
        """Handle a response from the server.

        Called by L{exchange} after a batch of messages has been
        successfully delivered to the server.

        If the C{server_uuid} changed, a C{"server-uuid-changed"} event
        will be fired.

        Call L{handle_message} for each message in C{result}.

        @param payload: The payload that was sent to the server.
        @param result: The response got in reply to the C{payload}.
        """
        message_store = self._message_store
        self._client_accepted_types_hash = result.get(
            "client-accepted-types-hash")
        next_expected = result.get("next-expected-sequence")
        old_sequence = message_store.get_sequence()
        if next_expected is None:
            next_expected = message_store.get_sequence()
            next_expected += len(payload["messages"])

        message_store_state = got_next_expected(message_store, next_expected)
        message_store.commit()
        if message_store_state == ANCIENT:
            # The server has probably lost some data we sent it. The
            # slate has been wiped clean (by got_next_expected), now
            # let's fire an event to tell all the plugins that they
            # ought to generate new messages so the server gets some
            # up-to-date data.
            logging.info("Server asked for ancient data: resynchronizing all "
                         "state with the server.")

            message_store.add({"type": "resynchronize"})
            self._reactor.fire("resynchronize-clients")

        old_uuid = message_store.get_server_uuid()
        new_uuid = result.get("server-uuid")
        if new_uuid != old_uuid:
            logging.info("Server UUID changed (old=%s, new=%s)."
                         % (old_uuid, new_uuid))
            self._reactor.fire("server-uuid-changed", old_uuid, new_uuid)
            message_store.set_server_uuid(new_uuid)

        sequence = message_store.get_server_sequence()
        for message in result.get("messages", ()):
            self.handle_message(message)
            sequence += 1
            message_store.set_server_sequence(sequence)
            message_store.commit()

        if message_store.get_pending_messages(1):
            logging.info("Pending messages remain after the last exchange.")
            # Either the server asked us for old messages, or we
            # otherwise have more messages even after transferring
            # what we could.
            if next_expected != old_sequence:
                self.schedule_exchange(urgent=True)

    def register_message(self, type, handler):
        """Register a handler for the given message type.

        The C{handler} callable will to be executed when a message of
        type C{type} has been received from the server.

        Multiple handlers for the same type will be called in the
        order they were registered.
        """
        self._message_handlers.setdefault(type, []).append(handler)
        self._client_accepted_types.add(type)

    def handle_message(self, message):
        """
        Handle a message received from the server.

        Any message handlers registered with L{register_message} will
        be called.
        """
        if 'operation-id' in message:
            # This is a message that requires a response. Store the secure ID
            # so we can check for obsolete results later.
            self._exchange_store.add_message_context(
                message['operation-id'], self._registration_info.secure_id,
                message['type'])

        self._reactor.fire("message", message)
        # This has plan interference! but whatever.
        if message["type"] in self._message_handlers:
            for handler in self._message_handlers[message["type"]]:
                handler(message)

    def register_client_accepted_message_type(self, type):
        # stringify the type because it's a dbus.String.  It should work
        # anyway, but this is just for sanity and less confusing logs.
        self._client_accepted_types.add(str(type))

    def get_client_accepted_message_types(self):
        return sorted(self._client_accepted_types)


def get_accepted_types_diff(old_types, new_types):
    old_types = set(old_types)
    new_types = set(new_types)
    added_types = new_types - old_types
    stable_types = old_types & new_types
    removed_types = old_types - new_types
    diff = []
    diff.extend(["+%s" % type for type in added_types])
    diff.extend(["%s" % type for type in stable_types])
    diff.extend(["-%s" % type for type in removed_types])
    return " ".join(diff)
