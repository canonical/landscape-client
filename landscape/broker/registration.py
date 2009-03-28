
import logging
import socket
import pycurl

from twisted.internet.defer import Deferred

from landscape.lib.twisted_util import gather_results
from landscape.lib.bpickle import loads
from landscape.lib.log import log_failure
from landscape.lib.fetch import fetch, HTTPCodeError


EC2_API = "http://169.254.169.254/latest"


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

    L{register} should be used to perform initial registration.
    """

    def __init__(self, config, identity, reactor, exchange, pinger,
                 message_store, cloud=False, fetch_async=None):
        self._config = config
        self._identity = identity
        self._reactor = reactor
        self._exchange = exchange
        self._pinger = pinger
        self._message_store = message_store
        self._reactor.call_on("run", self._fetch_ec2_data)
        self._reactor.call_on("pre-exchange", self._handle_pre_exchange)
        self._reactor.call_on("exchange-done", self._handle_exchange_done)
        self._exchange.register_message("set-id", self._handle_set_id)
        self._exchange.register_message("unknown-id", self._handle_unknown_id)
        self._exchange.register_message("registration",
                                        self._handle_registration)
        self._should_register = None
        self._cloud = cloud
        self._fetch_async = fetch_async
        self._otp = None
        self._ec2_data = None

    def should_register(self):
        id = self._identity
        # boolean logic is hard, I'm gonna use an if
        if self._cloud:
            return bool(not id.secure_id
                        and self._message_store.accepts("register-cloud-vm"))
        return bool(not id.secure_id and id.computer_title and id.account_name
                    and self._message_store.accepts("register"))

    def register(self):
        """
        Attempt to register with the Landscape server.

        @return: A L{Deferred} which will either be fired with None if
            registration was successful or will fail with an
            L{InvalidCredentialsError} if not.
        """
        self._identity.secure_id = None
        self._identity.insecure_id = None
        result = RegistrationResponse(self._reactor).deferred
        self._exchange.exchange()
        return result

    @classmethod
    def _extract_ec2_instance_data(cls, raw_user_data, launch_index):
        """
        Given the raw string of EC2 User Data, parse it and return the dict of
        instance data for this particular instance.

        If the data can't be parsed, a debug message will be logged and None
        will be returned.
        """
        try:
            user_data = loads(raw_user_data)
        except ValueError:
            logging.debug("Got invalid user-data %r" % (raw_user_data,))
            return

        if not isinstance(user_data, dict):
            logging.debug("user-data %r is not a dict" % (user_data,))
            return
        for key in "otps", "exchange-url", "ping-url":
            if key not in user_data:
                logging.debug("user-data %r doesn't have key %r."
                              % (user_data, key))
                return
        if len(user_data["otps"]) <= launch_index:
            logging.debug("user-data %r doesn't have OTP for launch index %d"
                          % (user_data, launch_index))
            return
        return {"otp": user_data["otps"][launch_index],
                "exchange-url": user_data["exchange-url"],
                "ping-url": user_data["ping-url"]}

    def _fetch_ec2_data(self):
        id = self._identity
        if self._cloud and not id.secure_id:
            # Fetch data from the EC2 API, to be used later in the registration
            # process
            registration_data = gather_results([
                # We ignore errors from user-data because it's common for the
                # URL to return a 404 when the data is unavailable.
                self._fetch_async(EC2_API + "/user-data")
                    .addErrback(log_failure),
                # The rest of the fetches don't get protected because we just
                # fall back to regular registration if any of them don't work.
                self._fetch_async(EC2_API + "/meta-data/instance-id"),
                self._fetch_async(EC2_API + "/meta-data/reservation-id"),
                self._fetch_async(EC2_API + "/meta-data/local-hostname"),
                self._fetch_async(EC2_API + "/meta-data/public-hostname"),
                self._fetch_async(EC2_API + "/meta-data/ami-launch-index"),
                self._fetch_async(EC2_API + "/meta-data/kernel-id"),
                self._fetch_async(EC2_API + "/meta-data/ramdisk-id"),
                self._fetch_async(EC2_API + "/meta-data/ami-id"),
                ],
                consume_errors=True)

            def record_data(ec2_data):
                """Record the instance data returned by the EC2 API."""
                (raw_user_data, instance_key, reservation_key,
                 local_hostname, public_hostname, launch_index,
                 kernel_key, ramdisk_key, ami_key) = ec2_data
                self._ec2_data = {
                    "instance_key": instance_key,
                    "reservation_key": reservation_key,
                    "local_hostname": local_hostname,
                    "public_hostname": public_hostname,
                    "launch_index": launch_index,
                    "kernel_key": kernel_key,
                    "ramdisk_key": ramdisk_key,
                    "image_key": ami_key}
                for k, v in self._ec2_data.items():
                    self._ec2_data[k] = v.decode("utf-8")
                self._ec2_data["launch_index"] = int(
                    self._ec2_data["launch_index"])

                instance_data = self._extract_ec2_instance_data(
                    raw_user_data, int(launch_index))
                if instance_data is not None:
                    self._otp = instance_data["otp"]
                    exchange_url = instance_data["exchange-url"]
                    ping_url = instance_data["ping-url"]
                    self._exchange._transport.set_url(exchange_url)
                    self._pinger.set_url(ping_url)
                    self._config.url = exchange_url
                    self._config.ping_url = ping_url
                    self._config.write()

            def log_error(error):
                log_failure(error, msg="Got error while fetching meta-data: %r"
                            % (error.value,))

            # It sucks that this deferred is never returned
            registration_data.addCallback(record_data)
            registration_data.addErrback(log_error)

    def _handle_exchange_done(self):
        if self.should_register() and not self._should_register:
            # We received accepted-types (first exchange), so we now trigger
            # the second exchange for registration
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

        if self._should_register:
            id = self._identity

            self._message_store.delete_all_messages()
            if self._cloud and self._ec2_data is not None:
                if self._otp:
                    logging.info("Queueing message to register with OTP")
                    message = {"type": "register-cloud-vm",
                               "otp": self._otp,
                               "hostname": socket.gethostname(),
                               "account_name": None,
                               "registration_password": None,
                               }
                    message.update(self._ec2_data)
                    self._exchange.send(message)
                elif id.account_name:
                    logging.info("Queueing message to register with account "
                                 "%r as an EC2 instance." % (id.account_name,))
                    message = {"type": "register-cloud-vm",
                               "otp": None,
                               "hostname": socket.gethostname(),
                               "account_name": id.account_name,
                               "registration_password": \
                                   id.registration_password}
                    message.update(self._ec2_data)
                    self._exchange.send(message)
                else:
                    self._reactor.fire("registration-failed")
            elif id.account_name:
                with_word = ["without", "with"][bool(id.registration_password)]
                logging.info("Queueing message to register with account %r %s "
                             "a password." % (id.account_name, with_word))

                message = {"type": "register",
                           "computer_title": id.computer_title,
                           "account_name": id.account_name,
                           "registration_password": id.registration_password,
                           "hostname": socket.gethostname()}
                self._exchange.send(message)
            else:
                self._reactor.fire("registration-failed")

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


def is_cloud_managed(fetch=fetch):
    """
    Return C{True} if the machine has been started by Landscape, i.e. if we can
    find the expected data inside the EC2 user-data field.
    """
    try:
        raw_user_data = fetch(EC2_API + "/user-data")
        launch_index = fetch(EC2_API + "/meta-data/ami-launch-index")
    except (pycurl.error, HTTPCodeError):
        return False
    instance_data = RegistrationHandler._extract_ec2_instance_data(
        raw_user_data, int(launch_index))
    return instance_data is not None
