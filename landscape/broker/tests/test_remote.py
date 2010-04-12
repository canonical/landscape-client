from dbus import DBusException

from twisted.internet.defer import Deferred

from landscape.schema import Message, InvalidError, String, List, Dict
from landscape.broker.remote import (FakeRemoteBroker,
                                     DBusSignalToReactorTransmitter)
from landscape.tests.helpers import (LandscapeIsolatedTest, LandscapeTest,
                                     LegacyExchangeHelper, RemoteBrokerHelper)
from landscape.reactor import FakeReactor


class RemoteBrokerTestsMixin(object):
    """Test cases for testing L{RemoteBroker}-like objects."""

    def setUp(self):
        super(RemoteBrokerTestsMixin, self).setUp()
        self.mstore.add_schema(Message("empty", {}))
        self.mstore.set_accepted_types(["empty"])

    def test_send_message(self):
        # Reset urgent flag.
        self.exchanger.exchange()
        done = self.get_remote().send_message({"type": "empty"})
        def got_result(r):
            self.assertMessages(self.mstore.get_pending_messages(),
                                [{"type": "empty"}])
            self.assertFalse(self.exchanger.is_urgent())
        return done.addCallback(got_result)

    def test_send_message_containing_string_remains_as_string(self):
        """
        Strings in messages should not be converted to unicode.

        This is a regression test related to the fact that strings by default
        are sent as unicode with dbus. We must send our bytes unmolested.
        """
        # Reset urgent flag.
        self.exchanger.exchange()
        self.mstore.add_schema(Message("data", {"data": String()}))
        self.mstore.set_accepted_types(["data"])

        msg = {"type": "data", "data": "foo"}
        done = self.get_remote().send_message(msg)
        def got_result(r):
            messages = self.mstore.get_pending_messages()
            # By now, the assertion already happened in the schema system -
            # String() does not allow unicode objects. Let's just do a sanity
            # check.
            self.assertMessages(messages, [msg])
        return done.addCallback(got_result)

    def test_send_complex_data_in_messages(self):
        # Reset urgent flag.
        self.exchanger.exchange()
        self.mstore.add_schema(
            Message("data", {"data": List(Dict(String(), String()))}))
        self.mstore.set_accepted_types(["data"])

        msg = {"type": "data", "data": [{"foo": "bar"}]}
        done = self.get_remote().send_message(msg)
        def got_result(r):
            messages = self.mstore.get_pending_messages()
            self.assertMessages(messages, [msg])
        return done.addCallback(got_result)

    def test_send_message_urgent(self):
        """
        Sending a message with the urgent flag should schedule an
        urgent exchange.
        """
        # Reset urgent flag.
        self.exchanger.exchange()
        self.assertFalse(self.exchanger.is_urgent())
        done = self.get_remote().send_message({"type": "empty"}, urgent=True)
        def got_result(r):
            self.assertMessages(self.mstore.get_pending_messages(),
                                [{"type": "empty"}])
            self.assertTrue(self.exchanger.is_urgent())
        return done.addCallback(got_result)

    def test_send_bad_schema(self):
        self.log_helper.ignore_errors(InvalidError)
        done = self.get_remote().send_message({"type": "empty", "data": "data"})
        return self.assertFailure(done, InvalidError)


class FakeRemoteBrokerTests(RemoteBrokerTestsMixin, LandscapeTest):
    """Tests for L{FakeRemoteBroker}."""

    helpers = [LegacyExchangeHelper]

    def get_remote(self):
        return FakeRemoteBroker(self.exchanger, self.mstore)


class RemoteBrokerTests(RemoteBrokerTestsMixin, LandscapeIsolatedTest):
    """Tests for L{RemoteBroker}."""

    helpers = [RemoteBrokerHelper]

    @property
    def mstore(self):
        return self.broker_service.message_store

    @property
    def exchanger(self):
        return self.broker_service.exchanger

    def get_remote(self):
        """
        Return a real L{RemoteBroker} object that will talk to a
        L{BrokerDBusObject} over DBus.
        """
        return self.remote

    def test_unknown_errors_will_errback(self):
        """
        The errback is invoked when an unknown error is raised during
        a DBUS call.
        """
        self.log_helper.ignore_errors(AssertionError)
        self.log_helper.ignore_errors(KeyError)
        result = self.get_remote().send_message({"no-type": "none"})
        self.assertFailure(result, DBusException)
        def got_result(exception):
            self.assertTrue("AssertionError" in str(exception))
        result.addCallback(got_result)
        return result

    def test_fire_event(self):
        """
        The L{RemoteBroker.fire_event} method lets clients fire events in the
        broker reactor.
        """
        deferred = Deferred()

        def event_fired():
            deferred.callback(None)
        
        self.broker_service.reactor.call_on("event", event_fired)
        remote = self.get_remote()
        remote.fire_event("event")
        return deferred


def assertTransmitterActive(test_case, deployment_broker, target_reactor):
    """
    Make sure that there is a dbus message -> reactor event transmitter
    installed.

    The return value of this function should be returned from your test.

    The common failure mode of this test is timing out. :-(

    @param test_case: C{self}, most likely
    @param deployment_broker: C{self.broker_service} if you are using the
        L{RemoteBrokerHelper}.
    @param target_reactor: A reactor which should have the
        L{DBusSignalToReactorTransmitter} installed on it.
    """
    result = Deferred()
    target_reactor.call_on("resynchronize", lambda: result.callback(None))

    # *Kind* of reach into some guts to broadcast a message DBUS signal.
    msg = {"type": "foo", "data": "whatever"}
    deployment_broker.reactor.fire("resynchronize-clients")

    return result


def set_timeout(timeout):
    """Decorator to set the method timeout."""
    def decorate(method):
        method.timeout = timeout
        return method
    return decorate


class MessageDBusSignalToReactorTransmitterTests(LandscapeIsolatedTest):

    helpers = [RemoteBrokerHelper]

    @set_timeout(4)
    def test_resynchronize(self):
        """
        A 'resynchronize' DBUS signal should be translated to a 'resynchronize'
        reactor event.
        """
        reactor = FakeReactor()
        DBusSignalToReactorTransmitter(self.broker_service.bus, reactor)
        result = Deferred()
        reactor.call_on("resynchronize", lambda: result.callback(None))
        self.broker_service.reactor.fire("resynchronize-clients")
        return result

    @set_timeout(4)
    def test_message_type_acceptance_changed(self):
        """
        A 'message-type-acceptance-changed' DBUS signal should be
        translated to a 'message-type-acceptance-changed' reactor
        event.
        """
        reactor = FakeReactor()
        DBusSignalToReactorTransmitter(self.broker_service.bus, reactor)
        result = Deferred()
        reactor.call_on(("message-type-acceptance-changed", u"some-type"),
                        result.callback)
        result.addCallback(self.assertEquals, True)
        self.broker_service.reactor.fire("message-type-acceptance-changed",
                                         "some-type", True)
        return result

    @set_timeout(4)
    def test_message_type_acceptance_changed_to_false(self):
        """
        A 'message-type-acceptance-changed' DBUS signal should be
        translated to a 'message-type-acceptance-changed' reactor
        event.
        """
        reactor = FakeReactor()
        DBusSignalToReactorTransmitter(self.broker_service.bus, reactor)
        result = Deferred()
        reactor.call_on(("message-type-acceptance-changed", u"some-type"),
                        result.callback)
        result.addCallback(self.assertEquals, False)
        self.broker_service.reactor.fire("message-type-acceptance-changed",
                                         "some-type", False)
        return result

    @set_timeout(4)
    def test_server_uuid_changed(self):
        """
        A 'server-uuid-changed' DBUS signal should be translated to a
        'server-uuid-changed' reactor event.
        """
        reactor = FakeReactor()
        DBusSignalToReactorTransmitter(self.broker_service.bus, reactor)
        waiter = Deferred()
        def got_result((old_uuid, new_uuid)):
            self.assertEquals(old_uuid, "old-uuid")
            self.assertEquals(new_uuid, "new-uuid")
        waiter.addCallback(got_result)
        def server_uuid_changed(old_uuid, new_uuid):
            waiter.callback((old_uuid, new_uuid))
        reactor.call_on("server-uuid-changed", server_uuid_changed)
        self.broker_service.reactor.fire("server-uuid-changed",
                                         "old-uuid", "new-uuid")
        return waiter

    @set_timeout(4)
    def test_server_uuid_changed_converts_empty_strings_back_to_nones(self):
        """
        DBus doesn't work well with Nones, so we convert them to empty
        strings when sending the signal.  The remote should then convert
        them back to Nones so that we have the same API on both sides.
        """
        reactor = FakeReactor()
        DBusSignalToReactorTransmitter(self.broker_service.bus, reactor)
        waiter = Deferred()
        def got_result((old_uuid, new_uuid)):
            self.assertEquals(old_uuid, None)
            self.assertEquals(new_uuid, None)
        waiter.addCallback(got_result)
        def server_uuid_changed(old_uuid, new_uuid):
            waiter.callback((old_uuid, new_uuid))
        reactor.call_on("server-uuid-changed", server_uuid_changed)
        self.broker_service.reactor.fire("server-uuid-changed", None, None)
        return waiter

    @set_timeout(4)
    def test_package_data_changed(self):
        """
        A 'package-data-changed' DBUS signal is converted into a reactor event
        with the same name.
        """
        reactor = FakeReactor()
        DBusSignalToReactorTransmitter(self.broker_service.bus, reactor)
        waiter = Deferred()

        def package_data_changed():
            waiter.callback(None)

        reactor.call_on("package-data-changed", package_data_changed)
        self.broker_service.reactor.fire("package-data-changed")
        return waiter
