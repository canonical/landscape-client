from mock import ANY, Mock, patch

from landscape.lib.testing import LogKeeperHelper
from landscape.lib.schema import Int
from landscape.message_schemas.message import Message
from landscape.client.monitor.plugin import MonitorPlugin, DataWatcher
from landscape.client.tests.helpers import LandscapeTest, MonitorHelper


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
        self.assertEqual(self.monitor.persist.get("wubble"), {"hi": "there"})

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
        callback = Mock()
        plugin.call_on_accepted("type", callback, "foo", kwarg="bar")
        self.reactor.fire(("message-type-acceptance-changed", "type"), True)
        callback.assert_called_once_with("foo", kwarg="bar")

    def test_call_on_accepted_when_unaccepted(self):
        """
        Notifications are only dispatched to plugins when types become
        accepted, not when they become unaccepted.
        """
        plugin = MonitorPlugin()
        plugin.register(self.monitor)
        callback = (lambda: 1 / 0)
        plugin.call_on_accepted("type", callback)
        self.reactor.fire(("message-type-acceptance-changed", "type"), False)

    def test_resynchronize_with_global_scope(self):
        """
        If a 'resynchronize' event fires with global scope, we clear down the
        persist.
        """
        plugin = MonitorPlugin()
        plugin.persist_name = "wubble"
        plugin.register(self.monitor)
        plugin.persist.set("hi", "there")
        self.assertEqual(self.monitor.persist.get("wubble"), {"hi": "there"})
        self.reactor.fire("resynchronize")
        self.assertTrue(self.monitor.persist.get("wubble") is None)

    def test_resynchronize_with_provided_scope(self):
        """
        If a 'resynchronize' event fires with the provided scope, we clear down
        the persist.
        """
        plugin = MonitorPlugin()
        plugin.persist_name = "wubble"
        plugin.scope = "frujical"
        plugin.register(self.monitor)
        plugin.persist.set("hi", "there")
        self.assertEqual(self.monitor.persist.get("wubble"), {"hi": "there"})
        self.reactor.fire("resynchronize", scopes=["frujical"])
        self.assertTrue(self.monitor.persist.get("wubble") is None)

    def test_do_not_resynchronize_with_other_scope(self):
        """
        If a 'resynchronize' event fires with an irrelevant scope, we do
        nothing.
        """
        plugin = MonitorPlugin()
        plugin.persist_name = "wubble"
        plugin.scope = "frujical"
        plugin.register(self.monitor)
        plugin.persist.set("hi", "there")
        self.assertEqual(self.monitor.persist.get("wubble"), {"hi": "there"})
        self.reactor.fire("resynchronize", scopes=["chrutfup"])
        self.assertEqual(self.monitor.persist.get("wubble"), {"hi": "there"})


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
        self.assertEqual(self.plugin.get_message(),
                         {"type": "wubble", "wubblestuff": 1})

    def test_get_message_unchanging(self):
        self.assertEqual(self.plugin.get_message(),
                         {"type": "wubble", "wubblestuff": 1})
        self.assertEqual(self.plugin.get_message(), None)

    def test_basic_exchange(self):
        # Is this really want we want to do?
        self.mstore.set_accepted_types(["wubble"])
        self.plugin.exchange()
        messages = self.mstore.get_pending_messages()
        self.assertEqual(messages[0]["type"], "wubble")
        self.assertEqual(messages[0]["wubblestuff"], 1)
        self.assertIn("Queueing a message with updated data watcher info for "
                      "landscape.client.monitor.tests.test_plugin."
                      "StubDataWatchingPlugin.", self.logfile.getvalue())

    def test_unchanging_value(self):
        # Is this really want we want to do?
        self.mstore.set_accepted_types(["wubble"])
        self.plugin.exchange()
        self.plugin.exchange()
        messages = self.mstore.get_pending_messages()
        self.assertEqual(len(messages), 1)

    def test_urgent_exchange(self):
        """
        When exchange is called with an urgent argument set to True
        make sure it sends the message urgently.
        """
        with patch.object(self.remote, "send_message"):
            self.mstore.set_accepted_types(["wubble"])
            self.plugin.exchange(True)
            self.remote.send_message.assert_called_once_with(
                ANY, ANY, urgent=True)

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
