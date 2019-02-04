from logging import getLogger, StreamHandler
import mock
import os
import unittest

from twisted.internet.defer import Deferred, succeed, fail

from landscape.lib.compat import StringIO
from landscape.lib.plugin import PluginRegistry
from landscape.lib.testing import HelperTestCase
from landscape.sysinfo.sysinfo import SysInfoPluginRegistry, format_sysinfo


class SysInfoPluginRegistryTest(HelperTestCase):

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
        self.assertEqual(
            self.sysinfo.get_headers(),
            [("Memory usage", "65%"), ("Swap usage", "None")])
        self.assertEqual(self.sysinfo.get_notes(), [])
        self.assertEqual(self.sysinfo.get_footnotes(), [])

    def test_add_same_header_twice(self):
        self.sysinfo.add_header("Header1", "Value1")
        self.sysinfo.add_header("Header2", "Value2")
        self.sysinfo.add_header("Header3", "Value3")
        self.sysinfo.add_header("Header2", "Value4")
        self.assertEqual(self.sysinfo.get_headers(),
                         [("Header1", "Value1"),
                          ("Header2", "Value2"),
                          ("Header2", "Value4"),
                          ("Header3", "Value3")])

    def test_add_header_with_none_value(self):
        self.sysinfo.add_header("Header1", "Value1")
        self.sysinfo.add_header("Header2", None)
        self.sysinfo.add_header("Header3", "Value3")
        self.assertEqual(self.sysinfo.get_headers(),
                         [("Header1", "Value1"),
                          ("Header3", "Value3")])
        self.sysinfo.add_header("Header2", "Value2")
        self.assertEqual(self.sysinfo.get_headers(),
                         [("Header1", "Value1"),
                          ("Header2", "Value2"),
                          ("Header3", "Value3")])

    def test_add_and_get_notes(self):
        self.sysinfo.add_note("Your laptop is burning!")
        self.sysinfo.add_note("Oh, your house too, btw.")
        self.assertEqual(
            self.sysinfo.get_notes(),
            ["Your laptop is burning!", "Oh, your house too, btw."])
        self.assertEqual(self.sysinfo.get_headers(), [])
        self.assertEqual(self.sysinfo.get_footnotes(), [])

    def test_add_and_get_footnotes(self):
        self.sysinfo.add_footnote("Graphs available at http://graph")
        self.sysinfo.add_footnote("Go! Go!")
        self.assertEqual(
            self.sysinfo.get_footnotes(),
            ["Graphs available at http://graph", "Go! Go!"])
        self.assertEqual(self.sysinfo.get_headers(), [])
        self.assertEqual(self.sysinfo.get_notes(), [])

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
            self.assertEqual(result, [123, 456])

        deferred = self.sysinfo.run()
        deferred.addBoth(check_result)

        self.assertEqual(deferred.called, False)
        plugin_deferred1.callback(123)
        self.assertEqual(deferred.called, False)
        plugin_deferred2.callback(456)
        self.assertEqual(deferred.called, True)

    plugin_exception_message = (
        "There were exceptions while processing one or more plugins. "
        "See %s/sysinfo.log for more information.")

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
                1 / 0

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
        self.assertEqual(plugins_what_run, [plugin1, plugin2])
        log = self.sysinfo_logfile.getvalue()
        message = "BadPlugin plugin raised an exception."
        self.assertIn(message, log)
        self.assertIn("1 / 0", log)
        self.assertIn("ZeroDivisionError", log)

        path = os.path.expanduser("~/.landscape")
        self.assertEqual(
            self.sysinfo.get_notes(),
            [self.plugin_exception_message % path])

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
        path = os.path.expanduser("~/.landscape")
        self.assertEqual(
            self.sysinfo.get_notes(),
            [self.plugin_exception_message % path])

    def test_multiple_exceptions_get_one_note(self):
        self.log_helper.ignore_errors(ZeroDivisionError)

        class RegularBadPlugin(object):

            def register(self, registry):
                pass

            def run(self):
                1 / 0

        class AsyncBadPlugin(object):

            def register(self, registry):
                pass

            def run(self):
                return fail(ZeroDivisionError("Hi"))

        plugin1 = RegularBadPlugin()
        plugin2 = AsyncBadPlugin()
        self.sysinfo.add(plugin1)
        self.sysinfo.add(plugin2)
        self.sysinfo.run()

        path = os.path.expanduser("~/.landscape")
        self.assertEqual(
            self.sysinfo.get_notes(),
            [self.plugin_exception_message % path])

    @mock.patch("os.getuid", return_value=0)
    def test_exception_running_as_privileged_user(self, uid_mock):
        """
        If a Plugin fails while running and the sysinfo binary is running with
        a uid of 0, Landscape sysinfo should write to the system logs
        directory.
        """

        class AsyncBadPlugin(object):

            def register(self, registry):
                pass

            def run(self):
                return fail(ZeroDivisionError("Hi"))

        self.log_helper.ignore_errors(ZeroDivisionError)

        plugin = AsyncBadPlugin()
        self.sysinfo.add(plugin)
        self.sysinfo.run()
        uid_mock.assert_called_with()

        path = "/var/log/landscape"
        self.assertEqual(
            self.sysinfo.get_notes(),
            [self.plugin_exception_message % path])


class FormatTest(unittest.TestCase):

    def test_no_headers(self):
        output = format_sysinfo([])
        self.assertEqual(output, "")

    def test_one_header(self):
        output = format_sysinfo([("Header", "Value")])
        self.assertEqual(output, "Header: Value")

    def test_parallel_headers_with_just_enough_space(self):
        output = format_sysinfo([("Header1", "Value1"),
                                 ("Header2", "Value2")], width=34)
        self.assertEqual(output, "Header1: Value1   Header2: Value2")

    def test_stacked_headers_which_barely_doesnt_fit(self):
        output = format_sysinfo([("Header1", "Value1"),
                                 ("Header2", "Value2")], width=33)
        self.assertEqual(output, "Header1: Value1\nHeader2: Value2")

    def test_stacked_headers_with_clearly_insufficient_space(self):
        output = format_sysinfo([("Header1", "Value1"),
                                 ("Header2", "Value2")], width=1)
        self.assertEqual(output,
                         "Header1: Value1\n"
                         "Header2: Value2")

    def test_indent_headers_in_parallel_with_just_enough_space(self):
        output = format_sysinfo([("Header1", "Value1"),
                                 ("Header2", "Value2")], indent=">>", width=36)
        self.assertEqual(output, ">>Header1: Value1   Header2: Value2")

    def test_indent_headers_stacked_which_barely_doesnt_fit(self):
        output = format_sysinfo([("Header1", "Value1"),
                                 ("Header2", "Value2")], indent=">>", width=35)
        self.assertEqual(output,
                         ">>Header1: Value1\n"
                         ">>Header2: Value2")

    def test_parallel_and_stacked_headers(self):
        headers = [("Header%d" % i, "Value%d" % i) for i in range(1, 6)]
        output = format_sysinfo(headers)
        self.assertEqual(
            output,
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
        self.assertEqual(output,
                         "Header one: Value one   Header4: Value4\n"
                         "Header2:    Value2      Header5: Value five\n"
                         "Header3:    Value3")

    def test_one_note(self):
        self.assertEqual(format_sysinfo(notes=["Something's wrong!"]),
                         "=> Something's wrong!")

    def test_more_notes(self):
        self.assertEqual(format_sysinfo(notes=["Something's wrong",
                                               "You should look at it",
                                               "Really"]),
                         "=> Something's wrong\n"
                         "=> You should look at it\n"
                         "=> Really")

    def test_indented_notes(self):
        self.assertEqual(format_sysinfo(notes=["Something's wrong",
                                               "You should look at it",
                                               "Really"], indent=">>"),
                         ">>=> Something's wrong\n"
                         ">>=> You should look at it\n"
                         ">>=> Really")

    def test_header_and_note(self):
        self.assertEqual(format_sysinfo(headers=[("Header", "Value")],
                                        notes=["Note"]),
                         "Header: Value\n"
                         "\n"
                         "=> Note")

    def test_one_footnote(self):
        # Pretty dumb.
        self.assertEqual(format_sysinfo(footnotes=["Graphs at http://..."]),
                         "Graphs at http://...")

    def test_more_footnotes(self):
        # Still dumb.
        self.assertEqual(format_sysinfo(footnotes=["Graphs at http://...",
                                                   "Lunch at ..."]),
                         "Graphs at http://...\n"
                         "Lunch at ...")

    def test_indented_footnotes(self):
        # Barely more interesting.
        self.assertEqual(format_sysinfo(footnotes=["Graphs at http://...",
                                                   "Lunch at ..."],
                                        indent=">>"),
                         ">>Graphs at http://...\n"
                         ">>Lunch at ...")

    def test_header_and_footnote(self):
        # Warming up.
        self.assertEqual(format_sysinfo(headers=[("Header", "Value")],
                                        footnotes=["Footnote"]),
                         "Header: Value\n"
                         "\n"
                         "Footnote"
                         )

    def test_header_note_and_footnote(self):
        # Nice.
        self.assertEqual(format_sysinfo(headers=[("Header", "Value")],
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
        self.assertEqual(format_sysinfo(headers=[("Header1", "Value1"),
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

    def test_wrap_long_notes(self):
        self.assertEqual(
            format_sysinfo(notes=[
                "I do believe that a very long note, such as one that is "
                "longer than about 50 characters, should wrap at the "
                "specified width."], width=50, indent="Z"),
            """\
Z=> I do believe that a very long note, such as
    one that is longer than about 50 characters,
    should wrap at the specified width.""")
