import unittest

from twisted.internet.defer import Deferred

from landscape.lib import testing
from landscape.lib.plugin import PluginRegistry


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


class PluginTest(testing.FSTestCase, testing.TwistedTestCase,
                 unittest.TestCase):

    def setUp(self):
        super(PluginTest, self).setUp()
        self.registry = PluginRegistry()

    def test_register_plugin(self):
        sample_plugin = SamplePlugin()
        self.registry.add(sample_plugin)
        self.assertEqual(sample_plugin.registered, [self.registry])

    def test_get_plugins(self):
        plugin1 = SamplePlugin()
        plugin2 = SamplePlugin()
        self.registry.add(plugin1)
        self.registry.add(plugin2)
        self.assertEqual(self.registry.get_plugins()[-2:], [plugin1, plugin2])

    def test_get_named_plugin(self):
        """
        If a plugin has a C{plugin_name} attribute, it is possible to look it
        up by name after adding it to the L{Monitor}.
        """
        plugin = SamplePlugin()
        self.registry.add(plugin)
        self.assertEqual(self.registry.get_plugin("sample"), plugin)
