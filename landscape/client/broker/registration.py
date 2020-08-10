"""
Handle client registration against the server.

When the service is started for the first time it connects to the server
as a new client without providing any identification credentials, and the
server replies with the available registration mechanisms. At this point
the machinery in this module will notice that we have no identification
credentials yet and that the server accepts registration messages, so it
will craft an appropriate one and send it out.
"""
import logging

from twisted.internet.defer import Deferred

from landscape.client.broker.exchange import maybe_bytes
from landscape.lib.juju import get_juju_info
from landscape.lib.tag import is_valid_tag_list
from landscape.lib.network import get_fqdn
from landscape.lib.vm_info import get_vm_info, get_container_info
from landscape.lib.versioning import is_version_higher


class RegistrationError(Exception):
    """
    Raised when the registration failed because an invalid account title
    and/or registration key are used with RegistrationManager.register,
    or the server has too many pending computers already.
    """


def persist_property(name):

    def get(self):
        value = self._persist.get(name)
        try:
            return value.decode("ascii")
        except (AttributeError, UnicodeDecodeError):
            return value

    def set(self, value):
        self._persist.set(name, value)

    return property(get, set)


def config_property(name):

    def get(self):
        return getattr(self._config, name)

    return property(get)


class Identity(object):
    """Maintains details about the identity of this Landscape client.

    @ivar secure_id: A server-provided ID for secure message exchange.
    @ivar insecure_id: Non-secure server-provided ID, mainly used with
        the ping server.
    @ivar computer_title: See L{BrokerConfiguration}.
    @ivar account_name: See L{BrokerConfiguration}.
    @ivar registration_password: See L{BrokerConfiguration}.
    @ivar tags: See L{BrokerConfiguration}

    @param config: A L{BrokerConfiguration} object, used to set the
        C{computer_title}, C{account_name} and C{registration_password}
        instance variables.
    """

    secure_id = persist_property("secure-id")
    insecure_id = persist_property("insecure-id")

    computer_title = config_property("computer_title")
    account_name = config_property("account_name")
    registration_key = config_property("registration_key")
    tags = config_property("tags")
    access_group = config_property("access_group")

    def __init__(self, config, persist):
        self._config = config
        self._persist = persist.root_at("registration")


class RegistrationHandler(object):
    """
    An object from which registration can be requested of the server,
    and which will handle forced ID changes from the server.

    L{register} should be used to perform initial registration.
    """

    def __init__(self, config, identity, reactor, exchange, pinger,
                 message_store, fetch_async=None):
        self._config = config
        self._identity = identity
        self._reactor = reactor
        self._exchange = exchange
        self._pinger = pinger
        self._message_store = message_store
        self._reactor.call_on("run", self._get_juju_data)
        self._reactor.call_on("pre-exchange", self._handle_pre_exchange)
        self._reactor.call_on("exchange-done", self._handle_exchange_done)
        self._exchange.register_message("set-id", self._handle_set_id)
        self._exchange.register_message("unknown-id", self._handle_unknown_id)
        self._exchange.register_message("registration",
                                        self._handle_registration)
        self._should_register = None
        self._fetch_async = fetch_async
        self._juju_data = None

    def should_register(self):
        id = self._identity
        if id.secure_id:
            return False

        return bool(id.computer_title and
                    id.account_name and
                    self._message_store.accepts("register"))

    def register(self):
        """
        Attempt to register with the Landscape server.

        @return: A L{Deferred} which will either be fired with None if
            registration was successful or will fail with an
            RegistrationError if not.
        """
        self._identity.secure_id = None
        self._identity.insecure_id = None
        result = RegistrationResponse(self._reactor).deferred
        self._exchange.exchange()
        return result

    def _get_juju_data(self):
        """Load Juju information."""
        juju_info = get_juju_info(self._config)
        if juju_info is None:
            return None
        self._juju_data = juju_info

    def _handle_exchange_done(self):
        """Registered handler for the C{"exchange-done"} event.

        If we are not registered yet, schedule another message exchange.

        The first exchange made us accept the message type "register", so
        the next "pre-exchange" event will make L{_handle_pre_exchange}
        queue a registration message for delivery.
        """
        if self.should_register() and not self._should_register:
            self._exchange.exchange()

    def _handle_pre_exchange(self):
        """
        An exchange is about to happen.  If we don't have a secure id already
        set, and we have the needed information available, queue a registration
        message with the server.
        """
        # The point of storing this flag is that if we should *not* register
        # now, and then after the exchange we *should*, we schedule an urgent
        # exchange again.  Without this flag we would just spin trying to
        # connect to the server when something is clearly preventing the
        # registration.
        self._should_register = self.should_register()
        if not self._should_register:
            return

        # These are just to shorten the code.
        identity = self._identity
        account_name = identity.account_name

        if not account_name:
            self._reactor.fire("registration-failed", reason="unknown-account")
            return

        tags = identity.tags
        group = identity.access_group
        registration_key = identity.registration_key

        self._message_store.delete_all_messages()

        if not is_valid_tag_list(tags):
            tags = None
            logging.error("Invalid tags provided for registration.")

        message = {"type": "register",
                   "hostname": get_fqdn(),
                   "account_name": account_name,
                   "computer_title": identity.computer_title,
                   "registration_password": identity.registration_key,
                   "tags": tags,
                   "container-info": get_container_info(),
                   "vm-info": get_vm_info()}

        if group:
            message["access_group"] = group

        server_api = self._message_store.get_server_api()
        # If we have juju data to send and if the server is recent enough to
        # know how to handle juju data, then we include it in the registration
        # message. We want to trigger the 3.3 server handler because client
        # version 14.01 has a different format for the juju-info field,
        # so this makes sure that the correct schema is used by the server
        # when validating our message.
        if self._juju_data and is_version_higher(server_api, b"3.3"):
            message["juju-info"] = {
                "environment-uuid": self._juju_data["environment-uuid"],
                "api-addresses": self._juju_data["api-addresses"],
                "machine-id": self._juju_data["machine-id"]}

        # The computer is a normal computer, possibly a container.
        with_word = "with" if bool(registration_key) else "without"
        with_tags = "and tags %s " % tags if tags else ""
        with_group = "in access group '%s' " % group if group else ""

        logging.info(
            u"Queueing message to register with account %r %s%s"
            "%s a password." % (
                account_name, with_group, with_tags, with_word))
        self._exchange.send(message)

    def _handle_set_id(self, message):
        """Registered handler for the C{"set-id"} event.

        Record and start using the secure and insecure IDs from the given
        message.

        Fire C{"registration-done"} and C{"resynchronize-clients"}.
        """
        id = self._identity
        if id.secure_id:
            logging.info("Overwriting secure_id with '%s'" % id.secure_id)

        id.secure_id = message.get("id")
        id.insecure_id = message.get("insecure-id")
        logging.info("Using new secure-id ending with %s for account %s.",
                     id.secure_id[-10:], id.account_name)
        logging.debug("Using new secure-id: %s", id.secure_id)
        self._reactor.fire("registration-done")
        self._reactor.fire("resynchronize-clients")

    def _handle_registration(self, message):
        message_info = maybe_bytes(message["info"])
        if message_info in ("unknown-account", "max-pending-computers"):
            self._reactor.fire("registration-failed", reason=message_info)

    def _handle_unknown_id(self, message):
        id = self._identity
        clone = message.get("clone-of")
        if clone is None:
            logging.info("Client has unknown secure-id for account %s."
                         % id.account_name)
        else:
            logging.info("Client is clone of computer %s" % clone)
            # Set a new computer title so when a registration request will be
            # made, the pending computer UI will indicate that this is a clone
            # of another computer. There's no need to persist the changes since
            # a new registration will be requested immediately.
            if clone == self._config.computer_title:
                title = "%s (clone)" % self._config.computer_title
            else:
                title = "%s (clone of %s)" % (self._config.computer_title,
                                              clone)
            self._config.computer_title = title
        id.secure_id = None
        id.insecure_id = None


class RegistrationResponse(object):
    """A helper for dealing with the response of a single registration request.

    @ivar deferred: The L{Deferred} that will be fired as per
        L{RegistrationHandler.register}.
    """

    def __init__(self, reactor):
        self._reactor = reactor
        self._done_id = reactor.call_on("registration-done", self._done)
        self._failed_id = reactor.call_on("registration-failed", self._failed)
        self.deferred = Deferred()

    def _cancel_calls(self):
        self._reactor.cancel_call(self._done_id)
        self._reactor.cancel_call(self._failed_id)

    def _done(self):
        self.deferred.callback(None)
        self._cancel_calls()

    def _failed(self, reason=None):
        self.deferred.errback(RegistrationError(reason))
        self._cancel_calls()
