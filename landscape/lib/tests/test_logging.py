import logging
import unittest

from landscape.lib.logging import init_app_logging
from landscape.lib.logging import LoggingAttributeError
from landscape.lib.logging import rotate_logs
from landscape.lib.testing import FSTestCase


class RotateLogsTest(FSTestCase, unittest.TestCase):
    def test_log_rotation(self):
        logging.getLogger().addHandler(logging.FileHandler(self.makeFile()))
        # Store the initial set of handlers
        original_streams = [
            handler.stream
            for handler in logging.getLogger().handlers
            if isinstance(handler, logging.FileHandler)
        ]
        rotate_logs()
        new_streams = [
            handler.stream
            for handler in logging.getLogger().handlers
            if isinstance(handler, logging.FileHandler)
        ]

        for stream in new_streams:
            self.assertTrue(stream not in original_streams)

    def test_wrong_log_level(self):
        tmpdir = self.makeDir()
        with self.assertRaises(LoggingAttributeError) as exp:
            init_app_logging(tmpdir, "'INFO'")
        self.assertTrue(
            "Unknown level \"'INFO'\", conversion to "
            "logging code was \"Level 'INFO'\"" in str(exp.exception),
        )
