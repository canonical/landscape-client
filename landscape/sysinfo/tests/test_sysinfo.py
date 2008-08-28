from cStringIO import StringIO
from logging import getLogger, StreamHandler

from twisted.internet.defer import Deferred, succeed, fail

from landscape.sysinfo.sysinfo import SysInfoPluginRegistry, format_sysinfo
from landscape.plugin import PluginRegistry
from landscape.tests.helpers import LandscapeTest


class SysInfoPluginRegistryTest(LandscapeTest):

    def setUp(self):
        super(SysInfoPluginRegistryTest, self).setUp()
        self.sysinfo = SysInfoPluginRegistry()
        self.sysinfo_logfile = StringIO()
        self.handler = StreamHandler(self.sysinfo_logfile)
        self.logger = getLogger("landscape-sysinfo")
        self.logger.addHandler(self.handler)

    def tearDown(self):
        super(SysInfoPluginRegistryTest, self).tearDown()
        self.logger.removeHandler(self.handler)

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

    def test_add_same_header_twice(self):
        self.sysinfo.add_header("Header1", "Value1")
        self.sysinfo.add_header("Header2", "Value2")
        self.sysinfo.add_header("Header3", "Value3")
        self.sysinfo.add_header("Header2", "Value4")
        self.assertEquals(self.sysinfo.get_headers(),
                          [("Header1", "Value1"),
                           ("Header2", "Value4"),
                           ("Header3", "Value3")])

    def test_add_header_with_none_value(self):
        self.sysinfo.add_header("Header1", "Value1")
        self.sysinfo.add_header("Header2", None)
        self.sysinfo.add_header("Header3", "Value3")
        self.assertEquals(self.sysinfo.get_headers(),
                          [("Header1", "Value1"),
                           ("Header3", "Value3")])
        self.sysinfo.add_header("Header2", "Value2")
        self.assertEquals(self.sysinfo.get_headers(),
                          [("Header1", "Value1"),
                           ("Header2", "Value2"),
                           ("Header3", "Value3")])

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

    def test_plugins_run_after_synchronous_error(self):
        """
        Even when a plugin raises a synchronous error, other plugins will
        continue to be run.
        """
        self.log_helper.ignore_errors(ZeroDivisionError)
        plugins_what_run = []
        class BadPlugin(object):
            def register(self, registry):
                pass
            def run(self):
                plugins_what_run.append(self)
                1/0
        class GoodPlugin(object):
            def register(self, registry):
                pass
            def run(self):
                plugins_what_run.append(self)
                return succeed(None)
        plugin1 = BadPlugin()
        plugin2 = GoodPlugin()
        self.sysinfo.add(plugin1)
        self.sysinfo.add(plugin2)
        self.sysinfo.run()
        self.assertEquals(plugins_what_run, [plugin1, plugin2])
        log = self.sysinfo_logfile.getvalue()
        message = "BadPlugin plugin raised an exception."
        self.assertIn(message, log)
        self.assertIn("1/0", log)
        self.assertIn("ZeroDivisionError", log)
        self.assertEquals(
            self.sysinfo.get_notes(),
            [message + "  See ~/.landscape-sysinfo.log for information."])

    def test_asynchronous_errors_logged(self):
        self.log_helper.ignore_errors(ZeroDivisionError)
        class BadPlugin(object):
            def register(self, registry):
                pass
            def run(self):
                return fail(ZeroDivisionError("yay"))
        plugin = BadPlugin()
        self.sysinfo.add(plugin)
        self.sysinfo.run()
        log = self.sysinfo_logfile.getvalue()
        message = "BadPlugin plugin raised an exception."
        self.assertIn(message, log)
        self.assertIn("ZeroDivisionError: yay", log)
        self.assertEquals(
            self.sysinfo.get_notes(),
            [message + "  See ~/.landscape-sysinfo.log for information."])


class FormatTest(LandscapeTest):

    def test_no_headers(self):
        output = format_sysinfo([])
        self.assertEquals(output, "")

    def test_one_header(self):
        output = format_sysinfo([("Header", "Value")])
        self.assertEquals(output, "Header: Value")

    def test_parallel_headers_with_just_enough_space(self):
        output = format_sysinfo([("Header1", "Value1"),
                                 ("Header2", "Value2")], width=34)
        self.assertEquals(output, "Header1: Value1   Header2: Value2")

    def test_stacked_headers_which_barely_doesnt_fit(self):
        output = format_sysinfo([("Header1", "Value1"),
                                 ("Header2", "Value2")], width=33)
        self.assertEquals(output, "Header1: Value1\nHeader2: Value2")

    def test_stacked_headers_with_clearly_insufficient_space(self):
        output = format_sysinfo([("Header1", "Value1"),
                                 ("Header2", "Value2")], width=1)
        self.assertEquals(output, "Header1: Value1\n"
                                  "Header2: Value2")

    def test_indent_headers_in_parallel_with_just_enough_space(self):
        output = format_sysinfo([("Header1", "Value1"),
                                 ("Header2", "Value2")], indent=">>", width=36)
        self.assertEquals(output, ">>Header1: Value1   Header2: Value2")

    def test_indent_headers_stacked_which_barely_doesnt_fit(self):
        output = format_sysinfo([("Header1", "Value1"),
                                 ("Header2", "Value2")], indent=">>", width=35)
        self.assertEquals(output, ">>Header1: Value1\n"
                                  ">>Header2: Value2")

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

    def test_one_note(self):
        self.assertEquals(format_sysinfo(notes=["Something's wrong!"]),
                          "=> Something's wrong!")

    def test_more_notes(self):
        self.assertEquals(format_sysinfo(notes=["Something's wrong",
                                                "You should look at it",
                                                "Really"]),
                          "=> Something's wrong\n"
                          "=> You should look at it\n"
                          "=> Really")

    def test_indented_notes(self):
        self.assertEquals(format_sysinfo(notes=["Something's wrong",
                                                "You should look at it",
                                                "Really"], indent=">>"),
                          ">>=> Something's wrong\n"
                          ">>=> You should look at it\n"
                          ">>=> Really")

    def test_header_and_note(self):
        self.assertEquals(format_sysinfo(headers=[("Header", "Value")],
                                         notes=["Note"]),
                          "Header: Value\n"
                          "\n" 
                          "=> Note")

    def test_one_footnote(self):
        # Pretty dumb.
        self.assertEquals(format_sysinfo(footnotes=["Graphs at http://..."]),
                          "Graphs at http://...")

    def test_more_footnotes(self):
        # Still dumb.
        self.assertEquals(format_sysinfo(footnotes=["Graphs at http://...",
                                                    "Lunch at ..."]),
                          "Graphs at http://...\n"
                          "Lunch at ...")

    def test_indented_footnotes(self):
        # Barely more interesting.
        self.assertEquals(format_sysinfo(footnotes=["Graphs at http://...",
                                                    "Lunch at ..."],
                                         indent=">>"),
                          ">>Graphs at http://...\n"
                          ">>Lunch at ...")

    def test_header_and_footnote(self):
        # Warming up.
        self.assertEquals(format_sysinfo(headers=[("Header", "Value")],
                                         footnotes=["Footnote"]),
                          "Header: Value\n"
                          "\n"
                          "Footnote"
                          )

    def test_header_note_and_footnote(self):
        # Nice.
        self.assertEquals(format_sysinfo(headers=[("Header", "Value")],
                                         notes=["Note"],
                                         footnotes=["Footnote"]),
                          "Header: Value\n"
                          "\n" 
                          "=> Note\n"
                          "\n"
                          "Footnote"
                          )

    def test_indented_headers_notes_and_footnotes(self):
        # Hot!
        self.assertEquals(format_sysinfo(headers=[("Header1", "Value1"),
                                                  ("Header2", "Value2"),
                                                  ("Header3", "Value3")],
                                         notes=["Note1", "Note2"],
                                         footnotes=["Footnote1", "Footnote2"],
                                         indent="  ",
                                         width=36),
                          "  Header1: Value1   Header3: Value3\n"
                          "  Header2: Value2\n"
                          "\n" 
                          "  => Note1\n"
                          "  => Note2\n"
                          "\n"
                          "  Footnote1\n"
                          "  Footnote2"
                          )
