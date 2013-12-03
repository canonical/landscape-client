"""
Handle client registration against the server.

When the service is started for the first time it connects to the server
as a new client without providing any identification credentials, and the
server replies with the available registration mechanisms. At this point
the machinery in this module will notice that we have no identification
credentials yet and that the server accepts registration messages, so it
will craft an appropriate one and send it out.
"""
import time
import logging
import socket

from twisted.internet.defer import Deferred

from landscape.message_schemas import juju_data

from landscape.lib.bpickle import loads
from landscape.lib.log import log_failure
from landscape.lib.juju import get_juju_info
from landscape.lib.fetch import fetch, FetchError
from landscape.lib.tag import is_valid_tag_list
from landscape.lib.network import get_fqdn
from landscape.lib.vm_info import get_vm_info, get_container_info


EC2_HOST = "169.254.169.254"
EC2_API = "http://%s/latest" % (EC2_HOST,)


class InvalidCredentialsError(Exception):
    """
    Raised when an invalid account title and/or registration key
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
        self._reactor.call_on("run", self._fetch_ec2_data)
        self._reactor.call_on("run", self._get_juju_data)
        self._reactor.call_on("pre-exchange", self._handle_pre_exchange)
        self._reactor.call_on("exchange-done", self._handle_exchange_done)
        self._exchange.register_message("set-id", self._handle_set_id)
        self._exchange.register_message("unknown-id", self._handle_unknown_id)
        self._exchange.register_message("registration",
                                        self._handle_registration)
        self._should_register = None
        self._fetch_async = fetch_async
        self._otp = None
        self._ec2_data = None
        self._juju_data = None

    def should_register(self):
        id = self._identity
        if id.secure_id:
            # We already have a secure ID, no need to register
            return False
        if self._config.cloud:
            return self._message_store.accepts("register-cloud-vm")
        elif self._config.provisioning_otp:
            return self._message_store.accepts("register-provisioned-machine")
        return bool(id.computer_title and id.account_name
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

    def _get_juju_data(self):
        """Load Juju information."""
        juju_info = get_juju_info(self._config)
        if juju_info is None:
            return None
        self._juju_data = dict(
            (key, juju_info[key]) for key in juju_data)

    def _get_data(self, path, accumulate):
        """
        Get data at C{path} on the EC2 API endpoint, and add the result to the
        C{accumulate} list.
        """
        return self._fetch_async(EC2_API + path).addCallback(accumulate.append)

    def _fetch_ec2_data(self):
        """Retrieve available EC2 information, if in a EC2 compatible cloud."""
        id = self._identity
        if self._config.cloud and not id.secure_id:
            # Fetch data from the EC2 API, to be used later in the registration
            # process
            # We ignore errors from user-data because it's common for the
            # URL to return a 404 when the data is unavailable.
            ec2_data = []
            deferred = self._fetch_async(EC2_API + "/user-data").addErrback(
                log_failure).addCallback(ec2_data.append)
            paths = [
                "/meta-data/instance-id",
                "/meta-data/reservation-id",
                "/meta-data/local-hostname",
                "/meta-data/public-hostname",
                "/meta-data/ami-launch-index",
                "/meta-data/ami-id",
                "/meta-data/local-ipv4",
                "/meta-data/public-ipv4"]
            # We're not using a DeferredList here because we want to keep the
            # number of connections to the backend minimal. See lp:567515.
            for path in paths:
                deferred.addCallback(
                    lambda ignore, path=path: self._get_data(path, ec2_data))
            # Special case the ramdisk retrieval, because it may not be present
            deferred.addCallback(
                lambda ignore: self._fetch_async(
                    EC2_API + "/meta-data/ramdisk-id").addErrback(log_failure))
            deferred.addCallback(ec2_data.append)
            # And same for kernel
            deferred.addCallback(
                lambda ignore: self._fetch_async(
                    EC2_API + "/meta-data/kernel-id").addErrback(log_failure))
            deferred.addCallback(ec2_data.append)

            def record_data(ignore):
                """Record the instance data returned by the EC2 API."""
                (raw_user_data, instance_key, reservation_key,
                 local_hostname, public_hostname, launch_index,
                 ami_key, local_ip, public_ip, ramdisk_key,
                 kernel_key) = ec2_data
                self._ec2_data = {
                    "instance_key": instance_key,
                    "reservation_key": reservation_key,
                    "local_hostname": local_hostname,
                    "public_hostname": public_hostname,
                    "launch_index": launch_index,
                    "kernel_key": kernel_key,
                    "ramdisk_key": ramdisk_key,
                    "image_key": ami_key,
                    "public_ipv4": public_ip,
                    "local_ipv4": local_ip}
                for k, v in self._ec2_data.items():
                    if v is None and k in ("ramdisk_key", "kernel_key"):
                        continue
                    self._ec2_data[k] = v.decode("utf-8")
                self._ec2_data["launch_index"] = int(
                    self._ec2_data["launch_index"])

                if self._config.otp:
                    self._otp = self._config.otp
                    return
                instance_data = _extract_ec2_instance_data(
                    raw_user_data, int(launch_index))
                if instance_data is not None:
                    self._otp = instance_data["otp"]
                    exchange_url = instance_data["exchange-url"]
                    ping_url = instance_data["ping-url"]
                    self._exchange._transport.set_url(exchange_url)
                    self._config.url = exchange_url
                    self._config.ping_url = ping_url
                    if "ssl-ca-certificate" in instance_data:
                        from landscape.configuration import \
                            store_public_key_data
                        public_key_file = store_public_key_data(
                            self._config, instance_data["ssl-ca-certificate"])
                        self._config.ssl_public_key = public_key_file
                        self._exchange._transport._pubkey = public_key_file
                    self._config.write()

            def log_error(error):
                log_failure(error, msg="Got error while fetching meta-data: %r"
                            % (error.value,))

            deferred.addCallback(record_data)
            deferred.addErrback(log_error)

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

        A computer can fall into several categories:
            - a "cloud VM"
            - a "normal" computer
            - a "provisionned machine".

        Furthermore, Cloud VMs can be registered with either a One Time
        Password (OTP), or with a normal registration password.
        """
        registration_failed = False

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
        tags = identity.tags
        access_group = identity.access_group

        self._message_store.delete_all_messages()

        if not is_valid_tag_list(tags):
            tags = None
            logging.error("Invalid tags provided for cloud registration.")

        message = {"type": None,  # either "register" or "register-cloud-vm"
                   "otp": None,
                   "hostname": get_fqdn(),
                   "account_name": identity.account_name,
                   "registration_password": None,
                   "tags": tags,
                   "vm-info": get_vm_info()}

        if access_group == "":
            access_group = None

        if access_group is not None:
            message["access_group"] = access_group

        if self._config.cloud and self._ec2_data is not None:
            # This is the "cloud VM" case.
            message["type"] = "register-cloud-vm"

            message.update(self._ec2_data)

            if self._otp:
                logging.info("Queueing message to register with OTP")
                message["otp"] = self._otp

            elif account_name:
                with_tags = ["", u"and tags %s " % tags][bool(tags)]
                logging.info(
                    u"Queueing message to register with account %r %s"
                    u"as an EC2 instance." % (account_name, with_tags))
                message["registration_password"] = identity.registration_key

            else:
                registration_failed = True

        elif account_name:
            # The computer is a normal computer, possibly a container.
            with_word = ["without", "with"][bool(identity.registration_key)]
            with_tags = ["", u"and tags %s " % tags][bool(tags)]
            logging.info(u"Queueing message to register with account %r %s"
                         "%s a password." % (account_name, with_tags,
                                             with_word))
            message["type"] = "register"
            message["computer_title"] = identity.computer_title
            message["registration_password"] = identity.registration_key
            message["container-info"] = get_container_info()

            if self._juju_data is not None:
                message["juju-info"] = self._juju_data

        elif self._config.provisioning_otp:
            # This is a newly provisionned machine.
            # In this case message is overwritten because it's much simpler
            logging.info(u"Queueing message to register with OTP as a"
                         u" newly provisioned machine.")
            message = {"type": "register-provisioned-machine",
                       "otp": self._config.provisioning_otp}
        else:
            registration_failed = True

        if registration_failed:
            self._reactor.fire("registration-failed")
        else:
            self._exchange.send(message)

    def _handle_set_id(self, message):
        """Registered handler for the C{"set-id"} event.

        Record and start using the secure and insecure IDs from the given
        message.

        Fire C{"registration-done"} and C{"resynchronize-clients"}.
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

    def _failed(self):
        self.deferred.errback(InvalidCredentialsError())
        self._cancel_calls()


def _extract_ec2_instance_data(raw_user_data, launch_index):
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
    instance_data = {"otp": user_data["otps"][launch_index],
                     "exchange-url": user_data["exchange-url"],
                     "ping-url": user_data["ping-url"]}
    if "ssl-ca-certificate" in user_data:
        instance_data["ssl-ca-certificate"] = user_data["ssl-ca-certificate"]
    return instance_data


def _wait_for_network():
    """
    Keep trying to connect to the EC2 metadata server until it becomes
    accessible or until five minutes pass.

    This is necessary because the networking init script on Ubuntu is
    asynchronous; the network may not actually be up by the time the
    landscape-client init script is invoked.
    """
    timeout = 5 * 60
    port = 80

    start = time.time()
    while True:
        s = socket.socket()
        try:
            s.connect((EC2_HOST, port))
            s.close()
            return
        except socket.error:
            time.sleep(1)
            if time.time() - start > timeout:
                break


def is_cloud_managed(fetch=fetch):
    """
    Return C{True} if the machine has been started by Landscape, i.e. if we can
    find the expected data inside the EC2 user-data field.
    """
    _wait_for_network()
    try:
        raw_user_data = fetch(EC2_API + "/user-data",
                              connect_timeout=5)
        launch_index = fetch(EC2_API + "/meta-data/ami-launch-index",
                             connect_timeout=5)
    except FetchError:
        return False
    instance_data = _extract_ec2_instance_data(
        raw_user_data, int(launch_index))
    return instance_data is not None
