from landscape.sysinfo.sysinfo import SysInfoPluginRegistry
from landscape.plugin import PluginRegistry
from landscape.tests.helpers import LandscapeTest
from twisted.internet.defer import Deferred


class SysInfoPluginRegistryTest(LandscapeTest):

    def setUp(self):
        super(SysInfoPluginRegistryTest, self).setUp()
        self.sysinfo = SysInfoPluginRegistry()

    def test_is_plugin_registry(self):
        self.assertTrue(isinstance(self.sysinfo, PluginRegistry))

    def test_add_and_get_headers(self):
        self.sysinfo.add_header("Memory usage", "65%")
        self.sysinfo.add_header("Swap usage", "None")
        self.assertEquals(
            self.sysinfo.get_headers(),
            [("Memory usage", "65%"), ("Swap usage", "None")])

    def test_add_and_get_notes(self):
        self.sysinfo.add_note("Your laptop is burning!")
        self.sysinfo.add_note("Oh, your house too, btw.")
        self.assertEquals(
            self.sysinfo.get_notes(),
            ["Your laptop is burning!", "Oh, your house too, btw."])

    def test_run(self):
        class Plugin(object):
            def __init__(self, deferred):
                self._deferred = deferred
            def register(self, registry):
                pass
            def run(self):
                return self._deferred

        plugin_deferred1 = Deferred()
        plugin_deferred2 = Deferred()

        plugin1 = Plugin(plugin_deferred1)
        plugin2 = Plugin(plugin_deferred2)

        self.sysinfo.add(plugin1)
        self.sysinfo.add(plugin2)

        def check_result(result):
            self.assertEquals(result, [123, 456])

        deferred = self.sysinfo.run()
        deferred.addBoth(check_result)

        self.assertEquals(deferred.called, False)
        plugin_deferred1.callback(123)
        self.assertEquals(deferred.called, False)
        plugin_deferred2.callback(456)
        self.assertEquals(deferred.called, True)
