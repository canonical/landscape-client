import logging

from landscape.log import (format_object, format_delta, format_percent,
                           rotate_logs)
from landscape.tests.helpers import LandscapeTest


def function():
    pass


class FormatObjectTest(LandscapeTest):

    def test_format_instance(self):
        self.assertEquals(format_object(self),
                          "landscape.tests.test_log.FormatObjectTest")

    def method(self):
        pass

    def test_format_method(self):
        self.assertEquals(format_object(self.method),
                          "landscape.tests.test_log.FormatObjectTest.method()")

    def test_format_function(self):
        self.assertEquals(format_object(function),
                          "landscape.tests.test_log.function()")

    # FIXME Write tests to make sure that inner functions render
    # usefully.


class FormatDeltaTest(LandscapeTest):

    def test_format_float(self):
        self.assertEquals(format_delta(0.0), "0.00s")
        self.assertEquals(format_delta(47.16374), "47.16s")
        self.assertEquals(format_delta(100.0), "100.00s")

    def test_format_int(self):
        self.assertEquals(format_delta(0), "0.00s")
        self.assertEquals(format_delta(47), "47.00s")
        self.assertEquals(format_delta(100), "100.00s")

    def test_format_none(self):
        self.assertEquals(format_delta(None), "0.00s")


class FormatPercentTest(LandscapeTest):

    def test_format_float(self):
        self.assertEquals(format_percent(0.0), "0.00%")
        self.assertEquals(format_percent(47.16374), "47.16%")
        self.assertEquals(format_percent(100.0), "100.00%")

    def test_format_int(self):
        self.assertEquals(format_percent(0), "0.00%")
        self.assertEquals(format_percent(47), "47.00%")
        self.assertEquals(format_percent(100), "100.00%")

    def test_format_none(self):
        self.assertEquals(format_percent(None), "0.00%")


class RotateLogsTest(LandscapeTest):

    def test_log_rotation(self):
        logging.getLogger().addHandler(logging.FileHandler(self.makeFile()))
        # Store the initial set of handlers
        original_streams = [handler.stream for handler in
                            logging.getLogger().handlers if
                            isinstance(handler, logging.FileHandler)]
        rotate_logs()
        new_streams = [handler.stream for handler in
                       logging.getLogger().handlers if
                       isinstance(handler, logging.FileHandler)]

        for stream in new_streams:
            self.assertTrue(stream not in original_streams)
