from twisted.internet.defer import Deferred

from landscape.tests.helpers import LandscapeTest, LandscapeIsolatedTest

from landscape.plugin import (PluginRegistry, BrokerClientPluginRegistry,
                              BrokerPlugin, HandlerNotFoundError)
from landscape.lib.dbus_util import method
from landscape.lib.twisted_util import gather_results
from landscape.lib.bpickle import dumps
from landscape.tests.helpers import RemoteBrokerHelper


class SamplePlugin(object):
    plugin_name = "sample"

    def __init__(self):
        self.registered = []

    def register(self, monitor):
        self.registered.append(monitor)


class ExchangePlugin(SamplePlugin):
    """A plugin which records exchange notification events."""

    def __init__(self):
        super(ExchangePlugin, self).__init__()
        self.exchanged = 0
        self.waiter = None

    def wait_for_exchange(self):
        self.waiter = Deferred()
        return self.waiter

    def exchange(self):
        self.exchanged += 1
        if self.waiter is not None:
            self.waiter.callback(None)


class PluginTest(LandscapeTest):

    def setUp(self):
        super(PluginTest, self).setUp()
        self.registry = PluginRegistry()

    def test_register_plugin(self):
        sample_plugin = SamplePlugin()
        self.registry.add(sample_plugin)
        self.assertEquals(sample_plugin.registered, [self.registry])

    def test_get_plugins(self):
        plugin1 = SamplePlugin()
        plugin2 = SamplePlugin()
        self.registry.add(plugin1)
        self.registry.add(plugin2)
        self.assertEquals(self.registry.get_plugins()[-2:], [plugin1, plugin2])

    def test_get_named_plugin(self):
        """
        If a plugin has a C{plugin_name} attribute, it is possible to look it
        up by name after adding it to the L{Monitor}.
        """
        plugin = SamplePlugin()
        self.registry.add(plugin)
        self.assertEquals(self.registry.get_plugin("sample"), plugin)


class BrokerClientPluginTest(LandscapeIsolatedTest):
    helpers = [RemoteBrokerHelper]

    def setUp(self):
        super(BrokerClientPluginTest, self).setUp()
        self.registry = BrokerClientPluginRegistry(self.remote)

    def test_register_plugin(self):
        sample_plugin = SamplePlugin()
        self.registry.add(sample_plugin)
        self.assertEquals(sample_plugin.registered, [self.registry])

    def test_get_plugins(self):
        plugin1 = SamplePlugin()
        plugin2 = SamplePlugin()
        self.registry.add(plugin1)
        self.registry.add(plugin2)
        self.assertEquals(self.registry.get_plugins()[-2:], [plugin1, plugin2])

    def test_get_named_plugin(self):
        """
        If a plugin has a C{plugin_name} attribute, it is possible to look it
        up by name after adding it to the L{Monitor}.
        """
        plugin = SamplePlugin()
        self.registry.add(plugin)
        self.assertEquals(self.registry.get_plugin("sample"), plugin)

    def test_dispatch_message(self):
        """C{dispatch_message} calls a previously-registered message handler.
        """
        l = []
        def got_it(message):
            l.append(message)
            return "Heyo"
        self.registry.register_message("foo", got_it)
        msg = {"type": "foo", "value": "whatever"}
        self.assertEquals(self.registry.dispatch_message(msg), "Heyo")
        self.assertEquals(l, [msg])

    def test_dispatch_nonexistent_message(self):
        """
        L{HandlerNotFoundError} is raised when a message handler can't be
        found.
        """
        msg = {"type": "foo", "value": "whatever"}
        self.assertRaises(HandlerNotFoundError,
                          self.registry.dispatch_message, msg)

    def test_register_message_registers_message_type_with_broker(self):
        """
        When register_plugin is called on a BrokerClientPluginRegistry, the
        broker is notified that the message type is now accepted.
        """
        result1 = self.registry.register_message("foo", lambda m: None)
        result2 = self.registry.register_message("bar", lambda m: None)
        def got_result(result):
            exchanger = self.broker_service.exchanger
            self.assertEquals(exchanger.get_client_accepted_message_types(),
                              ["bar", "foo"])
        return gather_results([result1, result2]).addCallback(got_result)

    def test_exchange_calls_exchanges(self):
        """
        The L{PluginRegistry.exchange} method calls C{exchange} on all
        plugins, if available.
        """
        plugin1 = SamplePlugin()
        self.assertFalse(hasattr(plugin1, "exchange"))

        exchange_plugin1 = ExchangePlugin()
        exchange_plugin2 = ExchangePlugin()

        self.registry.add(plugin1)
        self.registry.add(exchange_plugin1)
        self.registry.add(exchange_plugin2)
        self.registry.add(SamplePlugin())

        self.registry.exchange()
        self.assertEquals(exchange_plugin1.exchanged, 1)
        self.assertEquals(exchange_plugin2.exchanged, 1)

    def test_exchange_logs_errors_and_continues(self):
        self.log_helper.ignore_errors(ZeroDivisionError)
        plugin1 = SamplePlugin()
        plugin2 = ExchangePlugin()
        plugin1.exchange = lambda: 1/0
        self.registry.add(plugin1)
        self.registry.add(plugin2)

        self.registry.exchange()
        self.assertEquals(plugin2.exchanged, 1)
        self.assertTrue("ZeroDivisionError" in self.logfile.getvalue())


def assertReceivesMessages(test_case, broker_plugin, broker_service, remote):
    """
    Assert (with the given C{test_case}) that the given C{broker_plugin} is
    correctly receiving messages sent by the given C{broker_service} when
    registered with the given C{remote}.

    @return: A deferred that you should return from your test case.
    """
    final_result = Deferred()
    broker_plugin.registry.register_message("foo", final_result.callback)

    result = remote.register_plugin(broker_plugin.bus_name,
                                    broker_plugin.object_path)

    def registered(result):
        transport = broker_service.transport
        transport.responses.append([{"type": "foo", "value": 42}])
        return broker_service.exchanger.exchange()
    result.addCallback(registered)

    def ready(message):
        test_case.assertEquals(message, {"type": "foo", "value": 42})

    final_result.addCallback(ready)
    return final_result


class MyBrokerPlugin(BrokerPlugin):
    bus_name = "my.service"
    object_path = "/my/service"

    ping = method(bus_name)(BrokerPlugin.ping)
    exit = method(bus_name)(BrokerPlugin.exit)
    message = method(bus_name)(BrokerPlugin.message)


class BrokerPluginTests(LandscapeIsolatedTest):
    """Tests for L{BrokerPlugin}."""

    helpers = [RemoteBrokerHelper]

    def setUp(self):
        super(BrokerPluginTests, self).setUp()
        self.registry = BrokerClientPluginRegistry(self.remote)

    def test_message_receiving(self):
        """
        BrokerPlugins can receive messages via Broker. Really this is a test
        for L{assertReceivesMessages}.
        """
        plugin = MyBrokerPlugin(self.broker_service.bus, self.registry)
        return assertReceivesMessages(self, plugin, self.broker_service,
                                      self.remote)

    def test_message_found(self):
        """
        When a message handler is found and dispatched, C{message} returns
        True.
        """
        l = []
        self.registry.register_message("foo", l.append)
        broker_plugin = MyBrokerPlugin(self.broker_service.bus, self.registry)
        msg = {"type": "foo", "value": "x"}
        array = map(ord, dumps(msg))
        self.assertEquals(broker_plugin.dispatch_message(array), True)
        self.assertEquals(l, [msg])

    def test_message_not_found(self):
        """
        When a message handler is not found for a type of message, {message}
        returns False.
        """
        broker_plugin = MyBrokerPlugin(self.broker_service.bus, self.registry)
        msg = {"type": "foo", "value": "x"}
        array = map(ord, dumps(msg))
        self.assertEquals(broker_plugin.dispatch_message(array), False)

    def test_exchange_notification_calls_exchange(self):
        """
        When the L{Broker} notifies the L{MonitorDBusObject} that an
        exchange is about to happen, the plugins' C{exchange} methods
        gets called.
        """
        exchange_plugin1 = ExchangePlugin()
        exchange_plugin2 = ExchangePlugin()
        self.registry.add(exchange_plugin1)
        self.registry.add(exchange_plugin2)

        broker_plugin = MyBrokerPlugin(self.broker_service.bus, self.registry)
        self.broker_service.reactor.fire("impending-exchange")

        d = gather_results([exchange_plugin1.wait_for_exchange(),
                            exchange_plugin2.wait_for_exchange()])
        d.addCallback(self.assertEquals, [None, None])
        return d
