from twisted.internet.defer import Deferred
from landscape.lib.twisted_util import gather_results
from landscape.tests.helpers import (
    LandscapeTest, DEFAULT_ACCEPTED_TYPES, TestSpy, spy)
from landscape.broker.tests.helpers import RemoteBrokerHelper
from landscape.broker.plugin import (
    BrokerClientPluginRegistry, HandlerNotFoundError)


class BrokerClientPluginRegistryTest(LandscapeTest):

    helpers = [RemoteBrokerHelper]

    def setUp(self):
        connected = super(BrokerClientPluginRegistryTest, self).setUp()
        connected.addCallback(lambda x: setattr(
            self, "registry", BrokerClientPluginRegistry(self.remote)))
        return connected

    def test_add_plugin(self):
        """
        The L{BrokerClientPluginRegistry.add_plugin} method register a new
        plugin, and calls the plugin's C{register} method.
        """
        plugin = TestSpy()
        self.registry.add(plugin)
        spy.replay(plugin)
        self.assertEquals(spy.history(plugin),
                          [plugin.register(self.registry)])

    def test_get_plugins(self):
        """
        The L{BrokerClientPluginRegistry.get_plugins} method returns a list
        of registered plugins.
        """
        plugin1 = TestSpy()
        plugin2 = TestSpy()
        self.registry.add(plugin1)
        self.registry.add(plugin2)
        self.assertEquals(self.registry.get_plugins(), [plugin1, plugin2])

    def test_get_named_plugin(self):
        """
        If a plugin has a C{plugin_name} attribute, it is possible to look it
        up by name after adding it to the L{BrokerClientPluginRegistry}.
        """
        plugin = TestSpy(plugin_name="foo")
        self.registry.add(plugin)
        self.assertEquals(self.registry.get_plugin("foo"), plugin)

    def test_dispatch_message(self):
        """
        C{BrokerClientPluginRegistry.dispatch_message} calls a
        previously-registered message handler.
        """
        history = []

        def handle_message(message):
            history.append(message)
            return "bar"

        def dispatch_message(result):
            message = {"type": "foo"}
            self.assertEquals(self.registry.dispatch_message(message), "bar")
            self.assertEquals(history, [message])

        result = self.registry.register_message("foo", handle_message)
        return result.addCallback(dispatch_message)

    def test_dispatch_nonexistent_message(self):
        """
        L{HandlerNotFoundError} is raised when a message handler can't be
        found.
        """
        self.assertRaises(HandlerNotFoundError,
                          self.registry.dispatch_message, {"type": "test"})

    def test_register_message_registers_message_type_with_broker(self):
        """
        When L{BrokerClientPluginRegistry.register_message} is called, the
        broker is notified that the message type is now accepted.
        """
        result1 = self.registry.register_message("foo", lambda m: None)
        result2 = self.registry.register_message("bar", lambda m: None)

        def got_result(result):
            self.assertEquals(
                self.exchanger.get_client_accepted_message_types(),
                sorted(["bar", "foo"] + DEFAULT_ACCEPTED_TYPES))

        return gather_results([result1, result2]).addCallback(got_result)

    def test_exchange_on_plugin_without_exchange_method(self):
        """
        The L{PluginRegistry.exchange} method calls C{exchange} on all
        plugins, if available.
        """
        plugin = TestSpy(plugin_name="test")
        spy.blacklist(plugin, "exchange")
        self.assertFalse(hasattr(plugin, "exchange"))
        self.registry.add(plugin)
        spy.clear(plugin)
        self.registry.exchange()
        self.assertEquals(spy.history(plugin), [])

    def test_exchange_on_plugin_with_exchange_method(self):
        """
        The L{PluginRegistry.exchange} method calls C{exchange} on all
        plugins, if available.
        """
        plugin = TestSpy(plugin_name="test")
        self.assertTrue(hasattr(plugin, "exchange"))
        self.registry.add(plugin)
        spy.clear(plugin)
        self.registry.exchange()
        spy.replay(plugin)
        self.assertEquals(spy.history(plugin), [plugin.exchange()])

    def test_exchange_logs_errors_and_continues(self):
        """
        If the L{exchange} method of a registered plugin fails, the error is
        logged and other plugins are processed.
        """
        self.log_helper.ignore_errors(ZeroDivisionError)
        plugin1 = TestSpy(plugin_name="foo", exchange=lambda: 1/0)
        plugin2 = TestSpy(plugin_name="bar")
        self.registry.add(plugin1)
        self.registry.add(plugin2)
        spy.clear(plugin2)
        self.registry.exchange()
        self.assertTrue("Error during plugin exchange" in
                        self.logfile.getvalue())
        self.assertTrue("ZeroDivisionError" in self.logfile.getvalue())
        spy.replay(plugin2)
        self.assertEquals(spy.history(plugin2), [plugin2.exchange()])

    def test_broker_restart(self):
        """
        When L{BrokerClientPluginRegistry.broker_started} is called, any
        message types previously registered with the broker are registered
        again.
        """
        result1 = self.registry.register_message("foo", lambda m: None)
        result2 = self.registry.register_message("bar", lambda m: None)
        types = []
        d = Deferred()

        def register_client_accepted_message_type(type):
            types.append(type)
            if len(types) == 2:
                d.callback(types)

        def got_result(result):
            self.registry.broker.register_client_accepted_message_type = \
                 register_client_accepted_message_type
            self.registry.broker_started()
            return d.addCallback(self.assertEquals, ["foo", "bar"])
        return gather_results([result1, result2]).addCallback(got_result)
