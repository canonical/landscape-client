from twisted.internet.defer import succeed

from landscape.monitor.plugin import MonitorPlugin, DataWatcher
from landscape.schema import Message, Int
from landscape.tests.mocker import ANY
from landscape.tests.helpers import (
    LandscapeTest, MonitorHelper, LogKeeperHelper)


class MonitorPluginTest(LandscapeTest):

    helpers = [MonitorHelper]

    def test_without_persist_name(self):
        """
        By default a L{MonitorPlugin} doesn't have a C{_persist} attribute.
        """
        plugin = MonitorPlugin()
        plugin.register(self.monitor)
        self.assertIs(plugin.persist, None)

    def test_with_persist_name(self):
        """
        When plugins providea C{persist_name} attribute, they get a persist
        object set at C{_persist} which is rooted at the name specified.
        """
        plugin = MonitorPlugin()
        plugin.persist_name = "wubble"
        plugin.register(self.monitor)
        plugin.persist.set("hi", "there")
        self.assertEquals(self.monitor.persist.get("wubble"), {"hi": "there"})

    def test_with_no_run_interval(self):
        """
        If the C{run_interval} attribute of L{MonitorPlugin} is C{None}, its
        C{run} method won't get called by the reactor.
        """
        plugin = MonitorPlugin()
        plugin.run = lambda: 1 / 0
        plugin.run_interval = None
        plugin.register(self.monitor)
        self.reactor.advance(MonitorPlugin.run_interval)

    def test_call_on_accepted(self):
        """
        L{MonitorPlugin}-based plugins can provide a callable to call
        when a message type becomes accepted.
        """
        plugin = MonitorPlugin()
        plugin.register(self.monitor)
        callback = self.mocker.mock()
        callback("foo", kwarg="bar")
        self.mocker.replay()
        plugin.call_on_accepted("type", callback, "foo", kwarg="bar")
        self.reactor.fire(("message-type-acceptance-changed", "type"), True)

    def test_call_on_accepted_when_unaccepted(self):
        """
        Notifications are only dispatched to plugins when types become
        accepted, not when they become unaccepted.
        """
        plugin = MonitorPlugin()
        plugin.register(self.monitor)
        callback = lambda: 1 / 0
        plugin.call_on_accepted("type", callback)
        self.reactor.fire(("message-type-acceptance-changed", "type"), False)


class StubDataWatchingPlugin(DataWatcher):

    persist_name = "ooga"
    message_type = "wubble"
    message_key = "wubblestuff"

    def __init__(self, data=None):
        self.data = data

    def get_data(self):
        return self.data


class DataWatcherTest(LandscapeTest):

    helpers = [MonitorHelper, LogKeeperHelper]

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
        self.assertIn("Queueing a message with updated data watcher info for "
                      "landscape.monitor.tests.test_plugin.StubDataWatching"
                      "Plugin.", self.logfile.getvalue())

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
