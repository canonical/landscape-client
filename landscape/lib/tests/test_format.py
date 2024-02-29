import unittest

from landscape.lib.format import expandvars
from landscape.lib.format import format_delta
from landscape.lib.format import format_object
from landscape.lib.format import format_percent


def function():
    pass


class FormatObjectTest(unittest.TestCase):
    def test_format_instance(self):
        self.assertEqual(
            format_object(self),
            "landscape.lib.tests.test_format.FormatObjectTest",
        )

    def method(self):
        pass

    def test_format_method(self):
        self.assertEqual(
            format_object(self.method),
            ("landscape.lib.tests.test_format" ".FormatObjectTest.method()"),
        )

    def test_format_function(self):
        self.assertEqual(
            format_object(function),
            "landscape.lib.tests.test_format.function()",
        )

    # FIXME Write tests to make sure that inner functions render
    # usefully.


class FormatDeltaTest(unittest.TestCase):
    def test_format_float(self):
        self.assertEqual(format_delta(0.0), "0.00s")
        self.assertEqual(format_delta(47.16374), "47.16s")
        self.assertEqual(format_delta(100.0), "100.00s")

    def test_format_int(self):
        self.assertEqual(format_delta(0), "0.00s")
        self.assertEqual(format_delta(47), "47.00s")
        self.assertEqual(format_delta(100), "100.00s")

    def test_format_none(self):
        self.assertEqual(format_delta(None), "0.00s")


class FormatPercentTest(unittest.TestCase):
    def test_format_float(self):
        self.assertEqual(format_percent(0.0), "0.00%")
        self.assertEqual(format_percent(47.16374), "47.16%")
        self.assertEqual(format_percent(100.0), "100.00%")

    def test_format_int(self):
        self.assertEqual(format_percent(0), "0.00%")
        self.assertEqual(format_percent(47), "47.00%")
        self.assertEqual(format_percent(100), "100.00%")

    def test_format_none(self):
        self.assertEqual(format_percent(None), "0.00%")


class ExpandVarsTest(unittest.TestCase):
    def test_expand_without_offset_and_length(self):
        self.assertEqual(
            expandvars("${serial}", serial="f315cab5"),
            "f315cab5",
        )
        self.assertEqual(
            expandvars("before:${Serial}", serial="f315cab5"),
            "before:f315cab5",
        )
        self.assertEqual(
            expandvars("${serial}:after", serial="f315cab5"),
            "f315cab5:after",
        )
        self.assertEqual(
            expandvars("be$fore:${serial}:after", serial="f315cab5"),
            "be$fore:f315cab5:after",
        )

    def test_expand_with_offset(self):
        self.assertEqual(
            expandvars("${serial:7}", serial="01234567890abcdefgh"),
            "7890abcdefgh",
        )
        self.assertEqual(
            expandvars("before:${SERIAL:7}", serial="01234567890abcdefgh"),
            "before:7890abcdefgh",
        )
        self.assertEqual(
            expandvars("${serial:7}:after", serial="01234567890abcdefgh"),
            "7890abcdefgh:after",
        )
        self.assertEqual(
            expandvars(
                "be$fore:${serial:7}:after",
                serial="01234567890abcdefgh",
            ),
            "be$fore:7890abcdefgh:after",
        )

    def test_expand_with_offset_and_length(self):
        self.assertEqual(
            expandvars("${serial:7:0}", serial="01234567890abcdefgh"),
            "",
        )
        self.assertEqual(
            expandvars("before:${serial:7:2}", serial="01234567890abcdefgh"),
            "before:78",
        )
        self.assertEqual(
            expandvars("${serial:7:2}:after", serial="01234567890abcdefgh"),
            "78:after",
        )
        self.assertEqual(
            expandvars(
                "be$fore:${serial:7:2}:after",
                serial="01234567890abcdefgh",
            ),
            "be$fore:78:after",
        )

    def test_expand_multiple(self):
        self.assertEqual(
            expandvars(
                "${model:8:7}-${serial:0:8}",
                model="generic-classic",
                serial="f315cab5-ba74-4d3c-be85-713406455773",
            ),
            "classic-f315cab5",
        )

    def test_expand_offset_longer_than_substitute(self):
        self.assertEqual(
            expandvars("${serial:50}", serial="01234567890abcdefgh"),
            "",
        )

    def test_expand_length_longer_than_substitute(self):
        self.assertEqual(
            expandvars("${serial:1:100}", serial="01234567890abcdefgh"),
            "1234567890abcdefgh",
        )

    def test_expand_with_non_string_substitutes(self):
        self.assertEqual(expandvars("${foo}", foo=42), "42")
        self.assertEqual(expandvars("${foo}.bar", foo=42), "42.bar")
