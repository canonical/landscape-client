from twisted.internet import reactor
from twisted.internet.defer import Deferred, gatherResults

from landscape.tests.helpers import LandscapeTest, DEFAULT_ACCEPTED_TYPES
from landscape.broker.tests.helpers import BrokerClientHelper
from landscape.broker.client import BrokerClientPlugin, HandlerNotFoundError


class BrokerClientTest(LandscapeTest):

    helpers = [BrokerClientHelper]

    def test_ping(self):
        """
        The L{BrokerClient.ping} method always returns C{True}.
        """
        self.assertTrue(self.client.ping())

    def test_add(self):
        """
        The L{BrokerClient.add} method registers a new plugin
        plugin, and calls the plugin's C{register} method.
        """
        plugin = BrokerClientPlugin()
        self.client.add(plugin)
        self.assertIs(plugin.client, self.client)

    def test_registering_plugin_gets_session_id(self):
        """
        As part of the BrokerClientPlugin registration process, a session ID
        is generated.
        """
        plugin = BrokerClientPlugin()
        self.client.add(plugin)
        self.assertIsNot(None, plugin._session_id)

    def test_registered_plugin_uses_correct_scope(self):
        """
        When we register a plugin we use that plugin's scope variable when
        getting a session id.
        """
        test_session_id = self.successResultOf(
            self.client.broker.get_session_id(scope="test"))
        plugin = BrokerClientPlugin()
        plugin.scope = "test"
        self.client.add(plugin)
        self.assertEqual(test_session_id, plugin._session_id)

    def test_resynchronizing_refreshes_session_id(self):
        """
        When a 'reysnchronize' event fires a new session ID is acquired as the
        old one will be removed.
        """
        plugin = BrokerClientPlugin()
        plugin.scope = "test"
        self.client.add(plugin)
        session_id = plugin._session_id
        self.mstore.drop_session_ids()
        self.client_reactor.fire("resynchronize")
        self.assertNotEqual(session_id, plugin._session_id)

    def test_resynchronize_calls_reset(self):
        plugin = BrokerClientPlugin()
        plugin.scope = "test"
        self.client.add(plugin)

        plugin._resest = self.mocker.mock()
        self.expect(plugin._reset())
        self.mocker.replay()
        self.client_reactor.fire("resynchronize")

    def test_get_plugins(self):
        """
        The L{BrokerClient.get_plugins} method returns a list
        of registered plugins.
        """
        plugins = [BrokerClientPlugin(), BrokerClientPlugin()]
        self.client.add(plugins[0])
        self.client.add(plugins[1])
        self.assertEqual(self.client.get_plugins(), plugins)

    def test_get_plugins_returns_a_copy(self):
        """
        The L{BrokerClient.get_plugins} method returns a copy of the list
        of registered plugins, so user can't can't modify our internals.
        """
        plugins = self.client.get_plugins()
        plugins.append(BrokerClientPlugin())
        self.assertEqual(self.client.get_plugins(), [])

    def test_get_named_plugin(self):
        """
        If a plugin has a C{plugin_name} attribute, it is possible to look it
        up by name after adding it to the L{BrokerClient}.
        """
        plugin = BrokerClientPlugin()
        plugin.plugin_name = "foo"
        self.client.add(plugin)
        self.assertEqual(self.client.get_plugin("foo"), plugin)

    def test_run_interval(self):
        """
        If a plugin has a C{run} method, the reactor will call it every
        C{run_interval} seconds.
        """
        plugin = BrokerClientPlugin()
        plugin.run = self.mocker.mock()
        self.expect(plugin.run()).count(2)
        self.mocker.replay()
        self.client.add(plugin)
        self.client_reactor.advance(plugin.run_interval)
        self.client_reactor.advance(plugin.run_interval)

    def test_run_interval_blocked_during_resynch(self):
        """
        During resynchronisation we want to block the C{run} method so that we
        don't send any new messages with old session ids, or with state in an
        indeterminate condition.
        """
        runs = []

        plugin = BrokerClientPlugin()
        self.client.add(plugin)
        session_id = plugin._session_id

        def fake_run():
            runs.append(plugin._session_id)

        def resynchronized(scopes):
            self.assertNotEqual([session_id], runs)
            self.assertEqual([plugin._session_id], runs)

        plugin.run = fake_run
        self.mstore.drop_session_ids()
        deferred = plugin._resynchronize()
        self.client_reactor.advance(plugin.run_interval)
        deferred.addCallback(resynchronized)

    def test_run_immediately(self):
        """
        If a plugin has a C{run} method and C{run_immediately} is C{True},
        the plugin will be run immediately at registration.
        """
        plugin = BrokerClientPlugin()
        plugin.run = self.mocker.mock()
        plugin.run_immediately = True
        self.expect(plugin.run()).count(1)
        self.mocker.replay()
        self.client.add(plugin)

    def test_register_message(self):
        """
        When L{BrokerClient.register_message} is called, the broker is notified
        that the message type is now accepted.
        """
        result1 = self.client.register_message("foo", lambda m: None)
        result2 = self.client.register_message("bar", lambda m: None)

        def got_result(result):
            self.assertEqual(
                self.exchanger.get_client_accepted_message_types(),
                sorted(["bar", "foo"] + DEFAULT_ACCEPTED_TYPES))

        return gatherResults([result1, result2]).addCallback(got_result)

    def test_dispatch_message(self):
        """
        L{BrokerClient.dispatch_message} calls a previously-registered message
        handler and return its value.
        """
        message = {"type": "foo"}
        handle_message = self.mocker.mock()
        self.expect(handle_message(message)).result(123)
        self.mocker.replay()

        def dispatch_message(result):
            self.assertEqual(self.client.dispatch_message(message), 123)

        result = self.client.register_message("foo", handle_message)
        return result.addCallback(dispatch_message)

    def test_dispatch_message_with_exception(self):
        """
        L{BrokerClient.dispatch_message} gracefully logs exceptions raised
        by message handlers.
        """
        message = {"type": "foo"}
        handle_message = self.mocker.mock()
        self.expect(handle_message(message)).throw(ZeroDivisionError)
        self.mocker.replay()

        self.log_helper.ignore_errors("Error running message handler.*")

        def dispatch_message(result):
            self.assertIs(self.client.dispatch_message(message), None)
            self.assertTrue("Error running message handler for type 'foo'" in
                            self.logfile.getvalue())

        result = self.client.register_message("foo", handle_message)
        return result.addCallback(dispatch_message)

    def test_dispatch_message_with_no_handler(self):
        """
        L{BrokerClient.dispatch_message} raises an error if no handler was
        found for the given message.
        """
        error = self.assertRaises(HandlerNotFoundError,
                                  self.client.dispatch_message, {"type": "x"})
        self.assertEqual(str(error), "x")

    def test_message(self):
        """
        The L{BrokerClient.message} method dispatches a message and
        returns C{True} if an handler for it was found.
        """
        message = {"type": "foo"}

        handle_message = self.mocker.mock()
        handle_message(message)
        self.mocker.replay()

        def dispatch_message(result):
            self.assertEqual(self.client.message(message), True)

        result = self.client.register_message("foo", handle_message)
        return result.addCallback(dispatch_message)

    def test_message_with_no_handler(self):
        """
        The L{BrokerClient.message} method returns C{False} if no
        handler was found.
        """
        message = {"type": "foo"}
        self.assertEqual(self.client.message(message), False)

    def test_exchange(self):
        """
        The L{BrokerClient.exchange} method calls C{exchange} on all
        plugins, if available.
        """
        plugin = BrokerClientPlugin()
        plugin.exchange = self.mocker.mock()
        plugin.exchange()
        self.mocker.replay()
        self.client.add(plugin)
        self.client.exchange()

    def test_exchange_on_plugin_without_exchange_method(self):
        """
        The L{BrokerClient.exchange} method ignores plugins without
        an C{exchange} method.
        """
        plugin = BrokerClientPlugin()
        self.assertFalse(hasattr(plugin, "exchange"))
        self.client.exchange()

    def test_exchange_logs_errors_and_continues(self):
        """
        If the L{exchange} method of a registered plugin fails, the error is
        logged and other plugins are processed.
        """
        self.log_helper.ignore_errors(ZeroDivisionError)
        plugin1 = BrokerClientPlugin()
        plugin2 = BrokerClientPlugin()
        plugin1.exchange = self.mocker.mock()
        plugin2.exchange = self.mocker.mock()
        self.expect(plugin1.exchange()).throw(ZeroDivisionError)
        plugin2.exchange()
        self.mocker.replay()
        self.client.add(plugin1)
        self.client.add(plugin2)
        self.client.exchange()
        self.assertTrue("Error during plugin exchange" in
                        self.logfile.getvalue())
        self.assertTrue("ZeroDivisionError" in self.logfile.getvalue())

    def test_notify_exchange(self):
        """
        The L{BrokerClient.notify_exchange} method is triggered by an
        impending-exchange event and calls C{exchange} on all plugins,
        logging the event.
        """
        plugin = BrokerClientPlugin()
        plugin.exchange = self.mocker.mock()
        plugin.exchange()
        self.mocker.replay()
        self.client.add(plugin)
        self.client_reactor.fire("impending-exchange")
        self.assertTrue("Got notification of impending exchange. "
                        "Notifying all plugins." in self.logfile.getvalue())

    def test_fire_event(self):
        """
        The L{BrokerClient.fire_event} method makes the reactor fire the
        given event.
        """
        callback = self.mocker.mock()
        callback()
        self.mocker.replay()
        self.client_reactor.call_on("event", callback)
        self.client.fire_event("event")

    def test_fire_event_with_arguments(self):
        """
        The L{BrokerClient.fire_event} accepts optional arguments and keyword
        arguments to pass to the registered callback.
        """
        callback = self.mocker.mock()
        callback(True, kwarg=2)
        self.mocker.replay()
        self.client_reactor.call_on("event", callback)
        self.client.fire_event("event", True, kwarg=2)

    def test_fire_event_with_mixed_results(self):
        """
        The return values of the fired handlers can be part L{Deferred}s
        and part not.
        """
        deferred = Deferred()
        callback1 = self.mocker.mock()
        callback2 = self.mocker.mock()
        self.expect(callback1()).result(123)
        self.expect(callback2()).result(deferred)
        self.mocker.replay()
        self.client_reactor.call_on("event", callback1)
        self.client_reactor.call_on("event", callback2)
        result = self.client.fire_event("event")
        reactor.callLater(0, lambda: deferred.callback("abc"))
        return self.assertSuccess(result, [123, "abc"])

    def test_fire_event_with_acceptance_changed(self):
        """
        When the given event type is C{message-type-acceptance-changed}, the
        fired event will be a 2-tuple of the eventy type and the message type.
        """
        event_type = "message-type-acceptance-changed"
        callback = self.mocker.mock()
        callback(False)
        self.mocker.replay()
        self.client_reactor.call_on((event_type, "test"), callback)
        self.client.fire_event(event_type, "test", False)

    def test_handle_reconnect(self):
        """
        The L{BrokerClient.handle_reconnect} method is triggered by a
        broker-reconnect event, and it causes any message types previously
        registered with the broker to be registered again.
        """
        result1 = self.client.register_message("foo", lambda m: None)
        result2 = self.client.register_message("bar", lambda m: None)

        def got_result(result):
            self.client.broker = self.mocker.mock()
            self.client.broker.register_client_accepted_message_type("foo")
            self.client.broker.register_client_accepted_message_type("bar")
            self.client.broker.register_client("client")
            self.mocker.replay()
            self.client_reactor.fire("broker-reconnect")

        return gatherResults([result1, result2]).addCallback(got_result)

    def test_exit(self):
        """
        The L{BrokerClient.exit} method causes the reactor to be stopped.
        """
        self.client.reactor.stop = self.mocker.mock()
        self.client.reactor.stop()
        self.mocker.replay()
        self.client.exit()
        self.client.reactor.advance(0.1)
