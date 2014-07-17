import json
import logging
import socket

from landscape.broker.registration import (
    InvalidCredentialsError, Identity)

from landscape.tests.helpers import LandscapeTest
from landscape.broker.tests.helpers import (
    BrokerConfigurationHelper, RegistrationHelper)
from landscape.lib.persist import Persist
from landscape.lib.vm_info import get_vm_info


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

    def test_registration_key(self):
        self.check_config_property("registration_key")

    def test_client_tags(self):
        self.check_config_property("tags")

    def test_access_group(self):
        self.check_config_property("access_group")


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

    def test_unknown_id_with_clone(self):
        """
        If the server reports us that we are a clone of another computer, then
        set our computer's title accordingly.
        """
        self.config.computer_title = "Wu"
        self.mstore.set_accepted_types(["register"])
        self.exchanger.handle_message({"type": "unknown-id", "clone-of": "Wu"})
        self.assertEqual("Wu (clone)", self.config.computer_title)
        self.assertIn("Client is clone of computer Wu",
                      self.logfile.getvalue())

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
        messages = self.mstore.get_pending_messages()
        self.assertEqual(1, len(messages))
        self.assertEqual("register", messages[0]["type"])
        self.assertEqual(self.logfile.getvalue().strip(),
                         "INFO: Queueing message to register with account "
                         "'account_name' without a password.\n    "
                         "INFO: Sending registration message to exchange.")

    def test_queue_message_on_exchange_with_vm_info(self):
        """
        When a computer_title and account_name are available, no
        secure_id is set, and an exchange is about to happen,
        queue a registration message with VM information.
        """
        get_vm_info_mock = self.mocker.replace(get_vm_info)
        get_vm_info_mock()
        self.mocker.result("vmware")
        self.mocker.replay()
        self.mstore.set_accepted_types(["register"])
        self.config.computer_title = "Computer Title"
        self.config.account_name = "account_name"
        self.reactor.fire("pre-exchange")
        messages = self.mstore.get_pending_messages()
        self.assertEqual("vmware", messages[0]["vm-info"])
        self.assertEqual(self.logfile.getvalue().strip(),
                         "INFO: Queueing message to register with account "
                         "'account_name' without a password.\n    "
                         "INFO: Sending registration message to exchange.")

    def test_queue_message_on_exchange_with_lxc_container(self):
        """
        If the client is running in an LXC container, the information is
        included in the registration message.
        """
        get_container_info_mock = self.mocker.replace(
            "landscape.lib.vm_info.get_container_info")
        get_container_info_mock()
        self.mocker.result("lxc")
        self.mocker.replay()
        self.mstore.set_accepted_types(["register"])
        self.config.computer_title = "Computer Title"
        self.config.account_name = "account_name"
        self.reactor.fire("pre-exchange")
        messages = self.mstore.get_pending_messages()
        self.assertEqual("lxc", messages[0]["container-info"])

    def test_queue_message_on_exchange_with_password(self):
        """If a registration password is available, we pass it on!"""
        self.mstore.set_accepted_types(["register"])
        self.config.computer_title = "Computer Title"
        self.config.account_name = "account_name"
        self.config.registration_key = "SEKRET"
        self.reactor.fire("pre-exchange")
        messages = self.mstore.get_pending_messages()
        password = messages[0]["registration_password"]
        self.assertEqual("SEKRET", password)
        self.assertEqual(self.logfile.getvalue().strip(),
                         "INFO: Queueing message to register with account "
                         "'account_name' with a password.\n    "
                         "INFO: Sending registration message to exchange.")

    def test_queue_message_on_exchange_with_tags(self):
        """
        If the admin has defined tags for this computer, we send them to the
        server.
        """
        self.mstore.set_accepted_types(["register"])
        self.config.computer_title = "Computer Title"
        self.config.account_name = "account_name"
        self.config.registration_key = "SEKRET"
        self.config.tags = u"computer,tag"
        self.reactor.fire("pre-exchange")
        messages = self.mstore.get_pending_messages()
        self.assertEqual("computer,tag", messages[0]["tags"])
        self.assertEqual(self.logfile.getvalue().strip(),
                         "INFO: Queueing message to register with account "
                         "'account_name' and tags computer,tag with a "
                         "password.\n    "
                         "INFO: Sending registration message to exchange.")

    def test_queue_message_on_exchange_with_invalid_tags(self):
        """
        If the admin has defined tags for this computer, but they are not
        valid, we drop them, and report an error.
        """
        self.log_helper.ignore_errors("Invalid tags provided for registration")
        self.mstore.set_accepted_types(["register"])
        self.config.computer_title = "Computer Title"
        self.config.account_name = "account_name"
        self.config.registration_key = "SEKRET"
        self.config.tags = u"<script>alert()</script>"
        self.reactor.fire("pre-exchange")
        messages = self.mstore.get_pending_messages()
        self.assertIs(None, messages[0]["tags"])
        self.assertEqual(self.logfile.getvalue().strip(),
                         "ERROR: Invalid tags provided for registration.\n    "
                         "INFO: Queueing message to register with account "
                         "'account_name' with a password.\n    "
                         "INFO: Sending registration message to exchange.")

    def test_queue_message_on_exchange_with_unicode_tags(self):
        """
        If the admin has defined tags for this computer, we send them to the
        server.
        """
        self.mstore.set_accepted_types(["register"])
        self.config.computer_title = "Computer Title"
        self.config.account_name = "account_name"
        self.config.registration_key = "SEKRET"
        self.config.tags = u"prova\N{LATIN SMALL LETTER J WITH CIRCUMFLEX}o"
        self.reactor.fire("pre-exchange")
        messages = self.mstore.get_pending_messages()
        expected = u"prova\N{LATIN SMALL LETTER J WITH CIRCUMFLEX}o"
        self.assertEqual(expected, messages[0]["tags"])

        self.assertEqual(self.logfile.getvalue().strip(),
                         "INFO: Queueing message to register with account "
                         "'account_name' and tags prova\xc4\xb5o "
                         "with a password.\n    "
                         "INFO: Sending registration message to exchange.")

    def test_queue_message_on_exchange_with_access_group(self):
        """
        If the admin has defined an access_group for this computer, we send
        it to the server.
        """
        self.mstore.set_accepted_types(["register"])
        self.config.account_name = "account_name"
        self.config.access_group = u"dinosaurs"
        self.config.tags = u"server,london"
        self.reactor.fire("pre-exchange")
        messages = self.mstore.get_pending_messages()
        self.assertEqual("dinosaurs", messages[0]["access_group"])
        self.assertEqual(self.logfile.getvalue().strip(),
                         "INFO: Queueing message to register with account "
                         "'account_name' in access group 'dinosaurs' and "
                         "tags server,london without a password.\n    "
                         "INFO: Sending registration message to exchange.")

    def test_queue_message_on_exchange_with_empty_access_group(self):
        """
        If the access_group is "", then the outgoing message does not define
        an "access_group" key.
        """
        self.mstore.set_accepted_types(["register"])
        self.config.access_group = u""
        self.reactor.fire("pre-exchange")
        messages = self.mstore.get_pending_messages()
        # Make sure the key does not appear in the outgoing message.
        self.assertNotIn("access_group", messages[0])

    def test_queue_message_on_exchange_with_none_access_group(self):
        """
        If the access_group is None, then the outgoing message does not define
        an "access_group" key.
        """
        self.mstore.set_accepted_types(["register"])
        self.config.access_group = None
        self.reactor.fire("pre-exchange")
        messages = self.mstore.get_pending_messages()
        # Make sure the key does not appear in the outgoing message.
        self.assertNotIn("access_group", messages[0])

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
        """
        When we call C{register} this should trigger a "resynchronize-clients"
        event with global scope.
        """
        results = []

        def append(scopes=None):
            results.append(scopes)

        self.reactor.call_on("resynchronize-clients", append)

        self.handler.register()

        # This should somehow callback the deferred.
        self.exchanger.handle_message(
            {"type": "set-id", "id": "abc", "insecure-id": "def"})

        self.assertEqual(results, [None])

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
        self.config.registration_key = "SEKRET"
        self.reactor.fire("pre-exchange")
        messages = self.mstore.get_pending_messages()
        self.assertEqual(socket.getfqdn(), messages[0]["hostname"])


class JujuRegistrationHandlerTest(RegistrationHandlerTestBase):

    juju_contents = json.dumps({"environment-uuid": "DEAD-BEEF",
                                "unit-name": "service/0",
                                "api-addresses": "10.0.3.1:17070"})

    def test_juju_information_added_when_present(self):
        """
        When Juju information is found in $data_dir/juju-info.d/*.json,
        key parts of it are sent in the registration message.
        """
        self.mstore.set_accepted_types(["register"])
        self.config.account_name = "account_name"
        self.reactor.fire("run")
        self.reactor.fire("pre-exchange")

        messages = self.mstore.get_pending_messages()
        expected = {"environment-uuid": "DEAD-BEEF",
                    "api-addresses": ["10.0.3.1:17070"],
                    "unit-name": "service/0"}
        self.assertEqual(expected, messages[0]["juju-info-list"][0])

    def test_juju_info_compatibility_present(self):
        """
        When Juju information is found in $data_dir/juju-info.d/*.json,
        the registration message also contains a "juju-info" key for
        backwards compatibility with older servers.
        """
        self.mstore.set_accepted_types(["register"])
        self.config.account_name = "account_name"
        self.reactor.fire("run")
        self.reactor.fire("pre-exchange")

        messages = self.mstore.get_pending_messages()
        expected = {"environment-uuid": "DEAD-BEEF",
                    "api-addresses": ["10.0.3.1:17070"],
                    "unit-name": "service/0"}
        self.assertEqual(expected, messages[0]["juju-info"])

    def test_multiple_juju_information_added_when_present(self):
        """
        When Juju information is found in $data_dir/juju-info.json,
        key parts of it are sent in the registration message.
        """
        # Write a second file in the config directory
        contents = json.dumps({"environment-uuid": "DEAD-BEEF",
                               "unit-name": "service-2/0",
                               "api-addresses": "10.0.3.2:17070",
                               "private-address": "127.0.0.1"})
        self.makeFile(
            contents,
            dirname=self.config.juju_directory, suffix=".json")

        self.mstore.set_accepted_types(["register"])
        self.config.account_name = "account_name"
        self.reactor.fire("run")
        self.reactor.fire("pre-exchange")

        messages = self.mstore.get_pending_messages()
        juju_info = messages[0]["juju-info-list"]
        self.assertEqual(2, len(juju_info))

        expected1 = {"environment-uuid": "DEAD-BEEF",
                     "api-addresses": ["10.0.3.1:17070"],
                     "unit-name": "service/0"}
        self.assertIn(expected1, juju_info)

        expected2 = {"environment-uuid": "DEAD-BEEF",
                     "api-addresses": ["10.0.3.2:17070"],
                     "unit-name": "service-2/0",
                     "private-address": "127.0.0.1"}
        self.assertIn(expected2, juju_info)


class ProvisioningRegistrationTest(RegistrationHandlerTestBase):

    def test_provisioned_machine_registration_with_otp(self):
        """
        Register provisioned machines using an OTP.
        """
        self.mstore.set_accepted_types(["register-provisioned-machine"])
        self.config.account_name = ""
        self.config.provisioning_otp = "ohteepee"
        self.reactor.fire("pre-exchange")

        self.assertMessages([{"otp": "ohteepee", "timestamp": 0, "api": "3.2",
                              "type": "register-provisioned-machine"}],
                            self.mstore.get_pending_messages())
        self.assertEqual(u"INFO: Queueing message to register with OTP as a"
                         u" newly provisioned machine.\n    "
                         "INFO: Sending registration message to exchange.",
                         self.logfile.getvalue().strip())

        self.exchanger.exchange()
        self.assertMessages([{"otp": "ohteepee", "timestamp": 0, "api": "3.2",
                              "type": "register-provisioned-machine"}],
                            self.transport.payloads[0]["messages"])

    def test_provisioned_machine_registration_with_empty_otp(self):
        """
        No message should be sent when an empty OTP is passed.
        """
        self.mstore.set_accepted_types(["register-provisioned-machine"])
        self.config.account_name = ""
        self.config.provisioning_otp = ""
        self.reactor.fire("pre-exchange")

        self.assertMessages([], self.mstore.get_pending_messages())
        self.assertEqual(u"", self.logfile.getvalue().strip())
