from twisted.internet.defer import Deferred
from landscape.lib.twisted_util import gather_results
from landscape.tests.helpers import (
    LandscapeTest, DEFAULT_ACCEPTED_TYPES, TestSpy, spy)
from landscape.broker.tests.helpers import BrokerClientHelper


class BrokerClientTest(LandscapeTest):

    helpers = [BrokerClientHelper]

    def test_ping(self):
        """
        The L{BrokerClient.ping} method always returns C{True}.
        """
        self.assertTrue(self.client.ping())

    def test_register_plugin(self):
        """
        The L{BrokerClient.register_plugin} method registers a new plugin
        plugin, and calls the plugin's C{register} method.
        """
        plugin = TestSpy()
        self.client.register_plugin(plugin)
        spy.replay(plugin)
        self.assertEquals(spy.history(plugin),
                          [plugin.register(self.client)])

    def test_get_plugins(self):
        """
        The L{BrokerClient.get_plugins} method returns a list
        of registered plugins.
        """
        plugin1 = TestSpy()
        plugin2 = TestSpy()
        self.client.register_plugin(plugin1)
        self.client.register_plugin(plugin2)
        self.assertEquals(self.client.get_plugins(), [plugin1, plugin2])

    def test_get_named_plugin(self):
        """
        If a plugin has a C{plugin_name} attribute, it is possible to look it
        up by name after adding it to the L{BrokerClient}.
        """
        plugin = TestSpy(plugin_name="foo")
        self.client.register_plugin(plugin)
        self.assertEquals(self.client.get_plugin("foo"), plugin)

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
        C{BrokerClient.dispatch_message} calls a previously-registered message
        handler.
        """
        history = []

        def handle_message(message):
            history.append(message)

        def dispatch_message(result):
            message = {"type": "foo"}
            self.assertTrue(self.client.dispatch_message(message))
            self.assertEquals(history, [message])

        result = self.client.register_message("foo", handle_message)
        return result.addCallback(dispatch_message)

    def test_dispatch_message_with_exception(self):
        """
        C{BrokerClient.dispatch_message} gracefully logs exceptions raised
        by message handlers.
        """
        self.log_helper.ignore_errors("Error running message handler.*")

        def handle_message(message):
            raise ZeroDivisionError

        def dispatch_message(result):
            message = {"type": "foo"}
            self.assertTrue(self.client.dispatch_message(message))
            self.assertTrue("Error running message handler for type 'foo'" in
                            self.logfile.getvalue())

        result = self.client.register_message("foo", handle_message)
        return result.addCallback(dispatch_message)

    def test_dispatch_nonexistent_message(self):
        """
        C{BrokerClient.dispatch_message} return C{False} if no handler was
        found for the given message.
        """
        self.assertFalse(self.client.dispatch_message({"type": "test"}))

    def test_exchange(self):
        """
        The L{BrokerClient.exchange} method calls C{exchange} on all
        plugins, if available.
        """
        plugin = TestSpy(plugin_name="test")
        self.assertTrue(hasattr(plugin, "exchange"))
        self.client.register_plugin(plugin)
        spy.clear(plugin)
        self.client.exchange()
        spy.replay(plugin)
        self.assertEquals(spy.history(plugin), [plugin.exchange()])
        self.assertTrue("Got notification of impending exchange. "
                        "Notifying all plugins." in self.logfile.getvalue())

    def test_exchange_on_plugin_without_exchange_method(self):
        """
        The L{BrokerClient.exchange} method ignores plugins without
        an C{exchange} method.
        """
        plugin = TestSpy(plugin_name="test")
        spy.blacklist(plugin, "exchange")
        self.assertFalse(hasattr(plugin, "exchange"))
        self.client.register_plugin(plugin)
        spy.clear(plugin)
        self.client.exchange()
        self.assertEquals(spy.history(plugin), [])

    def test_exchange_logs_errors_and_continues(self):
        """
        If the L{exchange} method of a registered plugin fails, the error is
        logged and other plugins are processed.
        """
        self.log_helper.ignore_errors(ZeroDivisionError)
        plugin1 = TestSpy(plugin_name="foo", exchange=lambda: 1 / 0)
        plugin2 = TestSpy(plugin_name="bar")
        self.client.register_plugin(plugin1)
        self.client.register_plugin(plugin2)
        spy.clear(plugin2)
        self.client.exchange()
        self.assertTrue("Error during plugin exchange" in
                        self.logfile.getvalue())
        self.assertTrue("ZeroDivisionError" in self.logfile.getvalue())
        spy.replay(plugin2)
        self.assertEquals(spy.history(plugin2), [plugin2.exchange()])

    def test_broker_started(self):
        """
        When L{BrokerClient.broker_started} is called, any message types
        previously registered with the broker are registered again.
        """
        result1 = self.client.register_message("foo", lambda m: None)
        result2 = self.client.register_message("bar", lambda m: None)
        types = []
        d = Deferred()

        def register_client_accepted_message_type(type):
            types.append(type)
            if len(types) == 2:
                d.callback(types)

        def got_result(result):
            self.client.broker.register_client_accepted_message_type = \
                 register_client_accepted_message_type
            self.client.broker_started()
            return d.addCallback(self.assertEquals, ["foo", "bar"])
        return gather_results([result1, result2]).addCallback(got_result)

    def test_exit(self):
        """
        The L{BrokerClient.exit} method causes the reactor to be stopped.
        """
        self.client.reactor = TestSpy()
        self.client.exit()
        spy.replay(self.client.reactor)
        self.assertEquals(spy.history(self.client.reactor),
                          [self.client.reactor.stop()])
