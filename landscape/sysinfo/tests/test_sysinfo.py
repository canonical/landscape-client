from landscape.sysinfo.sysinfo import SysInfoPluginRegistry
from landscape.plugin import PluginRegistry
from landscape.tests.helpers import LandscapeTest


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
