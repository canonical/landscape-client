from twisted.internet import reactor
from twisted.internet.defer import Deferred

from landscape.lib.twisted_util import gather_results
from landscape.tests.helpers import LandscapeTest, DEFAULT_ACCEPTED_TYPES
from landscape.broker.tests.helpers import BrokerClientHelper
from landscape.broker.client import BrokerClientPlugin, HandlerNotFoundError


class BrokerClientTest(LandscapeTest):

    helpers = [BrokerClientHelper]

    def test_connected(self):
        """
        The L{BrokerClient.connected} method sets the reference to
        the remote broker, and exposes the client itself via AMP.
        """
        self.assertIs(self.client.broker.protocol.object, self.client)

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

    def test_get_plugins(self):
        """
        The L{BrokerClient.get_plugins} method returns a list
        of registered plugins.
        """
        plugins = [BrokerClientPlugin(), BrokerClientPlugin()]
        self.client.add(plugins[0])
        self.client.add(plugins[1])
        self.assertEquals(self.client.get_plugins(), plugins)

    def test_get_named_plugin(self):
        """
        If a plugin has a C{plugin_name} attribute, it is possible to look it
        up by name after adding it to the L{BrokerClient}.
        """
        plugin = BrokerClientPlugin()
        plugin.plugin_name = "foo"
        self.client.add(plugin)
        self.assertEquals(self.client.get_plugin("foo"), plugin)

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

    def test_register_message(self):
        """
        When L{BrokerClient.register_message} is called, the broker is notified
        that the message type is now accepted.
        """
        result1 = self.client.register_message("foo", lambda m: None)
        result2 = self.client.register_message("bar", lambda m: None)

        def got_result(result):
            self.assertEquals(
                self.exchanger.get_client_accepted_message_types(),
                sorted(["bar", "foo"] + DEFAULT_ACCEPTED_TYPES))

        return gather_results([result1, result2]).addCallback(got_result)

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
            self.assertEquals(self.client.dispatch_message(message), 123)

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
        self.assertEquals(str(error), "x")

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
            self.assertEquals(self.client.message(message), True)

        result = self.client.register_message("foo", handle_message)
        return result.addCallback(dispatch_message)

    def test_message_with_no_handler(self):
        """
        The L{BrokerClient.message} method returns C{False} if no
        handler was found.
        """
        message = {"type": "foo"}
        self.assertEquals(self.client.message(message), False)

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
        The L{BrokerClient.notify_exchange} method calls C{exchange} on all
        plugins and logs the event.
        """
        plugin = BrokerClientPlugin()
        plugin.exchange = self.mocker.mock()
        plugin.exchange()
        self.mocker.replay()
        self.client.add(plugin)
        self.client.notify_exchange()
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

    def test_broker_started(self):
        """
        When L{BrokerClient.broker_started} is called, any message types
        previously registered with the broker are registered again.
        """
        result1 = self.client.register_message("foo", lambda m: None)
        result2 = self.client.register_message("bar", lambda m: None)

        def got_result(result):
            self.client.broker = self.mocker.mock()
            self.client.broker.register_client_accepted_message_type("foo")
            self.client.broker.register_client_accepted_message_type("bar")
            self.mocker.replay()
            self.client.broker_started()

        return gather_results([result1, result2]).addCallback(got_result)

    def test_exit(self):
        """
        The L{BrokerClient.exit} method causes the reactor to be stopped.
        """
        self.client.reactor = self.mocker.mock()
        self.client.reactor.stop()
        self.mocker.replay()
        self.client.exit()
