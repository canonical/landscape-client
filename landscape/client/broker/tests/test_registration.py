import json
import logging
import socket
import mock

from twisted.python.compat import _PY3

from landscape.client.broker.registration import RegistrationError, Identity
from landscape.client.tests.helpers import LandscapeTest
from landscape.client.broker.tests.helpers import (
    BrokerConfigurationHelper, RegistrationHelper)
from landscape.lib.persist import Persist


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

    def test_secure_id_as_unicode(self):
        """secure-id is expected to be retrieved as unicode."""
        self.identity.secure_id = b"spam"
        self.assertEqual(self.identity.secure_id, "spam")

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
            {"type": b"set-id", "id": b"abc", "insecure-id": b"def"})
        self.assertEqual(self.identity.secure_id, "abc")
        self.assertEqual(self.identity.insecure_id, "def")

    def test_registration_done_event(self):
        """
        When new ids are received from the server, a "registration-done"
        event is fired.
        """
        reactor_fire_mock = self.reactor.fire = mock.Mock()
        self.exchanger.handle_message(
            {"type": b"set-id", "id": b"abc", "insecure-id": b"def"})
        reactor_fire_mock.assert_any_call("registration-done")

    def test_unknown_id(self):
        self.identity.secure_id = "old_id"
        self.identity.insecure_id = "old_id"
        self.mstore.set_accepted_types(["register"])
        self.exchanger.handle_message({"type": b"unknown-id"})
        self.assertEqual(self.identity.secure_id, None)
        self.assertEqual(self.identity.insecure_id, None)

    def test_unknown_id_with_clone(self):
        """
        If the server reports us that we are a clone of another computer, then
        set our computer's title accordingly.
        """
        self.config.computer_title = "Wu"
        self.mstore.set_accepted_types(["register"])
        self.exchanger.handle_message(
            {"type": b"unknown-id", "clone-of": "Wu"})
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
                         "'account_name' without a password.")

    @mock.patch("landscape.client.broker.registration.get_vm_info")
    def test_queue_message_on_exchange_with_vm_info(self, get_vm_info_mock):
        """
        When a computer_title and account_name are available, no
        secure_id is set, and an exchange is about to happen,
        queue a registration message with VM information.
        """
        get_vm_info_mock.return_value = b"vmware"
        self.mstore.set_accepted_types(["register"])
        self.config.computer_title = "Computer Title"
        self.config.account_name = "account_name"
        self.reactor.fire("pre-exchange")
        messages = self.mstore.get_pending_messages()
        self.assertEqual(b"vmware", messages[0]["vm-info"])
        self.assertEqual(self.logfile.getvalue().strip(),
                         "INFO: Queueing message to register with account "
                         "'account_name' without a password.")
        get_vm_info_mock.assert_called_once_with()

    @mock.patch("landscape.client.broker.registration.get_container_info")
    def test_queue_message_on_exchange_with_lxc_container(
            self, get_container_info_mock):
        """
        If the client is running in an LXC container, the information is
        included in the registration message.
        """
        get_container_info_mock.return_value = "lxc"
        self.mstore.set_accepted_types(["register"])
        self.config.computer_title = "Computer Title"
        self.config.account_name = "account_name"
        self.reactor.fire("pre-exchange")
        messages = self.mstore.get_pending_messages()
        self.assertEqual("lxc", messages[0]["container-info"])
        get_container_info_mock.assert_called_once_with()

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
                         "'account_name' with a password.")

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
                         "password.")

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
                         "'account_name' with a password.")

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

        logs = self.logfile.getvalue().strip()
        # XXX This is not nice, as it has the origin in a non-consistent way of
        # using logging. self.logfile is a cStringIO in Python 2 and
        # io.StringIO in Python 3. This results in reading bytes in Python 2
        # and unicode in Python 3, but a drop-in replacement of cStringIO with
        # io.StringIO in Python 2 is not working. However, we compare bytes
        # here, to circumvent that problem.
        if _PY3:
            logs = logs.encode("utf-8")
        self.assertEqual(logs,
                         b"INFO: Queueing message to register with account "
                         b"'account_name' and tags prova\xc4\xb5o "
                         b"with a password.")

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
                         "tags server,london without a password.")

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
        self.mstore.set_accepted_types(["register"])
        self.config.computer_title = "Computer Title"
        self.config.account_name = "account_name"

        # If we didn't fake it, it'd work.  We do that to ensure that
        # all the needed data is in place, and that this method is
        # really what decides if a message is sent or not.  This way
        # we can test it individually.
        self.assertTrue(self.handler.should_register())

        handler_mock = self.handler.should_register = mock.Mock()
        handler_mock.return_value = False

        self.reactor.fire("pre-exchange")
        self.assertMessages(self.mstore.get_pending_messages(), [])
        handler_mock.assert_called_once_with()

    def test_registration_failed_event_unknown_account(self):
        """
        The deferred returned by a registration request should fail
        if the server responds with a failure message because credentials are
        wrong.
        """
        reactor_fire_mock = self.reactor.fire = mock.Mock()
        self.exchanger.handle_message(
            {"type": b"registration", "info": b"unknown-account"})
        reactor_fire_mock.assert_called_with(
            "registration-failed", reason="unknown-account")

    def test_registration_failed_event_max_pending_computers(self):
        """
        The deferred returned by a registration request should fail
        if the server responds with a failure message because the max number of
        pending computers have been reached.
        """
        reactor_fire_mock = self.reactor.fire = mock.Mock()
        self.exchanger.handle_message(
            {"type": b"registration", "info": b"max-pending-computers"})
        reactor_fire_mock.assert_called_with(
            "registration-failed", reason="max-pending-computers")

    def test_registration_failed_event_not_fired_when_uncertain(self):
        """
        If the data in the registration message isn't what we expect,
        the event isn't fired.
        """
        reactor_fire_mock = self.reactor.fire = mock.Mock()
        self.exchanger.handle_message(
            {"type": b"registration", "info": b"blah-blah"})
        for name, args, kwargs in reactor_fire_mock.mock_calls:
            self.assertNotEquals("registration-failed", args[0])

    def test_register_resets_ids(self):
        self.identity.secure_id = "foo"
        self.identity.insecure_id = "bar"
        self.handler.register()
        self.assertEqual(self.identity.secure_id, None)
        self.assertEqual(self.identity.insecure_id, None)

    def test_register_calls_urgent_exchange(self):
        self.exchanger.exchange = mock.Mock(wraps=self.exchanger.exchange)
        self.handler.register()
        self.exchanger.exchange.assert_called_once_with()

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
            {"type": b"set-id", "id": b"abc", "insecure-id": b"def"})

        self.assertEqual(calls, [1])

        # Doing it again to ensure that the deferred isn't called twice.
        self.exchanger.handle_message(
            {"type": b"set-id", "id": b"abc", "insecure-id": b"def"})

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
            {"type": b"set-id", "id": b"abc", "insecure-id": b"def"})

        self.assertEqual(results, [None])

    def test_register_deferred_called_on_failed_unknown_account(self):
        """
        The registration errback is called on failures when credentials are
        invalid.
        """
        # We don't want informational messages.
        self.logger.setLevel(logging.WARNING)

        calls = []
        d = self.handler.register()

        def add_call(failure):
            exception = failure.value
            self.assertTrue(isinstance(exception, RegistrationError))
            self.assertEqual("unknown-account", str(exception))
            calls.append(True)

        d.addErrback(add_call)

        # This should somehow callback the deferred.
        self.exchanger.handle_message(
            {"type": b"registration", "info": b"unknown-account"})

        self.assertEqual(calls, [True])

        # Doing it again to ensure that the deferred isn't called twice.
        self.exchanger.handle_message(
            {"type": b"registration", "info": b"unknown-account"})

        self.assertEqual(calls, [True])

        self.assertEqual(self.logfile.getvalue(), "")

    def test_register_deferred_called_on_failed_max_pending_computers(self):
        """
        The registration errback is called on failures when max number of
        pending computers has been reached.
        """
        # We don't want informational messages.
        self.logger.setLevel(logging.WARNING)

        calls = []
        d = self.handler.register()

        def add_call(failure):
            exception = failure.value
            self.assertTrue(isinstance(exception, RegistrationError))
            self.assertEqual("max-pending-computers", str(exception))
            calls.append(True)

        d.addErrback(add_call)

        self.exchanger.handle_message(
            {"type": b"registration", "info": b"max-pending-computers"})

        self.assertEqual(calls, [True])

        # Doing it again to ensure that the deferred isn't called twice.
        self.exchanger.handle_message(
            {"type": b"registration", "info": b"max-pending-computers"})

        self.assertEqual(calls, [True])

        self.assertEqual(self.logfile.getvalue(), "")

    def test_exchange_done_calls_exchange(self):
        self.exchanger.exchange = mock.Mock(wraps=self.exchanger.exchange)
        self.mstore.set_accepted_types(["register"])
        self.config.computer_title = "Computer Title"
        self.config.account_name = "account_name"
        self.reactor.fire("exchange-done")
        self.exchanger.exchange.assert_called_once_with()

    def test_exchange_done_wont_call_exchange_when_just_tried(self):
        self.exchanger.exchange = mock.Mock(wraps=self.exchanger.exchange)
        self.mstore.set_accepted_types(["register"])
        self.config.computer_title = "Computer Title"
        self.config.account_name = "account_name"
        self.reactor.fire("pre-exchange")
        self.reactor.fire("exchange-done")
        self.assertNot(self.exchanger.exchange.called)

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
                                "machine-id": "1",
                                "api-addresses": "10.0.3.1:17070"})

    def test_juju_info_added_when_present(self):
        """
        When information about the Juju environment is found in
        the $data_dir/juju-info.d/ directory, it's included in
        the registration message.
        """
        self.mstore.set_accepted_types(["register"])
        self.mstore.set_server_api(b"3.3")
        self.config.account_name = "account_name"
        self.reactor.fire("run")
        self.reactor.fire("pre-exchange")

        messages = self.mstore.get_pending_messages()
        self.assertEqual(
            {"environment-uuid": "DEAD-BEEF",
             "machine-id": "1",
             "api-addresses": ["10.0.3.1:17070"]},
            messages[0]["juju-info"])

    def test_juju_info_skipped_with_old_server(self):
        """
        If a server doesn't speak at least 3.3, the juju-info field is
        isn't included in the message.
        """
        self.mstore.set_accepted_types(["register"])
        self.mstore.set_server_api(b"3.2")
        self.config.account_name = "account_name"
        self.reactor.fire("run")
        self.reactor.fire("pre-exchange")

        messages = self.mstore.get_pending_messages()
        self.assertNotIn("juju-info", messages[0])
