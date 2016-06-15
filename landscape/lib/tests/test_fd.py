"""Tests for L{landscape.lib.fd}"""

import os
import resource
from mock import Mock, patch, call

from landscape.lib.fd import clean_fds
from landscape.tests.helpers import LandscapeTest


class CleanFDsTests(LandscapeTest):
    """Tests for L{clean_fds}."""

    def mock_rlimit(self, limit):
        return patch.object(resource, "getrlimit", return_value=[None, limit])


    def assert_rlimit(self, patchee):
        patchee.assert_called_once_with(resource.RLIMIT_NOFILE)

    @patch("os.close")
    def test_clean_fds_rlimit(self, close_mock):
        """
        L{clean_fds} cleans all non-stdio file descriptors up to the process
        limit for file descriptors.
        """
        with self.mock_rlimit(limit=10) as getrlimit_mock:
            clean_fds()
            
        calls = [call(i) for i in range(3, 10)]
        close_mock.assert_has_calls(calls, any_order=True)
        self.assert_rlimit(getrlimit_mock)

    def test_clean_fds_sanity(self):
        """
        If the process limit for file descriptors is very high (> 4096), then
        we only close 4096 file descriptors.
        """
        closed_fds = []
        
        with patch.object(
                os, "close", side_effect=closed_fds.append) as close_mock:
            with self.mock_rlimit(limit=4100) as getrlimit_mock:
                clean_fds()

        self.assert_rlimit(getrlimit_mock)

        expected_fds = range(3, 4096)
        calls = [call(i) for i in expected_fds]
        close_mock.assert_has_calls(calls, any_order=True)

        self.assertEqual(closed_fds, expected_fds)

    # def test_ignore_OSErrors(self):
    #     """
    #     If os.close raises an OSError, it is ignored and we continue to close
    #     the rest of the FDs.
    #     """
    #     self.mocker.order()
    #     self.mock_rlimit(10)

    #     closed_fds = []

    #     def remember_and_throw(fd):
    #         closed_fds.append(fd)
    #         raise OSError("Bad FD!")

    #     with patch.object(os, "close", side_effect=remember_and_throw):
    #         clean_fds()
        
    #     calls = [call(i) for i in range(3, 10)]
    #     close_mock.assert_has_calls(calls, any_order=True)


    #         close_mock = self.mocker.replace("os.close", passthrough=False)
    #     close_mock(ANY)
    #     self.mocker.count(7)
    #     self.mocker.call(remember_and_throw)

    #     self.mocker.replay()
    #     clean_fds()
    #     self.assertEqual(closed_fds, range(3, 10))

    # def test_dont_ignore_other_errors(self):
    #     """
    #     If other errors are raised from os.close, L{clean_fds} propagates them.
    #     """
    #     self.mocker.order()
    #     self.mock_rlimit(10)
    #     close_mock = self.mocker.replace("os.close", passthrough=False)
    #     close_mock(ANY)
    #     self.mocker.throw(MemoryError())

    #     self.mocker.replay()
    #     self.assertRaises(MemoryError, clean_fds)
