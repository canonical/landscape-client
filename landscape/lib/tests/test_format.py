import unittest

from landscape.lib.format import format_object, format_delta, format_percent


def function():
    pass


class FormatObjectTest(unittest.TestCase):

    def test_format_instance(self):
        self.assertEqual(format_object(self),
                         "landscape.lib.tests.test_format.FormatObjectTest")

    def method(self):
        pass

    def test_format_method(self):
        self.assertEqual(format_object(self.method),
                         ("landscape.lib.tests.test_format"
                          ".FormatObjectTest.method()"))

    def test_format_function(self):
        self.assertEqual(format_object(function),
                         "landscape.lib.tests.test_format.function()")

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
