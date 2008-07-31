from twisted.internet.defer import Deferred

from landscape.sysinfo.sysinfo import SysInfoPluginRegistry, format_sysinfo
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
        self.assertEquals(self.sysinfo.get_notes(), [])
        self.assertEquals(self.sysinfo.get_footnotes(), [])

    def test_add_and_get_notes(self):
        self.sysinfo.add_note("Your laptop is burning!")
        self.sysinfo.add_note("Oh, your house too, btw.")
        self.assertEquals(
            self.sysinfo.get_notes(),
            ["Your laptop is burning!", "Oh, your house too, btw."])
        self.assertEquals(self.sysinfo.get_headers(), [])
        self.assertEquals(self.sysinfo.get_footnotes(), [])

    def test_add_and_get_footnotes(self):
        self.sysinfo.add_footnote("Graphs available at http://graph")
        self.sysinfo.add_footnote("Go! Go!")
        self.assertEquals(
            self.sysinfo.get_footnotes(),
            ["Graphs available at http://graph", "Go! Go!"])
        self.assertEquals(self.sysinfo.get_headers(), [])
        self.assertEquals(self.sysinfo.get_notes(), [])

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


class FormatTest(LandscapeTest):

    def test_no_headers(self):
        output = format_sysinfo([])
        self.assertEquals(output, "")

    def test_one_header(self):
        output = format_sysinfo([("Header", "Value")])
        self.assertEquals(output, "Header: Value")

    def test_parallel_headers(self):
        output = format_sysinfo([("Header1", "Value1"),
                                 ("Header2", "Value2")])
        self.assertEquals(output, "Header1: Value1   Header2: Value2")

    def test_stacked_headers_with_insufficient_space(self):
        output = format_sysinfo([("Header1", "Value1"),
                                 ("Header2", "Value2")], width=1)
        self.assertEquals(output, "Header1: Value1\nHeader2: Value2")

    def test_parallel_and_stacked_headers(self):
        headers = [("Header%d" % i, "Value%d" % i) for i in range(1, 6)]
        output = format_sysinfo(headers)
        self.assertEquals(output,
            "Header1: Value1   Header3: Value3   Header5: Value5\n"
            "Header2: Value2   Header4: Value4")

    def test_value_alignment(self):
        output = format_sysinfo([("Header one", "Value one"),
                                 ("Header2", "Value2"),
                                 ("Header3", "Value3"),
                                 ("Header4", "Value4"),
                                 ("Header5", "Value five")], width=45)
        # These headers and values were crafted to cover several cases:
        #
        # - Header padding (Header2 and Header3)
        # - Value padding (Value2)
        # - Lack of value padding due to a missing last column (Value3)
        # - Lack of value padding due to being a last column (Value4)
        #
        self.assertEquals(output,
                          "Header one: Value one   Header4: Value4\n"
                          "Header2:    Value2      Header5: Value five\n"
                          "Header3:    Value3")
