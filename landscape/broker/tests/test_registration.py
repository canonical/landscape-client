import os
import logging
import pycurl
import socket

from twisted.internet.defer import succeed, fail

from landscape.broker.registration import (
    InvalidCredentialsError, RegistrationHandler, is_cloud_managed, EC2_HOST,
    EC2_API, Identity)

from landscape.broker.config import BrokerConfiguration
from landscape.tests.helpers import LandscapeTest, FakeFile
from landscape.broker.tests.helpers import (
    BrokerConfigurationHelper, RegistrationHelper)
from landscape.lib.bpickle import dumps
from landscape.lib.fetch import HTTPCodeError, FetchError
from landscape.lib.persist import Persist
from landscape.configuration import print_text


class IdentityTest(LandscapeTest):

    helpers = [BrokerConfigurationHelper]

    def setUp(self):
        super(IdentityTest, self).setUp()
        self.persist = Persist(filename=self.makePersistFile())
        self.identity = Identity(self.config, self.persist)

    def check_persist_property(self, attr, persist_name):
        value = "VALUE"
        self.assertEqual(getattr(self.identity, attr), None,
                         "%r attribute should default to None, not %r" %
                         (attr, getattr(self.identity, attr)))
        setattr(self.identity, attr, value)
        self.assertEqual(getattr(self.identity, attr), value,
                         "%r attribute should be %r, not %r" %
                         (attr, value, getattr(self.identity, attr)))
        self.assertEqual(
            self.persist.get(persist_name), value,
            "%r not set to %r in persist" % (persist_name, value))

    def check_config_property(self, attr):
        value = "VALUE"
        setattr(self.config, attr, value)
        self.assertEqual(getattr(self.identity, attr), value,
                         "%r attribute should be %r, not %r" %
                         (attr, value, getattr(self.identity, attr)))

    def test_secure_id(self):
        self.check_persist_property("secure_id",
                                    "registration.secure-id")

    def test_insecure_id(self):
        self.check_persist_property("insecure_id",
                                    "registration.insecure-id")

    def test_computer_title(self):
        self.check_config_property("computer_title")

    def test_account_name(self):
        self.check_config_property("account_name")

    def test_registration_password(self):
        self.check_config_property("registration_password")

    def test_client_tags(self):
        self.check_config_property("tags")


class RegistrationHandlerTestBase(LandscapeTest):

    helpers = [RegistrationHelper]

    def setUp(self):
        super(RegistrationHandlerTestBase, self).setUp()
        logging.getLogger().setLevel(logging.INFO)
        self.hostname = "ooga.local"
        self.addCleanup(setattr, socket, "getfqdn", socket.getfqdn)
        socket.getfqdn = lambda: self.hostname


class RegistrationHandlerTest(RegistrationHandlerTestBase):

    def test_server_initiated_id_changing(self):
        """
        The server must be able to ask a client to change its secure
        and insecure ids even if no requests were sent.
        """
        self.exchanger.handle_message(
            {"type": "set-id", "id": "abc", "insecure-id": "def"})
        self.assertEqual(self.identity.secure_id, "abc")
        self.assertEqual(self.identity.insecure_id, "def")

    def test_registration_done_event(self):
        """
        When new ids are received from the server, a "registration-done"
        event is fired.
        """
        reactor_mock = self.mocker.patch(self.reactor)
        reactor_mock.fire("registration-done")
        self.mocker.replay()
        self.exchanger.handle_message(
            {"type": "set-id", "id": "abc", "insecure-id": "def"})

    def test_unknown_id(self):
        self.identity.secure_id = "old_id"
        self.identity.insecure_id = "old_id"
        self.mstore.set_accepted_types(["register"])
        self.exchanger.handle_message({"type": "unknown-id"})
        self.assertEqual(self.identity.secure_id, None)
        self.assertEqual(self.identity.insecure_id, None)

    def test_should_register(self):
        self.mstore.set_accepted_types(["register"])
        self.config.computer_title = "Computer Title"
        self.config.account_name = "account_name"
        self.assertTrue(self.handler.should_register())

    def test_should_register_with_existing_id(self):
        self.mstore.set_accepted_types(["register"])
        self.identity.secure_id = "secure"
        self.config.computer_title = "Computer Title"
        self.config.account_name = "account_name"
        self.assertFalse(self.handler.should_register())

    def test_should_register_without_computer_title(self):
        self.mstore.set_accepted_types(["register"])
        self.config.computer_title = None
        self.assertFalse(self.handler.should_register())

    def test_should_register_without_account_name(self):
        self.mstore.set_accepted_types(["register"])
        self.config.account_name = None
        self.assertFalse(self.handler.should_register())

    def test_should_register_with_unaccepted_message(self):
        self.assertFalse(self.handler.should_register())

    def test_queue_message_on_exchange(self):
        """
        When a computer_title and account_name are available, no
        secure_id is set, and an exchange is about to happen,
        queue a registration message.
        """
        self.mstore.set_accepted_types(["register"])
        self.config.computer_title = "Computer Title"
        self.config.account_name = "account_name"
        self.reactor.fire("pre-exchange")
        self.assertMessages(self.mstore.get_pending_messages(),
                            [{"type": "register",
                              "computer_title": "Computer Title",
                              "account_name": "account_name",
                              "registration_password": None,
                              "hostname": "ooga.local",
                              "tags": None}])
        self.assertEqual(self.logfile.getvalue().strip(),
                         "INFO: Queueing message to register with account "
                         "'account_name' without a password.")

    def test_queue_message_on_exchange_with_password(self):
        """If a registration password is available, we pass it on!"""
        self.mstore.set_accepted_types(["register"])
        self.config.computer_title = "Computer Title"
        self.config.account_name = "account_name"
        self.config.registration_password = "SEKRET"
        self.reactor.fire("pre-exchange")
        self.assertMessages(self.mstore.get_pending_messages(),
                            [{"type": "register",
                              "computer_title": "Computer Title",
                              "account_name": "account_name",
                              "registration_password": "SEKRET",
                              "hostname": "ooga.local",
                              "tags": None}])
        self.assertEqual(self.logfile.getvalue().strip(),
                         "INFO: Queueing message to register with account "
                         "'account_name' with a password.")

    def test_queue_message_on_exchange_with_tags(self):
        """
        If the admin has defined tags for this computer, we send them to the
        server.
        """
        self.mstore.set_accepted_types(["register"])
        self.config.computer_title = "Computer Title"
        self.config.account_name = "account_name"
        self.config.registration_password = "SEKRET"
        self.config.tags = u"computer,tag"
        self.reactor.fire("pre-exchange")
        self.assertMessages(self.mstore.get_pending_messages(),
                            [{"type": "register",
                              "computer_title": "Computer Title",
                              "account_name": "account_name",
                              "registration_password": "SEKRET",
                              "hostname": "ooga.local",
                              "tags": u"computer,tag"}])
        self.assertEqual(self.logfile.getvalue().strip(),
                         "INFO: Queueing message to register with account "
                         "'account_name' and tags computer,tag "
                         "with a password.")

    def test_queue_message_on_exchange_with_invalid_tags(self):
        """
        If the admin has defined tags for this computer, but they are not
        valid, we drop them, and report an error.
        """
        self.log_helper.ignore_errors("Invalid tags provided for cloud "
                                      "registration")
        self.mstore.set_accepted_types(["register"])
        self.config.computer_title = "Computer Title"
        self.config.account_name = "account_name"
        self.config.registration_password = "SEKRET"
        self.config.tags = u"<script>alert()</script>"
        self.reactor.fire("pre-exchange")
        self.assertMessages(self.mstore.get_pending_messages(),
                            [{"type": "register",
                              "computer_title": "Computer Title",
                              "account_name": "account_name",
                              "registration_password": "SEKRET",
                              "hostname": "ooga.local",
                              "tags": None}])
        self.assertEqual(self.logfile.getvalue().strip(),
                         "ERROR: Invalid tags provided for cloud "
                         "registration.\n    "
                         "INFO: Queueing message to register with account "
                         "'account_name' with a password.")

    def test_queue_message_on_exchange_with_unicode_tags(self):
        """
        If the admin has defined tags for this computer, we send them to the
        server.
        """
        self.mstore.set_accepted_types(["register"])
        self.config.computer_title = "Computer Title"
        self.config.account_name = "account_name"
        self.config.registration_password = "SEKRET"
        self.config.tags = u"prova\N{LATIN SMALL LETTER J WITH CIRCUMFLEX}o"
        self.reactor.fire("pre-exchange")
        self.assertMessages(
            self.mstore.get_pending_messages(),
            [{"type": "register",
              "computer_title": "Computer Title",
              "account_name": "account_name",
              "registration_password": "SEKRET",
              "hostname": "ooga.local",
              "tags": u"prova\N{LATIN SMALL LETTER J WITH CIRCUMFLEX}o"}])
        self.assertEqual(self.logfile.getvalue().strip(),
                         "INFO: Queueing message to register with account "
                         "'account_name' and tags prova\xc4\xb5o "
                         "with a password.")

    def test_queueing_registration_message_resets_message_store(self):
        """
        When a registration message is queued, the store is reset
        entirely, since everything else that was queued is meaningless
        now that we're trying to register again.
        """
        self.mstore.set_accepted_types(["register", "test"])
        self.mstore.add({"type": "test"})
        self.config.computer_title = "Computer Title"
        self.config.account_name = "account_name"
        self.reactor.fire("pre-exchange")
        messages = self.mstore.get_pending_messages()
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0]["type"], "register")

    def test_no_message_when_should_register_is_false(self):
        """If we already have a secure id, do not queue a register message.
        """
        handler_mock = self.mocker.patch(self.handler)
        handler_mock.should_register()
        self.mocker.result(False)

        self.mstore.set_accepted_types(["register"])
        self.config.computer_title = "Computer Title"
        self.config.account_name = "account_name"

        # If we didn't fake it, it'd work.  We do that to ensure that
        # all the needed data is in place, and that this method is
        # really what decides if a message is sent or not.  This way
        # we can test it individually.
        self.assertTrue(self.handler.should_register())

        # Now let's see.
        self.mocker.replay()

        self.reactor.fire("pre-exchange")
        self.assertMessages(self.mstore.get_pending_messages(), [])

    def test_registration_failed_event(self):
        """
        The deferred returned by a registration request should fail
        with L{InvalidCredentialsError} if the server responds with a
        failure message.
        """
        reactor_mock = self.mocker.patch(self.reactor)
        reactor_mock.fire("registration-failed")
        self.mocker.replay()
        self.exchanger.handle_message(
            {"type": "registration", "info": "unknown-account"})

    def test_registration_failed_event_not_fired_when_uncertain(self):
        """
        If the data in the registration message isn't what we expect,
        the event isn't fired.
        """
        reactor_mock = self.mocker.patch(self.reactor)
        reactor_mock.fire("registration-failed")
        self.mocker.count(0)
        self.mocker.replay()
        self.exchanger.handle_message(
            {"type": "registration", "info": "blah-blah"})

    def test_register_resets_ids(self):
        self.identity.secure_id = "foo"
        self.identity.insecure_id = "bar"
        self.handler.register()
        self.assertEqual(self.identity.secure_id, None)
        self.assertEqual(self.identity.insecure_id, None)

    def test_register_calls_urgent_exchange(self):
        exchanger_mock = self.mocker.patch(self.exchanger)
        exchanger_mock.exchange()
        self.mocker.passthrough()
        self.mocker.replay()
        self.handler.register()

    def test_register_deferred_called_on_done(self):
        # We don't want informational messages.
        self.logger.setLevel(logging.WARNING)

        calls = [0]
        d = self.handler.register()

        def add_call(result):
            self.assertEqual(result, None)
            calls[0] += 1

        d.addCallback(add_call)

        # This should somehow callback the deferred.
        self.exchanger.handle_message(
            {"type": "set-id", "id": "abc", "insecure-id": "def"})

        self.assertEqual(calls, [1])

        # Doing it again to ensure that the deferred isn't called twice.
        self.exchanger.handle_message(
            {"type": "set-id", "id": "abc", "insecure-id": "def"})

        self.assertEqual(calls, [1])

        self.assertEqual(self.logfile.getvalue(), "")

    def test_resynchronize_fired_when_registration_done(self):

        results = []

        def append():
            results.append(True)

        self.reactor.call_on("resynchronize-clients", append)

        self.handler.register()

        # This should somehow callback the deferred.
        self.exchanger.handle_message(
            {"type": "set-id", "id": "abc", "insecure-id": "def"})

        self.assertEqual(results, [True])

    def test_register_deferred_called_on_failed(self):
        # We don't want informational messages.
        self.logger.setLevel(logging.WARNING)

        calls = [0]
        d = self.handler.register()

        def add_call(failure):
            exception = failure.value
            self.assertTrue(isinstance(exception, InvalidCredentialsError))
            calls[0] += 1

        d.addErrback(add_call)

        # This should somehow callback the deferred.
        self.exchanger.handle_message(
            {"type": "registration", "info": "unknown-account"})

        self.assertEqual(calls, [1])

        # Doing it again to ensure that the deferred isn't called twice.
        self.exchanger.handle_message(
            {"type": "registration", "info": "unknown-account"})

        self.assertEqual(calls, [1])

        self.assertEqual(self.logfile.getvalue(), "")

    def test_exchange_done_calls_exchange(self):
        exchanger_mock = self.mocker.patch(self.exchanger)
        exchanger_mock.exchange()
        self.mocker.passthrough()
        self.mocker.replay()

        self.mstore.set_accepted_types(["register"])
        self.config.computer_title = "Computer Title"
        self.config.account_name = "account_name"
        self.reactor.fire("exchange-done")

    def test_exchange_done_wont_call_exchange_when_just_tried(self):
        exchanger_mock = self.mocker.patch(self.exchanger)
        exchanger_mock.exchange()
        self.mocker.count(0)
        self.mocker.replay()

        self.mstore.set_accepted_types(["register"])
        self.config.computer_title = "Computer Title"
        self.config.account_name = "account_name"
        self.reactor.fire("pre-exchange")
        self.reactor.fire("exchange-done")

    def test_default_hostname(self):
        self.mstore.set_accepted_types(["register"])
        self.config.computer_title = "Computer Title"
        self.config.account_name = "account_name"
        self.config.registration_password = "SEKRET"
        self.reactor.fire("pre-exchange")
        self.assertMessages(self.mstore.get_pending_messages(),
                            [{"type": "register",
                              "computer_title": "Computer Title",
                              "account_name": "account_name",
                              "registration_password": "SEKRET",
                              "hostname": socket.getfqdn(),
                              "tags": None}])


class CloudRegistrationHandlerTest(RegistrationHandlerTestBase):

    cloud = True

    def setUp(self):
        super(CloudRegistrationHandlerTest, self).setUp()
        self.query_results = {}

        def fetch_stub(url):
            value = self.query_results[url]
            if isinstance(value, Exception):
                return fail(value)
            else:
                return succeed(value)

        self.fetch_func = fetch_stub

    def get_user_data(self, otps=None,
                      exchange_url="https://example.com/message-system",
                      ping_url="http://example.com/ping",
                      ssl_ca_certificate=None):
        if otps is None:
            otps = ["otp1"]
        user_data = {"otps": otps, "exchange-url": exchange_url,
                     "ping-url": ping_url}
        if ssl_ca_certificate is not None:
            user_data["ssl-ca-certificate"] = ssl_ca_certificate
        return user_data

    def prepare_query_results(
        self, user_data=None, instance_key="key1", launch_index=0,
        local_hostname="ooga.local", public_hostname="ooga.amazon.com",
        reservation_key=u"res1", ramdisk_key=u"ram1", kernel_key=u"kernel1",
        image_key=u"image1", ssl_ca_certificate=None):
        if user_data is None:
            user_data = self.get_user_data(
                ssl_ca_certificate=ssl_ca_certificate)
        if not isinstance(user_data, Exception):
            user_data = dumps(user_data)
        api_base = "http://169.254.169.254/latest"
        self.query_results.clear()
        for url_suffix, value in [
            ("/user-data", user_data),
            ("/meta-data/instance-id", instance_key),
            ("/meta-data/reservation-id", reservation_key),
            ("/meta-data/local-hostname", local_hostname),
            ("/meta-data/public-hostname", public_hostname),
            ("/meta-data/ami-launch-index", str(launch_index)),
            ("/meta-data/kernel-id", kernel_key),
            ("/meta-data/ramdisk-id", ramdisk_key),
            ("/meta-data/ami-id", image_key),
            ]:
            self.query_results[api_base + url_suffix] = value

    def prepare_cloud_registration(self, account_name=None,
                                   registration_password=None, tags=None):
        # Set things up so that the client thinks it should register
        self.mstore.set_accepted_types(list(self.mstore.get_accepted_types())
                                       + ["register-cloud-vm"])
        self.config.account_name = account_name
        self.config.registration_password = registration_password
        self.config.computer_title = None
        self.config.tags = tags
        self.identity.secure_id = None
        self.assertTrue(self.handler.should_register())

    def get_expected_cloud_message(self, **kwargs):
        """
        Return the message which is expected from a similar call to
        L{get_registration_handler_for_cloud}.
        """
        message = dict(type="register-cloud-vm",
                       otp="otp1",
                       hostname="ooga.local",
                       local_hostname="ooga.local",
                       public_hostname="ooga.amazon.com",
                       instance_key=u"key1",
                       reservation_key=u"res1",
                       ramdisk_key=u"ram1",
                       kernel_key=u"kernel1",
                       launch_index=0,
                       image_key=u"image1",
                       account_name=None,
                       registration_password=None,
                       tags=None)
        message.update(kwargs)
        return message

    def test_cloud_registration(self):
        """
        When the 'cloud' configuration variable is set, cloud registration is
        done instead of normal password-based registration. This means:

        - "Launch Data" is fetched from the EC2 Launch Data URL. This contains
          a one-time password that is used during registration.
        - A different "register-cloud-vm" message is sent to the server instead
          of "register", containing the OTP. This message is handled by
          immediately accepting the computer, instead of going through the
          pending computer stage.
        """
        self.prepare_query_results()

        self.prepare_cloud_registration(tags=u"server,london")

        # metadata is fetched and stored at reactor startup:
        self.reactor.fire("run")

        # And the metadata returned determines the URLs that are used
        self.assertEqual(self.transport.get_url(),
                         "https://example.com/message-system")
        self.assertEqual(self.pinger.get_url(),
                         "http://example.com/ping")
        # Lets make sure those values were written back to the config file
        new_config = BrokerConfiguration()
        new_config.load_configuration_file(self.config_filename)
        self.assertEqual(new_config.url, "https://example.com/message-system")
        self.assertEqual(new_config.ping_url, "http://example.com/ping")

        # Okay! Exchange should cause the registration to happen.
        self.exchanger.exchange()
        # This *should* be asynchronous, but I think a billion tests are
        # written like this
        self.assertEqual(len(self.transport.payloads), 1)
        self.assertMessages(
            self.transport.payloads[0]["messages"],
            [self.get_expected_cloud_message(tags=u"server,london")])

    def test_cloud_registration_with_invalid_tags(self):
        """
        Invalid tags in the configuration should result in the tags not being
        sent to the server, and this fact logged.
        """
        self.log_helper.ignore_errors("Invalid tags provided for cloud "
                                      "registration")
        self.prepare_query_results()
        self.prepare_cloud_registration(tags=u"<script>alert()</script>,hardy")

        # metadata is fetched and stored at reactor startup:
        self.reactor.fire("run")
        self.exchanger.exchange()
        self.assertEqual(len(self.transport.payloads), 1)
        self.assertMessages(self.transport.payloads[0]["messages"],
                            [self.get_expected_cloud_message(tags=None)])
        self.assertEqual(self.logfile.getvalue().strip(),
                         "ERROR: Invalid tags provided for cloud "
                         "registration.\n    "
                         "INFO: Queueing message to register with OTP\n    "
                         "INFO: Starting message exchange with "
                         "https://example.com/message-system.\n    "
                         "INFO: Message exchange completed in 0.00s.")

    def test_cloud_registration_with_ssl_ca_certificate(self):
        """
        If we have an SSL certificate CA included in the user-data, this should
        be written out, and the configuration updated to reflect this.
        """
        key_filename = os.path.join(self.config.data_path,
            "%s.ssl_public_key" % os.path.basename(self.config_filename))

        print_text_mock = self.mocker.replace(print_text)
        print_text_mock("Writing SSL CA certificate to %s..." %
                        key_filename)
        self.mocker.replay()
        self.prepare_query_results(ssl_ca_certificate=u"1234567890")
        self.prepare_cloud_registration(tags=u"server,london")
        # metadata is fetched and stored at reactor startup:
        self.reactor.fire("run")
        # And the metadata returned determines the URLs that are used
        self.assertEqual("https://example.com/message-system",
                         self.transport.get_url())
        self.assertEqual(key_filename, self.transport.pubkey)
        self.assertEqual("http://example.com/ping",
                         self.pinger.get_url())
        # Let's make sure those values were written back to the config file
        new_config = BrokerConfiguration()
        new_config.load_configuration_file(self.config_filename)
        self.assertEqual("https://example.com/message-system", new_config.url)
        self.assertEqual("http://example.com/ping", new_config.ping_url)
        self.assertEqual(key_filename, new_config.ssl_public_key)
        self.assertEqual("1234567890", open(key_filename, "r").read())

    def test_wrong_user_data(self):
        self.prepare_query_results(user_data="other stuff, not a bpickle")
        self.prepare_cloud_registration()

        # Mock registration-failed call
        reactor_mock = self.mocker.patch(self.reactor)
        reactor_mock.fire("registration-failed")
        self.mocker.replay()

        self.reactor.fire("run")
        self.exchanger.exchange()

    def test_wrong_object_type_in_user_data(self):
        self.prepare_query_results(user_data=True)
        self.prepare_cloud_registration()

        # Mock registration-failed call
        reactor_mock = self.mocker.patch(self.reactor)
        reactor_mock.fire("registration-failed")
        self.mocker.replay()

        self.reactor.fire("run")
        self.exchanger.exchange()

    def test_user_data_with_not_enough_elements(self):
        """
        If the AMI launch index isn't represented in the list of OTPs in the
        user data then BOOM.
        """
        self.prepare_query_results(launch_index=1)
        self.prepare_cloud_registration()

        # Mock registration-failed call
        reactor_mock = self.mocker.patch(self.reactor)
        reactor_mock.fire("registration-failed")
        self.mocker.replay()

        self.reactor.fire("run")
        self.exchanger.exchange()

    def test_user_data_bpickle_without_otp(self):
        self.prepare_query_results(user_data={"foo": "bar"})
        self.prepare_cloud_registration()

        # Mock registration-failed call
        reactor_mock = self.mocker.patch(self.reactor)
        reactor_mock.fire("registration-failed")
        self.mocker.replay()

        self.reactor.fire("run")
        self.exchanger.exchange()

    def test_no_otp_fallback_to_account(self):
        self.prepare_query_results(user_data="other stuff, not a bpickle",
                                   instance_key=u"key1")
        self.prepare_cloud_registration(account_name=u"onward",
                                        registration_password=u"password",
                                        tags=u"london,server")

        self.reactor.fire("run")
        self.exchanger.exchange()

        self.assertEqual(len(self.transport.payloads), 1)
        self.assertMessages(self.transport.payloads[0]["messages"],
                            [self.get_expected_cloud_message(
                                otp=None,
                                account_name=u"onward",
                                registration_password=u"password",
                                tags=u"london,server")])
        self.assertEqual(self.logfile.getvalue().strip(),
           "INFO: Queueing message to register with account u'onward' and "
           "tags london,server as an EC2 instance.\n    "
           "INFO: Starting message exchange with http://localhost:91919.\n    "
           "INFO: Message exchange completed in 0.00s.")

    def test_queueing_cloud_registration_message_resets_message_store(self):
        """
        When a registration from a cloud is about to happen, the message store
        is reset, because all previous messages are now meaningless.
        """
        self.mstore.set_accepted_types(list(self.mstore.get_accepted_types())
                                       + ["test"])

        self.mstore.add({"type": "test"})

        self.prepare_query_results()

        self.prepare_cloud_registration()

        self.reactor.fire("run")
        self.reactor.fire("pre-exchange")

        messages = self.mstore.get_pending_messages()
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0]["type"], "register-cloud-vm")

    def test_cloud_registration_fetch_errors(self):
        """
        If fetching metadata fails, and we have no account details to fall
        back to, we fire 'registration-failed'.
        """
        self.log_helper.ignore_errors(pycurl.error)

        def fetch_stub(url):
            return fail(pycurl.error(7, "couldn't connect to host"))

        self.handler = RegistrationHandler(
            self.config, self.identity, self.reactor, self.exchanger,
            self.pinger, self.mstore, fetch_async=fetch_stub)

        self.fetch_stub = fetch_stub
        self.prepare_query_results()
        self.fetch_stub = fetch_stub

        self.prepare_cloud_registration()

        failed = []
        self.reactor.call_on(
            "registration-failed", lambda: failed.append(True))

        self.log_helper.ignore_errors("Got error while fetching meta-data")
        self.reactor.fire("run")
        self.exchanger.exchange()
        self.assertEqual(failed, [True])
        self.assertIn('error: (7, "couldn\'t connect to host")',
                      self.logfile.getvalue())

    def test_cloud_registration_continues_without_user_data(self):
        """
        If no user-data exists (i.e., the user-data URL returns a 404), then
        register-cloud-vm still occurs.
        """
        self.log_helper.ignore_errors(HTTPCodeError)
        self.prepare_query_results(user_data=HTTPCodeError(404, "ohno"))
        self.prepare_cloud_registration(account_name="onward",
                                        registration_password="password")

        self.reactor.fire("run")
        self.exchanger.exchange()
        self.assertIn("HTTPCodeError: Server returned HTTP code 404",
                      self.logfile.getvalue())
        self.assertEqual(len(self.transport.payloads), 1)
        self.assertMessages(self.transport.payloads[0]["messages"],
                            [self.get_expected_cloud_message(
                                otp=None,
                                account_name=u"onward",
                                registration_password=u"password")])

    def test_cloud_registration_continues_without_ramdisk(self):
        """
        If the instance doesn't have a ramdisk (ie, the query for ramdisk
        returns a 404), then register-cloud-vm still occurs.
        """
        self.log_helper.ignore_errors(HTTPCodeError)
        self.prepare_query_results(ramdisk_key=HTTPCodeError(404, "ohno"))
        self.prepare_cloud_registration()

        self.reactor.fire("run")
        self.exchanger.exchange()
        self.assertIn("HTTPCodeError: Server returned HTTP code 404",
                      self.logfile.getvalue())
        self.assertEqual(len(self.transport.payloads), 1)
        self.assertMessages(self.transport.payloads[0]["messages"],
                            [self.get_expected_cloud_message(
                                ramdisk_key=None)])

    def test_fall_back_to_normal_registration_when_metadata_fetch_fails(self):
        """
        If fetching metadata fails, but we do have an account name, then we
        fall back to normal 'register' registration.
        """
        self.mstore.set_accepted_types(["register"])
        self.log_helper.ignore_errors(HTTPCodeError)
        self.prepare_query_results(
            public_hostname=HTTPCodeError(404, "ohnoes"))
        self.prepare_cloud_registration(account_name="onward",
                                        registration_password="password")
        self.config.computer_title = "whatever"
        self.reactor.fire("run")
        self.exchanger.exchange()
        self.assertIn("HTTPCodeError: Server returned HTTP code 404",
                      self.logfile.getvalue())
        self.assertEqual(len(self.transport.payloads), 1)
        self.assertMessages(self.transport.payloads[0]["messages"],
                            [{"type": "register",
                              "computer_title": u"whatever",
                              "account_name": u"onward",
                              "registration_password": u"password",
                              "hostname": socket.getfqdn(),
                              "tags": None}])

    def test_should_register_in_cloud(self):
        """
        The client should register when it's in the cloud even though
        it doesn't have the normal account details.
        """
        self.mstore.set_accepted_types(self.mstore.get_accepted_types()
                                       + ("register-cloud-vm",))
        self.config.account_name = None
        self.config.registration_password = None
        self.config.computer_title = None
        self.identity.secure_id = None
        self.assertTrue(self.handler.should_register())

    def test_launch_index(self):
        """
        The client used the value in C{ami-launch-index} to choose the
        appropriate OTP in the user data.
        """
        otp = "correct otp for launch index"
        self.prepare_query_results(
            user_data=self.get_user_data(otps=["wrong index", otp,
                                               "wrong again"],),
            instance_key="key1",
            launch_index=1)

        self.prepare_cloud_registration()

        self.reactor.fire("run")
        self.exchanger.exchange()
        self.assertEqual(len(self.transport.payloads), 1)
        self.assertMessages(self.transport.payloads[0]["messages"],
                            [self.get_expected_cloud_message(otp=otp,
                                                             launch_index=1)])

    def test_should_not_register_in_cloud(self):
        """
        Having a secure ID means we shouldn't register, even in the cloud.
        """
        self.mstore.set_accepted_types(self.mstore.get_accepted_types()
                                       + ("register-cloud-vm",))
        self.config.account_name = None
        self.config.registration_password = None
        self.config.computer_title = None
        self.identity.secure_id = "hello"
        self.assertFalse(self.handler.should_register())

    def test_should_not_register_without_register_cloud_vm(self):
        """
        If the server isn't accepting a 'register-cloud-vm' message,
        we shouldn't register.
        """
        self.config.account_name = None
        self.config.registration_password = None
        self.config.computer_title = None
        self.identity.secure_id = None
        self.assertFalse(self.handler.should_register())


class IsCloudManagedTests(LandscapeTest):

    def setUp(self):
        super(IsCloudManagedTests, self).setUp()
        self.urls = []
        self.responses = []

    def fake_fetch(self, url, connect_timeout=None):
        self.urls.append((url, connect_timeout))
        return self.responses.pop(0)

    def mock_socket(self):
        """
        Mock out socket usage by is_cloud_managed to wait for the network.
        """
        # Mock the socket.connect call that it also does
        socket_class = self.mocker.replace("socket.socket", passthrough=False)
        socket = socket_class()
        socket.connect((EC2_HOST, 80))
        socket.close()

    def test_is_managed(self):
        """
        L{is_cloud_managed} returns True if the EC2 user-data contains
        Landscape instance information.  It fetches the EC2 data with low
        timeouts.
        """
        user_data = {"otps": ["otp1"], "exchange-url": "http://exchange",
                     "ping-url": "http://ping"}
        self.responses = [dumps(user_data), "0"]

        self.mock_socket()
        self.mocker.replay()

        self.assertTrue(is_cloud_managed(self.fake_fetch))
        self.assertEqual(
            self.urls,
            [(EC2_API + "/user-data", 5),
             (EC2_API + "/meta-data/ami-launch-index", 5)])

    def test_is_managed_index(self):
        user_data = {"otps": ["otp1", "otp2"],
                     "exchange-url": "http://exchange",
                     "ping-url": "http://ping"}
        self.responses = [dumps(user_data), "1"]
        self.mock_socket()
        self.mocker.replay()
        self.assertTrue(is_cloud_managed(self.fake_fetch))

    def test_is_managed_wrong_index(self):
        user_data = {"otps": ["otp1"], "exchange-url": "http://exchange",
                     "ping-url": "http://ping"}
        self.responses = [dumps(user_data), "1"]
        self.mock_socket()
        self.mocker.replay()
        self.assertFalse(is_cloud_managed(self.fake_fetch))

    def test_is_managed_exchange_url(self):
        user_data = {"otps": ["otp1"], "ping-url": "http://ping"}
        self.responses = [dumps(user_data), "0"]
        self.mock_socket()
        self.mocker.replay()
        self.assertFalse(is_cloud_managed(self.fake_fetch))

    def test_is_managed_ping_url(self):
        user_data = {"otps": ["otp1"], "exchange-url": "http://exchange"}
        self.responses = [dumps(user_data), "0"]
        self.mock_socket()
        self.mocker.replay()
        self.assertFalse(is_cloud_managed(self.fake_fetch))

    def test_is_managed_bpickle(self):
        self.responses = ["some other user data", "0"]
        self.mock_socket()
        self.mocker.replay()
        self.assertFalse(is_cloud_managed(self.fake_fetch))

    def test_is_managed_no_data(self):
        self.responses = ["", "0"]
        self.mock_socket()
        self.mocker.replay()
        self.assertFalse(is_cloud_managed(self.fake_fetch))

    def test_is_managed_fetch_not_found(self):

        def fake_fetch(url, connect_timeout=None):
            raise HTTPCodeError(404, "ohnoes")

        self.mock_socket()
        self.mocker.replay()
        self.assertFalse(is_cloud_managed(fake_fetch))

    def test_is_managed_fetch_error(self):

        def fake_fetch(url, connect_timeout=None):
            raise FetchError(7, "couldn't connect to host")

        self.mock_socket()
        self.mocker.replay()
        self.assertFalse(is_cloud_managed(fake_fetch))

    def test_waits_for_network(self):
        """
        is_cloud_managed will wait until the network before trying to fetch
        the EC2 user data.
        """
        user_data = {"otps": ["otp1"], "exchange-url": "http://exchange",
                     "ping-url": "http://ping"}
        self.responses = [dumps(user_data), "0"]

        self.mocker.order()
        time_sleep = self.mocker.replace("time.sleep", passthrough=False)
        socket_class = self.mocker.replace("socket.socket", passthrough=False)
        socket_obj = socket_class()
        socket_obj.connect((EC2_HOST, 80))
        self.mocker.throw(socket.error("woops"))
        time_sleep(1)
        socket_obj = socket_class()
        socket_obj.connect((EC2_HOST, 80))
        self.mocker.result(None)
        socket_obj.close()
        self.mocker.replay()
        self.assertTrue(is_cloud_managed(self.fake_fetch))

    def test_waiting_times_out(self):
        """
        We'll only wait five minutes for the network to come up.
        """

        def fake_fetch(url, connect_timeout=None):
            raise FetchError(7, "couldn't connect to host")

        self.mocker.order()
        time_sleep = self.mocker.replace("time.sleep", passthrough=False)
        time_time = self.mocker.replace("time.time", passthrough=False)
        time_time()
        self.mocker.result(100)
        socket_class = self.mocker.replace("socket.socket", passthrough=False)
        socket_obj = socket_class()
        socket_obj.connect((EC2_HOST, 80))
        self.mocker.throw(socket.error("woops"))
        time_sleep(1)
        time_time()
        self.mocker.result(401)
        self.mocker.replay()
        # Mocking time.time is dangerous, because the test harness calls it. So
        # we explicitly reset mocker before returning from the test.
        try:
            self.assertFalse(is_cloud_managed(fake_fetch))
        finally:
            self.mocker.reset()
