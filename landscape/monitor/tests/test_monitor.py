from twisted.internet.defer import Deferred, succeed

from landscape.schema import Message, Int
from landscape.monitor.monitor import (
    MonitorPluginRegistry, MonitorDBusObject, MonitorPlugin, DataWatcher)
from landscape.lib.persist import Persist
from landscape.lib.dbus_util import get_object
from landscape.lib.twisted_util import gather_results
from landscape.tests.test_plugin import SamplePlugin
from landscape.tests.helpers import (LandscapeTest, LandscapeIsolatedTest,
                                     RemoteBrokerHelper, MonitorHelper)
from landscape.tests.mocker import ANY


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


class MonitorTest(LandscapeTest):

    helpers = [MonitorHelper]

    def test_persist(self):
        self.monitor.persist.set("a", 1)
        self.assertEquals(self.monitor.persist.get("a"), 1)

    def test_flush_saves_persist(self):
        """L{Monitor.flush} saves any changes made to the persist database."""
        self.monitor.persist.set("a", 1)
        self.monitor.flush()

        persist = Persist()
        persist.load(self.monitor.persist_filename)
        self.assertEquals(persist.get("a"), 1)

    def test_exchange_calls_exchanges(self):
        """
        The L{Monitor.exchange} method calls C{exchange} on all
        plugins, if available.
        """
        plugin1 = SamplePlugin()
        self.assertFalse(hasattr(plugin1, "exchange"))

        exchange_plugin1 = ExchangePlugin()
        exchange_plugin2 = ExchangePlugin()

        self.monitor.add(plugin1)
        self.monitor.add(exchange_plugin1)
        self.monitor.add(exchange_plugin2)
        self.monitor.add(SamplePlugin())

        self.monitor.exchange()
        self.assertEquals(exchange_plugin1.exchanged, 1)
        self.assertEquals(exchange_plugin2.exchanged, 1)

    def test_exchange_logs_errors_and_continues(self):
        self.log_helper.ignore_errors(ZeroDivisionError)
        plugin1 = SamplePlugin()
        plugin2 = ExchangePlugin()
        plugin1.exchange = lambda: 1/0
        self.monitor.add(plugin1)
        self.monitor.add(plugin2)

        self.monitor.exchange()
        self.assertEquals(plugin2.exchanged, 1)
        self.assertTrue("ZeroDivisionError" in self.logfile.getvalue())

    def test_flush_after_exchange(self):
        """
        The L{Monitor.exchange} method flushes the monitor after
        C{exchange} on all plugins has been called.
        """
        class SamplePlugin(ExchangePlugin):
            def exchange(myself):
                self.monitor.persist.set("a", 1)
                super(SamplePlugin, myself).exchange()

        self.monitor.add(SamplePlugin())
        self.monitor.exchange()

        persist = Persist()
        persist.load(self.monitor.persist_filename)
        self.assertEquals(persist.get("a"), 1)

    def test_creating_loads_persist(self):
        filename = self.make_path()

        persist = Persist()
        persist.set("a", "Hi there!")
        persist.save(filename)

        manager = MonitorPluginRegistry(self.reactor, self.remote,
                                        self.broker_service.config,
                                        None,
                                        persist=Persist(),
                                        persist_filename=filename)
        self.assertEquals(manager.persist.get("a"), "Hi there!")


class MonitorDBusObjectTest(LandscapeIsolatedTest):
    """Tests that use a monitor with a real DBUS service."""

    helpers = [RemoteBrokerHelper]

    def setUp(self):
        super(MonitorDBusObjectTest, self).setUp()
        persist = Persist()
        self.monitor = MonitorPluginRegistry(self.broker_service.reactor,
                                             self.remote,
                                             self.broker_service.config,
                                             self.broker_service.bus,
                                             persist)
        self.dbus_service = MonitorDBusObject(self.broker_service.bus,
                                              self.monitor)
        self.service = get_object(self.broker_service.bus,
                                  MonitorDBusObject.bus_name,
                                  MonitorDBusObject.object_path)

    def test_exchange_notification_calls_exchange(self):
        """
        When the L{Broker} notifies the L{MonitorDBusObject} that an
        exchange is about to happen, the plugins' C{exchange} methods
        gets called.
        """
        exchange_plugin1 = ExchangePlugin()
        exchange_plugin2 = ExchangePlugin()
        self.monitor.add(exchange_plugin1)
        self.monitor.add(exchange_plugin2)

        self.broker_service.reactor.fire("impending-exchange")

        d = gather_results([exchange_plugin1.wait_for_exchange(),
                            exchange_plugin2.wait_for_exchange()])
        d.addCallback(self.assertEquals, [None, None])
        return d

    def test_ping(self):
        result = self.service.ping()
        def got_result(result):
            self.assertEquals(result, True)
        return result.addCallback(got_result)

    def test_exit(self):
        result = Deferred()

        reactor = self.mocker.replace("twisted.internet.reactor")

        self.expect(reactor.stop()).call(lambda: result.callback(None))
        self.mocker.replay()

        self.service.exit()

        return result


class StubPluginUsingPlugin(MonitorPlugin):

    def run(self):
        pass

    def exchange(self):
        pass


class StubPluginRunIntervalNone(StubPluginUsingPlugin):

    run_interval = None

    def register(self, manager):
        super(StubPluginRunIntervalNone, self).register(manager)
        manager.reactor.call_on("foo", self.callee)

    def callee(self):
        pass


class StubPluginRespondingToChangedAcceptedTypes(StubPluginUsingPlugin):

    def __init__(self):
        self.called = []

    def register(self, manager):
        super(StubPluginRespondingToChangedAcceptedTypes,
              self).register(manager)
        self.call_on_accepted("some-type", self.exchange, True, param=10)

    def exchange(self, *args, **kwargs):
        self.called.append((args, kwargs))


class PluginTest(LandscapeTest):

    helpers = [MonitorHelper]

    def test_without_persist_name(self):
        plugin = StubPluginUsingPlugin()
        patched_reactor = self.mocker.patch(self.reactor)
        patched_reactor.call_every(5, plugin.run)
        self.mocker.replay()
        plugin.register(self.monitor)
        self.assertFalse(hasattr(plugin, "_persist"))

    def test_with_persist_name(self):
        """
        When plugins providea C{persist_name} attribute, they get a persist
        object set at C{_persist} which is rooted at the name specified.
        """
        plugin = StubPluginUsingPlugin()
        plugin.persist_name = "wubble"
        plugin.register(self.monitor)
        self.assertTrue(hasattr(plugin, "_persist"))
        plugin._persist.set("hi", "there")
        self.assertEquals(self.monitor.persist.get("wubble"), {"hi": "there"})

    def test_with_no_run_interval(self):
        plugin = StubPluginRunIntervalNone()
        patched_reactor = self.mocker.patch(self.reactor)

        # It *shouldn't* schedule run.
        patched_reactor.call_every(5, plugin.run)
        self.mocker.count(0)

        patched_reactor.call_on("foo", plugin.callee)
        self.mocker.replay()
        plugin.register(self.monitor)

    def test_call_on_accepted(self):
        """
        L{MonitorPlugin}-based plugins can provide a callable to call
        when a message type becomes accepted.
        """
        plugin = StubPluginRespondingToChangedAcceptedTypes()
        plugin.register(self.monitor)
        self.broker_service.reactor.fire(("message-type-acceptance-changed",
                                          "some-type"), True)
        self.assertEquals(plugin.called, [((True,), {"param": 10})])

    def test_call_on_accepted_when_unaccepted(self):
        """
        Notifications are only dispatched to plugins when types become
        accepted, not when they become unaccepted.
        """
        plugin = StubPluginRespondingToChangedAcceptedTypes()
        plugin.register(self.monitor)
        self.broker_service.reactor.fire(("message-type-acceptance-changed",
                                  "some-type"), False)
        self.assertEquals(plugin.called, [])


class StubDataWatchingPlugin(DataWatcher):

    persist_name = "ooga"
    message_type = "wubble"
    message_key = "wubblestuff"

    def __init__(self, data=None):
        self.data = data

    def get_data(self):
        return self.data


class DataWatcherTest(LandscapeTest):

    helpers = [MonitorHelper]

    def setUp(self):
        LandscapeTest.setUp(self)
        self.plugin = StubDataWatchingPlugin(1)
        self.plugin.register(self.monitor)
        self.mstore.add_schema(Message("wubble", {"wubblestuff": Int()}))

    def test_get_message(self):
        self.assertEquals(self.plugin.get_message(),
                          {"type": "wubble", "wubblestuff": 1})

    def test_get_message_unchanging(self):
        self.assertEquals(self.plugin.get_message(),
                          {"type": "wubble", "wubblestuff": 1})
        self.assertEquals(self.plugin.get_message(), None)

    def test_basic_exchange(self):
        # Is this really want we want to do?
        self.mstore.set_accepted_types(["wubble"])
        self.plugin.exchange()
        messages = self.mstore.get_pending_messages()
        self.assertEquals(messages[0]["type"], "wubble")
        self.assertEquals(messages[0]["wubblestuff"], 1)

    def test_unchanging_value(self):
        # Is this really want we want to do?
        self.mstore.set_accepted_types(["wubble"])
        self.plugin.exchange()
        self.plugin.exchange()
        messages = self.mstore.get_pending_messages()
        self.assertEquals(len(messages), 1)

    def test_urgent_exchange(self):
        """
        When exchange is called with an urgent argument set to True
        make sure it sends the message urgently.
        """
        remote_broker_mock = self.mocker.replace(self.remote)
        remote_broker_mock.send_message(ANY, urgent=True)
        self.mocker.result(succeed(None))
        self.mocker.replay()

        self.mstore.set_accepted_types(["wubble"])
        self.plugin.exchange(True)

    def test_no_message_if_not_accepted(self):
        """
        Don't add any messages at all if the broker isn't currently
        accepting their type.
        """
        self.mstore.set_accepted_types([])
        self.reactor.advance(self.monitor.step_size * 2)
        self.monitor.exchange()

        self.mstore.set_accepted_types(["wubble"])
        self.assertMessages(list(self.mstore.get_pending_messages()), [])
