
import logging
import socket

from twisted.internet.defer import Deferred

from landscape.lib.twisted_util import gather_results
from landscape.lib.bpickle import loads


EC2_API = "http://169.254.169.254/2008-12-01"


class InvalidCredentialsError(Exception):
    """
    Raised when an invalid account title and/or registration password
    is used with L{RegistrationManager.register}.
    """


def persist_property(name):
    def get(self):
        return self._persist.get(name)
    def set(self, value):
        self._persist.set(name, value)
    return property(get, set)

def config_property(name):
    def get(self):
        return getattr(self._config, name)
    return property(get)


class Identity(object):
    """Maintains details about the identity of this Landscape client."""

    secure_id = persist_property("secure-id")
    insecure_id = persist_property("insecure-id")
    computer_title = config_property("computer_title")
    account_name = config_property("account_name")
    registration_password = config_property("registration_password")

    def __init__(self, config, persist):
        self._config = config
        self._persist = persist.root_at("registration")


class RegistrationHandler(object):
    """
    An object from which registration can be requested of the server,
    and which will handle forced ID changes from the server.

    L{register} should be used to initial registration.
    """

    def __init__(self, identity, reactor, exchange, message_store, cloud=False,
                 fetch_async=None):
        self._identity = identity
        self._reactor = reactor
        self._exchange = exchange
        self._message_store = message_store
        self._reactor.call_on("pre-exchange", self._handle_pre_exchange)
        self._reactor.call_on("exchange-done", self._handle_exchange_done)
        self._exchange.register_message("set-id", self._handle_set_id)
        self._exchange.register_message("unknown-id", self._handle_unknown_id)
        self._exchange.register_message("registration",
                                        self._handle_registration)
        self._should_register = None
        self._cloud = cloud
        self._fetch_async = fetch_async

    def should_register(self):
        id = self._identity
        # boolean logic is hard, I'm gonna use an if
        if self._cloud:
            return bool(not id.secure_id
                        and self._message_store.accepts("register-cloud-vm"))
        return bool(not id.secure_id and id.computer_title and id.account_name
                    and self._message_store.accepts("register"))

    def register(self):
        """Attempt to register with the Landscape server.

        @return: A L{Deferred} which will either be fired with None if
            registration was successful or will fail with an
            L{InvalidCredentialsError} if not.
        """
        self._identity.secure_id = None
        self._identity.insecure_id = None
        # This was the original code, it works as well but it
        # takes longer due to the urgent exchange interval.
        #self._exchange.schedule_exchange(urgent=True)
        result = RegistrationResponse(self._reactor).deferred
        self._exchange.exchange()
        return result

    def _handle_exchange_done(self):
        if self.should_register() and not self._should_register:
            # This was the original code, it works as well but it
            # takes longer due to the urgent exchange interval.
            #self._exchange.schedule_exchange(urgent=True)
            self._exchange.exchange()

    def _handle_pre_exchange(self):
        """
        An exchange is about to happen.  If we don't have a secure id
        already set, and we have the needed information available,
        queue a registration message with the server.
        """

        # The point of storing this flag is that if we should *not*
        # register now, and then after the exchange we *should*, we
        # schedule an urgent exchange again.  Without this flag we
        # would just spin trying to connect to the server when
        # something is clearly preventing the registration.
        self._should_register = self.should_register()

        if self._should_register:
            id = self._identity

            self._message_store.delete_all_messages()
            if self._cloud:
                logging.info("Queueing message to register with account %r "
                             "as an EC2 instance." % (id.account_name,))
                userdata_deferred = self._fetch_async(EC2_API + "/user-data")
                instance_id_deferred = self._fetch_async(
                    EC2_API + "/meta-data/instance-id")
                hostname_deferred = self._fetch_async(
                    EC2_API + "/meta-data/local-hostname")
                registration_data = gather_results([userdata_deferred,
                                                    instance_id_deferred,
                                                    hostname_deferred])
                registration_data.addCallback(
                    lambda r:
                    self._exchange.send(
                        {"type": "register-cloud-vm",
                         "otp": loads(r[0])["otp"],
                         "instance-id": r[1],
                         "hostname": r[2]}))
            else:
                with_word = ["without", "with"][bool(id.registration_password)]
                logging.info("Queueing message to register with account %r %s "
                             "a password." % (id.account_name, with_word))

                message = {"type": "register",
                           "computer_title": id.computer_title,
                           "account_name": id.account_name,
                           "registration_password": id.registration_password,
                           "hostname": socket.gethostname()}

                self._exchange.send(message)

    def _handle_set_id(self, message):
        """
        Record and start using the secure and insecure IDs from the given
        message.
        """
        id = self._identity
        id.secure_id = message.get("id")
        id.insecure_id = message.get("insecure-id")
        logging.info("Using new secure-id ending with %s for account %s.",
                     id.secure_id[-10:], id.account_name)
        logging.debug("Using new secure-id: %s", id.secure_id)
        self._reactor.fire("registration-done")
        self._reactor.fire("resynchronize-clients")

    def _handle_registration(self, message):
        if message["info"] == "unknown-account":
            self._reactor.fire("registration-failed")

    def _handle_unknown_id(self, message):
        id = self._identity
        logging.info("Client has unknown secure-id for account %s."
                     % id.account_name)
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

    def _failed(self):
        self.deferred.errback(InvalidCredentialsError())
        self._cancel_calls()
