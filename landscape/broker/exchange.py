"""The part of the broker which deals with communications with the server."""
import time
import logging
import md5

from twisted.internet.defer import succeed

from landscape.lib.message import got_next_expected, ANCIENT
from landscape.log import format_delta
from landscape import API


class MessageExchange(object):
    """
    The Message Exchange is the place where messages are sent to go
    out to the Landscape server.

    The Message Exchange will accumulate messages in its message store
    and periodically deliver them to the server.
    """

    plugin_name = "message-exchange"

    def __init__(self, reactor, store, transport, registration_info,
                 exchange_interval=60*60,
                 urgent_exchange_interval=10,
                 monitor_interval=None,
                 max_messages=100,
                 create_time=time.time):
        self._reactor = reactor
        self._message_store = store
        self._create_time = create_time
        self._transport = transport
        self._registration_info = registration_info
        self._exchange_interval = exchange_interval
        self._urgent_exchange_interval = urgent_exchange_interval
        self._max_messages = max_messages
        self._notification_id = None
        self._exchange_id = None
        self._exchanging = False
        self._urgent_exchange = False

        reactor.call_on("message", self._handle_message)
        reactor.call_on("resynchronize-clients", self._resynchronize)
        reactor.call_on("pre-exit", self.stop)

    def get_exchange_intervals(self):
        return (self._urgent_exchange_interval, self._exchange_interval)

    def send(self, message, urgent=False):
        """Include a message to be sent in an exchange.

        If urgent is True, an exchange with the server will be
        scheduled urgently.
        """
        if "timestamp" not in message:
            message["timestamp"] = int(self._reactor.time())
        message_id = self._message_store.add(message)
        if urgent:
            self.schedule_exchange(urgent=True)
        return message_id

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

        If new types are made available, a
        C{("message-type-accepted", type_name)} reactor event will
        be fired.
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

    def _handle_message(self, message):
        message_type = message["type"]
        if message_type == "accepted-types":
            self._handle_accepted_types(message)
        elif message_type == "resynchronize":
            self._handle_resynchronize(message)
        elif message_type == "set-intervals":
            self._handle_set_intervals(message)

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
            logging.info("Exchange interval set to %d seconds." %
                         self._exchange_interval)
        if "urgent-exchange" in message:
            self._urgent_exchange_interval = message["urgent-exchange"]
            logging.info("Urgent exchange interval set to %d seconds." %
                         self._urgent_exchange_interval)

    def exchange(self):
        """Send pending messages to the server and process responses.

        @return: A deferred that is fired when exchange has completed.

        XXX Actually that is a lie right now. It returns before exchange is
        actually complete.
        """
        if self._exchanging:
            return

        self._exchanging = True

        self._reactor.fire("pre-exchange")

        payload = self.make_payload()

        start_time = self._create_time()
        if self._urgent_exchange:
            logging.info("Starting urgent message exchange.")
        else:
            logging.info("Starting message exchange.")

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
                       urgent interval.  This will reschedule the exchange
                       if necessary.  If another urgent exchange is already
                       scheduled, nothing happens.
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

    def make_payload(self):
        """Return a dict representing the complete payload."""
        store = self._message_store
        accepted_types_str = ";".join(store.get_accepted_types())
        accepted_types_digest = md5.new(accepted_types_str).digest()
        messages = store.get_pending_messages(self._max_messages)
        total_messages = store.count_pending_messages()
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
            server_api = API
        payload = {"server-api": server_api,
                   "client-api": API,
                   "sequence": store.get_sequence(),
                   "messages": messages,
                   "total-messages": total_messages,
                   "next-expected-sequence": store.get_server_sequence(),
                   "accepted-types": accepted_types_digest,
                  }
        return payload

    def _handle_result(self, payload, result):
        message_store = self._message_store

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


        sequence = message_store.get_server_sequence()
        for message in result.get("messages", ()):
            self._reactor.fire("message", message)
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
