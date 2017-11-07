import logging

from landscape.log import rotate_logs
from landscape.tests.helpers import LandscapeTest


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
