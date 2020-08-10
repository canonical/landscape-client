"""Manage outgoing and incoming messages when communicating with the server.

The protocol to communicate between the client and the server has been designed
to be very robust so that messages are not lost. In addition it is (vaguely)
symmetric, as the client and server need to send messages both ways.

Client->Server Payload
======================

All message payloads are bpickled with L{landscape.lib.bpickle.dumps}. Client
to server payloads are C{dict}s of the form::

  {'server-api': SERVER_API_VERSION,
   'client-api': CLIENT_API_VERSION,
   'sequence': SEQUENCE_NUMBER,
   'accepted-types': SERVER_ACCEPTED_TYPES_DIGEST,
   'messages': MESSAGES,
   'total-messages': TOTAL_COUNT_OF_PENDING_MESSAGES,
   'next-expected-sequence': EXPECTED_SEQUENCE_NUMBER,
   'client-accepted-types': CLIENT_ACCEPTED_TYPES (optional)}

The values have the following semantics:

  - C{SERVER_API_VERSION}: The API version that is required on the server
    in order to process the messages in this payload (the schema and semantics
    of message types are usually different for different API versions).

  - C{CLIENT_API_VERSION}: The API version of the client, hinting the server
    about the schema and semantics of the messages types accepted by the client
    (see below).

  - C{SEQUENCE_NUMBER}: A monotonically increasing nonnegative integer. The
    meaning of this is described below.

  - C{SERVER_ACCEPTED_TYPES_DIGEST}: A hash of the message types that the
    client thinks are currently accepted by the server. The server can use it
    to know whether to send the client a new up-to-date list of accepted
    message types.

  - C{MESSAGES}: A python list of messages, described below.

  - C{TOTAL_COUNT_OF_PENDING_MESSAGES}: The total number of messages in the
    client outgoing queue. This is includes the number of messages being sent
    in this payload, plus any other messages still pending and not included
    here.

  - C{EXPECTED_SEQUENCE_NUMBER}: The sequence number which the client expects
    the next message sent from the server to have.

  - C{CLIENT_ACCEPTED_TYPES}: Optionally, a list of message types that the
    client accepts. The server is supposed to send the client only messages of
    this type. It will be inlcuded in the payload only if the hash that the
    server sends us is out-of-date. This behavior is simmetric with respect to
    the C{SERVER_ACCEPTED_TYPES_DIGEST} field described above.

Server->Client Payload
======================

The payloads that the server sends to not-yet-registered clients (i.e. clients
that don't provide a secure ID associated with a computer) are C{dict}s of the
form::

  {'server-uuid': SERVER_UUID,
   'server-api': SERVER_API,
   'messages': MESSAGES}

where:

  - C{SERVER_UUID}: A string identifying the particular Landscape server the
    client is talking to.

  - C{SERVER_API}: The version number of the highest server API that this
    particular server is able to handle. It can be used by the client to
    implement backward compatibility with old servers, knowing what message
    schemas the server expects (since schemas can change from version to
    version).

  - C{MESSAGES}: A python list of messages, described below.

Additionally, payloads to registered clients will include these fields::

  {'next-expected-sequence': EXPECTED_SEQUENCE_NUMBER,
   'next-expected-token': EXPECTED_EXCHANGE_TOKEN,
   'client-accepted-types-hash': CLIENT_ACCEPTED_TYPES_DIGEST,

where:

  - C{EXPECTED_SEQUENCE_NUMBER}: The sequence number which the server expects
    the next message sent from the client to have.

  - C{EXPECTED_EXCHANGE_TOKEN}: The token (UUID string) that the server expects
    to receive back the next time the client performs an exchange. Since the
    client receives a new token at each exchange, this can be used by the
    server to detect cloned clients (either the orignal client or the cloned
    client will eventually send an expired token). The token is sent by the
    client as a special HTTP header (see L{landscape.broker.transport}).

  - C{CLIENT_ACCEPTED_TYPES_DIGEST}: A hash of the message types that the
    server thinks are currently accepted by the client. The client can use it
    to know whether to send to the server an up-to-date list the message types
    it now accepts (see CLIENT_ACCEPTED_TYPES in the client->server payload).

Individual Messages
===================

A message is a C{dict} with required and optional keys. Messages are packed
into Python lists and set as the value of the 'messages' key in the payload.

The C{dict} of a single message is of the form::

  {'type': MESSAGE_TYPE,
   ...}

where:

  - C{MESSAGE_TYPE}: A simple string, which lets the server decide what handler
    to dispatch the message to, also considering the SERVER_API_VERSION value.

  - C{...}: Other entries specific to the type of message.

This format is the same for messages sent by the server to the client and for
messages sent by the client to the server. In addition, messages sent by the
client to the server will contain also the following extra fields::

  {...
   'api': SERVER_API,
   'timestamp': TIMESTAMP,
   ...}

where:

 - C{SERVER_API}: The server API that the client was targeting when it
   generated the message. In single exchange the client will only include
   messages targeted to the same server API.

 - C{TIMESTAMP}: A timestamp indicating when the message was generated.

Message Sequencing
==================

A message numbering system is built in to the protocol to ensure robustness of
client/server communication. The way this works is not totally symmetrical, as
the client must connect to the server via HTTP, but the ordering that things
happen in over the course of many connections remains the same (see also
L{landscape.broker.store} for more concrete examples):

  - Receiver tells Sender which sequence number it expects the next batch of
    messages to start with.

  - Sender gives some messages to Receiver, specifying the sequence number of
    the first message. If the expected and actual sequence numbers are out of
    synch, Sender resynchronizes in a certain way.

The client and server must play the part of *both* of these roles on every
interaction, but it simplifies things to talk about them in terms of a single
role at a time.

When the client connects to the server, it does the following things acting
in the role of Sender (which is by far its more burdened role):

  - Send a payload containing messages and a sequence number. The sequence
    number should be the same number that the server gave as
    next-expected-sequence in the prior connection, or 0 if there was no
    previous connection.

  - Get back a next-expected-sequence from the server. If that value is is not
    len(messages) + previous-next-expected, then resynchronize.

It does the following when acting as Receiver:

  - Send a payload containing a next-expected-sequence, which should be the
    sequence number of the first message that the server responds with. This
    value should be previous-next-expected + len(previous_messages).

  - Receive some messages from the server, and process them immediately.

When the server is acting as Sender, it does the following:

  - Wait for a payload with next-expected-sequence from the client.

  - Perhaps resynchronize if next-expected-sequence is unexpected.

  - Respond with a payload of messages to the client. No sequence identifier
    is given for this payload of messages, because it would be redundant with
    data that has already passed over the wire (received from the client)
    during the very same TCP connection.

When the server is acting as a Receiver, it does the following:

  - Wait for a payload with a sequence identifier and a load of messages.
  - Respond with a next-expected-sequence.

There are two interesting exceptional cases which must be handled with
resynchronization:

  1. Messages received with sequence numbers less than the next expected
     sequence number should be discarded, and further messages starting at
     the expected sequence numbers should be processed.

  2. If the sequence number is higher than what the receiver expected, then
     no messages are processed and the receiver responds with the same
     {'next-expected-sequence': N}, so that the sender can resynchronize
     itself.

This implies that the receiver must record the sequence number of the last
successfully processed message, in order for it to respond to the sender
with that number. In addition, the sender must save outbound messages even
after they have been delivered over the transport, until the sender receives
a next-expected-sequence higher than the outbound message. The details of
this logic are described in L{landscape.broker.store}.

Exchange Sequence
=================

Diagram::

  1. BrokerService    -->  MessageExchange               : Start

  2. MessageExchange  -->  MessageExchange               : Schedule exchange

  3. [event]          <--  MessageExchange               : Fire "pre-exchange"

  4. [optional]                                          : Do registration
     (See L{landscape.broker.registration})              : sequence

  5. MessageExchange  -->  MessageStore                  : Request pending
                                                         : messages

  6. MessageExchange  <--  MessageStore                  : return( Messages )

  7. MessageExchange  -->  HTTPTransport                 : Exchange

  8. HTTPTransport    -->  {Server}LandscapeMessageSystem
                                                         : HTTP POST

  9. [Scope: Server]
   |
   |   9.1 LandscapeMessageSystem --> ComputerMessageAPI : run
   |
   |   9.2 ComputerMessageAPI     --> FunctionHandler    : handle
   |
   |   9.3 FunctionHandler        --> Callable           : call
   |       ( See also server code at:
   |             - C{canonical.landscape.message.handlers}
   |             - C{canonical.message.handler.FunctionHandler} )
   |
   |
   |   9.4 [If: the callable raises ConsistencyError]
   |     |
   |     | 9.4.1 ComputerMessageAPI --> Computer         : request
   |     |                                               : Resynchronize
   |     |
   |     | 9.4.2 Computer           --> Computer         : Create
   |     |                                               : ResynchronizeRequest
   |     |                                               : activity
   |     |
   |     --[End If]
   |
   |  9.5 ComputerMessageAPI     --> Computer            : get deliverable
   |                                                     : activities
   |
   |  9.6 ComputerMessageAPI     <-- Computer            : return activities
   |
   |  9.7 [Loop over activities]
   |    |
   |    | 9.7.1 ComputerMessageAPI  --> Activity         : deliver
   |    |
   |    | 9.7.2 Activity            --> MessageStore     : add activity message
   |    |
   |    --[End Loop]
   |
   |  9.8 ComputerMessageAPI     --> MessageStore        : get pending messages
   |
   |  9.9 ComputerMessageAPI     <-- MessageStore        : return messages
   |
   | 9.10 LandscapeMessageSystem <-- ComputerMessageAPI  : return payload
   |                                                     : (See below)
   |
   -- [End Scope]

  10. HTTPTransport    <--  {Server}LandscapeMessageSystem
                                                         : HTTP response
                                                         : with payload

  11. MessageExchange  <--  HTTPTransport                : response

  12. [If: server says it expects a very old message]
   |
   |  12.1 [event]              <-- MessageExchange      : event
   |       (See L{landscape.broker.server})              : "resynchronize-
   |                                                     : clients"
   |
   -- [End if]

  13. [Loop: over messages in payload]
   |
   |  13.1 [event]             <-- MessageExchange       : event
   |                                                     : message (message)
   |
   |  13.2 [Switch: on message type]
   |     |
   |     |- 13.2.1 [Case: message type is "accepted-types"]
   |     |       |
   |     |       | 13.2.1.1 MessageExchange -> MessageStore
   |     |       |                                       : set accepted types
   |     |       |
   |     |       | 13.2.1.2 MessageExchange -> MessageExchange
   |     |       |                                       : schedule urgent
   |     |       |                                       : exchange
   |     |       --[End Case]
   |     |
   |     |- 13.2.2 [Case: message type is "resynchronize"]
   |     |       |
   |     |       | 13.2.2.1 [event]         <- MessageExchange
   |     |       |        (See L{landscape.broker.server})
   |     |       |                                      : event
   |     |       |                                      : "resynchronize-
   |     |       |                                      : clients"
   |     |       |
   |     |       | 13.2.2.2 MessageExchange -> MessageStore
   |     |       |                                      : add "resynchronize"
   |     |       |                                      : message
   |     |       |
   |     |       | 13.2.2.3 MessageExchange -> MessageExchange
   |     |       |                                      : schedule urgent
   |     |       |                                      : exchange
   |     |       |
   |     |       --[End Case]
   |     |
   |     |- 13.2.3 [Case: message type is "set-intervals"]
   |     |       |
   |     |       | 13.2.3.1 MessageExchange -> BrokerConfiguration
   |     |       |                                      : set exchange
   |     |       |                                      : interval
   |     |       |
   |     |       --[End Case]
   |     |
   |     -- [End Switch]
   |
   -- [End Loop]

  14. Schedule exchange

"""
import time
import logging
from landscape.lib.hashlib import md5

from twisted.internet.defer import Deferred, succeed
from twisted.python.compat import _PY3

from landscape.lib.fetch import HTTPCodeError, PyCurlError
from landscape.lib.format import format_delta
from landscape.lib.message import got_next_expected, ANCIENT
from landscape.lib.versioning import is_version_higher, sort_versions

from landscape import DEFAULT_SERVER_API, SERVER_API, CLIENT_API


class MessageExchange(object):
    """Schedule and handle message exchanges with the server.

    The L{MessageExchange} is the place where messages are sent to go out
    to the Landscape server. It accumulates messages in its L{MessageStore}
    and periodically delivers them to the server.

    It is also the place where messages coming from the server are handled. For
    each message type the L{MessageExchange} supports setting an handler that
    will be invoked when a message of the that type is received.

    An exchange is performed with an HTTP POST request, whose body contains
    outgoing messages and whose response contains incoming messages.
    """

    # The highest server API that we are capable of speaking
    _api = SERVER_API

    def __init__(self, reactor, store, transport, registration_info,
                 exchange_store, config, max_messages=100):
        """
        @param reactor: The L{LandscapeReactor} used to fire events in response
            to messages received by the server.
        @param store: The L{MessageStore} used to queue outgoing messages.
        @param transport: The L{HTTPTransport} used to deliver messages.
        @param registration_info: The L{Identity} storing our secure ID.
        @param config: The L{BrokerConfiguration} with the `exchange_interval`
            and `urgent_exchange_interval` parameters, respectively holding
            the time interval between subsequent exchanges of non-urgent
            messages, and the time interval between subsequent exchanges
            of urgent messages.
        """
        self._reactor = reactor
        self._message_store = store
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
        self._stopped = False

        self.register_message("accepted-types", self._handle_accepted_types)
        self.register_message("resynchronize", self._handle_resynchronize)
        self.register_message("set-intervals", self._handle_set_intervals)
        reactor.call_on("resynchronize-clients", self._resynchronize)

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

    def start(self):
        """Start scheduling exchanges. The first one will be urgent."""
        self.schedule_exchange(urgent=True)

    def stop(self):
        """Stop scheduling exchanges."""
        if self._exchange_id is not None:
            # Cancel the next scheduled exchange
            self._reactor.cancel_call(self._exchange_id)
            self._exchange_id = None
        if self._notification_id is not None:
            # Cancel the next scheduled notification of an impending exchange
            self._reactor.cancel_call(self._notification_id)
            self._notification_id = None
        self._stopped = True

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
        scopes = message.get("scopes")
        self.send({"type": "resynchronize", "operation-id": opid})
        self._reactor.fire("resynchronize-clients", scopes=scopes)

    def _resynchronize(self, scopes=None):
        # When re-synchronisation occurs we don't want any previous messages
        # being sent to the server, dropping the existing session_ids means
        # that messages sent with those IDs will be dropped by the broker.
        self._message_store.drop_session_ids(scopes)
        self.schedule_exchange(urgent=True)

    def _handle_set_intervals(self, message):
        if "exchange" in message:
            self._config.exchange_interval = message["exchange"]
            logging.info("Exchange interval set to %d seconds." %
                         self._config.exchange_interval)
        if "urgent-exchange" in message:
            self._config.urgent_exchange_interval = message["urgent-exchange"]
            logging.info("Urgent exchange interval set to %d seconds." %
                         self._config.urgent_exchange_interval)
        self._config.write()

    def exchange(self):
        """Send pending messages to the server and process responses.

        A C{pre-exchange} reactor event will be emitted just before the
        actual exchange takes place.

        An C{exchange-done} or C{exchange-failed} reactor event will be
        emitted after a successful or failed exchange.

        @return: A L{Deferred} that is fired when exchange has completed.
        """
        if self._exchanging:
            return succeed(None)

        self._exchanging = True

        self._reactor.fire("pre-exchange")

        payload = self._make_payload()

        start_time = time.time()
        if self._urgent_exchange:
            logging.info("Starting urgent message exchange with %s."
                         % self._transport.get_url())
        else:
            logging.info("Starting message exchange with %s."
                         % self._transport.get_url())

        deferred = Deferred()

        def exchange_completed():
            self.schedule_exchange(force=True)
            self._reactor.fire("exchange-done")
            logging.info("Message exchange completed in %s.",
                         format_delta(time.time() - start_time))
            deferred.callback(None)

        def handle_result(result):
            self._exchanging = False
            if result:
                if self._urgent_exchange:
                    logging.info("Switching to normal exchange mode.")
                    self._urgent_exchange = False
                self._handle_result(payload, result)
                self._message_store.record_success(int(self._reactor.time()))
            else:
                self._reactor.fire("exchange-failed")
                logging.info("Message exchange failed.")
            exchange_completed()

        def handle_failure(error_class, error, traceback):
            self._exchanging = False

            if isinstance(error, HTTPCodeError) and error.http_code == 404:
                # If we got a 404 HTTP error it could be that we're trying to
                # speak a server API version that the server does not support,
                # e.g. this client was pointed at a different server. We'll to
                # downgrade to the least possible server API version and try
                # again.
                if self._message_store.get_server_api() != DEFAULT_SERVER_API:
                    self._message_store.set_server_api(DEFAULT_SERVER_API)
                    self.exchange()
                    return

            ssl_error = False
            if isinstance(error, PyCurlError) and error.error_code == 60:
                # The error returned is an SSL error, most likely the server
                # is using a self-signed certificate. Let's fire a special
                # event so that the GUI can display a nice message.
                logging.error("Message exchange failed: %s" % error.message)
                ssl_error = True

            self._reactor.fire("exchange-failed", ssl_error=ssl_error)

            self._message_store.record_failure(int(self._reactor.time()))
            logging.info("Message exchange failed.")
            exchange_completed()

        self._reactor.call_in_thread(handle_result, handle_failure,
                                     self._transport.exchange, payload,
                                     self._registration_info.secure_id,
                                     self._get_exchange_token(),
                                     payload.get("server-api"))
        return deferred

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
        if self._stopped:
            return
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
                interval = self._config.urgent_exchange_interval
            else:
                interval = self._config.exchange_interval

            if self._notification_id is not None:
                self._reactor.cancel_call(self._notification_id)
            notification_interval = interval - 10
            self._notification_id = self._reactor.call_later(
                notification_interval, self._notify_impending_exchange)

            self._exchange_id = self._reactor.call_later(
                interval, self.exchange)

    def _get_exchange_token(self):
        """Get the token given us by the server at the last exchange.

        It will be C{None} if we are not fully registered yet or if something
        bad happened during the last exchange and we could not get the token
        that the server had given us.
        """
        exchange_token = self._message_store.get_exchange_token()

        # Before starting the exchange set the saved token to None. This will
        # prevent us from locking ourselves out if the exchange fails or if we
        # crash badly, while the server has saved a new token that we couldn't
        # receive or persist (this works because if the token is None the
        # server will be forgiving and will authenticate us based only on the
        # secure ID we provide).
        self._message_store.set_exchange_token(None)
        self._message_store.commit()

        return exchange_token

    def _notify_impending_exchange(self):
        self._reactor.fire("impending-exchange")

    def _make_payload(self):
        """Return a dict representing the complete exchange payload.

        The payload will contain all pending messages eligible for
        delivery, up to a maximum of C{max_messages} as passed to
        the L{__init__} method.
        """
        store = self._message_store
        accepted_types_digest = self._hash_types(store.get_accepted_types())
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
        else:
            server_api = store.get_server_api()
        payload = {"server-api": server_api,
                   "client-api": CLIENT_API,
                   "sequence": store.get_sequence(),
                   "accepted-types": accepted_types_digest,
                   "messages": messages,
                   "total-messages": total_messages,
                   "next-expected-sequence": store.get_server_sequence()}
        accepted_client_types = self.get_client_accepted_message_types()
        accepted_client_types_hash = self._hash_types(accepted_client_types)
        if accepted_client_types_hash != self._client_accepted_types_hash:
            payload["client-accepted-types"] = accepted_client_types
        return payload

    def _hash_types(self, types):
        accepted_types_str = ";".join(types).encode("ascii")
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
            # If the server doesn't specify anything for the next-expected
            # value, just assume that it processed all messages that we sent
            # fine.
            next_expected = message_store.get_sequence()
            next_expected += len(payload["messages"])

        message_store_state = got_next_expected(message_store, next_expected)
        if message_store_state == ANCIENT:
            # The server has probably lost some data we sent it. The
            # slate has been wiped clean (by got_next_expected), now
            # let's fire an event to tell all the plugins that they
            # ought to generate new messages so the server gets some
            # up-to-date data.
            logging.info("Server asked for ancient data: resynchronizing all "
                         "state with the server.")
            self.send({"type": "resynchronize"})
            self._reactor.fire("resynchronize-clients")

        # Save the exchange token that the server has sent us. We will provide
        # it at the next exchange to prove that we're still the same client.
        # See also landscape.broker.transport.
        message_store.set_exchange_token(result.get("next-exchange-token"))

        old_uuid = message_store.get_server_uuid()
        new_uuid = result.get("server-uuid")
        if new_uuid and isinstance(new_uuid, bytes):
            new_uuid = new_uuid.decode("ascii")
        if new_uuid != old_uuid:
            logging.info("Server UUID changed (old=%s, new=%s)."
                         % (old_uuid, new_uuid))
            self._reactor.fire("server-uuid-changed", old_uuid, new_uuid)
            message_store.set_server_uuid(new_uuid)

        # Extract the server API from the payload. If it's not there it must
        # be 3.2, because it's the one that didn't have this field.
        server_api = result.get("server-api", b"3.2")

        if _PY3 and not isinstance(server_api, bytes):
            # The "server-api" field in the bpickle payload sent by the server
            # is a string, however in Python 3 we need to convert it to bytes,
            # since that's what the rest of the code expects.
            server_api = server_api.encode()

        if is_version_higher(server_api, message_store.get_server_api()):
            # The server can handle a message API that is higher than the one
            # we're currently using. If the highest server API is greater than
            # our one, so let's use our own, which is the most recent we can
            # speak. Otherwise if the highest server API is less than or equal
            # than ours, let's use the server one, because is the most recent
            # common one.
            lowest_server_api = sort_versions([server_api, self._api])[-1]
            message_store.set_server_api(lowest_server_api)

        message_store.commit()

        sequence = message_store.get_server_sequence()
        for message in result.get("messages", ()):
            # The wire format of the 'type' field is bytes, but our handlers
            # actually expect it to be a string. Some unit tests set it to
            # a regular string (since there is no difference between strings
            # and bytes in Python 2), so we check the type before converting.
            message["type"] = maybe_bytes(message["type"])
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
        message_type = maybe_bytes(message["type"])
        if message_type in self._message_handlers:
            for handler in self._message_handlers[message_type]:
                handler(message)

    def register_client_accepted_message_type(self, type):
        # stringify the type for sanity and less confusing logs.
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


def maybe_bytes(thing):
    """Return a py3 ascii string from maybe py2 bytes."""
    if _PY3 and isinstance(thing, bytes):
        return thing.decode("ascii")
    return thing
