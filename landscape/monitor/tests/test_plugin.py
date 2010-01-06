from landscape.tests.helpers import LandscapeTest, MonitorHelper
from landscape.monitor.plugin import MonitorPlugin


class MonitorPluginTest(LandscapeTest):

    helpers = [MonitorHelper]

    def test_without_persist_name(self):
        """
        By default a L{MonitorPlugin} doesn't have a C{_persist} attribute.
        """
        plugin = MonitorPlugin()
        self.assertFalse(hasattr(plugin, "_persist"))

    def test_with_persist_name(self):
        """
        When plugins providea C{persist_name} attribute, they get a persist
        object set at C{_persist} which is rooted at the name specified.
        """
        plugin = MonitorPlugin()
        plugin.persist_name = "wubble"
        plugin.register(self.monitor)
        self.assertTrue(hasattr(plugin, "_persist"))
        plugin._persist.set("hi", "there")
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
