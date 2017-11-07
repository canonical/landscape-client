from __future__ import absolute_import

import logging
import unittest

from landscape.lib.testing import FSTestCase
from landscape.lib.logging import rotate_logs


class RotateLogsTest(FSTestCase, unittest.TestCase):

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
