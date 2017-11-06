"""Tests for L{landscape.lib.fd}"""

import unittest

import resource
from mock import patch, call

from landscape.lib.fd import clean_fds


class CleanFDsTests(unittest.TestCase):
    """Tests for L{clean_fds}."""

    def mock_getrlimit(self, limit):
        """Return a context with getrlimit patched for testing."""
        return patch("resource.getrlimit", return_value=[None, limit])

    @patch("os.close")
    def test_clean_fds_rlimit(self, close_mock):
        """
        L{clean_fds} cleans all non-stdio file descriptors up to the process
        limit for file descriptors.
        """
        with self.mock_getrlimit(10) as getrlimit_mock:
            clean_fds()

        calls = [call(i) for i in range(3, 10)]
        close_mock.assert_has_calls(calls, any_order=True)
        getrlimit_mock.assert_called_once_with(resource.RLIMIT_NOFILE)

    def test_clean_fds_sanity(self):
        """
        If the process limit for file descriptors is very high (> 4096), then
        we only close 4096 file descriptors.
        """
        closed_fds = []

        with patch("os.close", side_effect=closed_fds.append) as close_mock:
            with self.mock_getrlimit(4100) as getrlimit_mock:
                clean_fds()

        getrlimit_mock.assert_called_once_with(resource.RLIMIT_NOFILE)

        expected_fds = list(range(3, 4096))
        calls = [call(i) for i in expected_fds]
        close_mock.assert_has_calls(calls, any_order=True)

        self.assertEqual(closed_fds, expected_fds)

    def test_ignore_OSErrors(self):
        """
        If os.close raises an OSError, it is ignored and we continue to close
        the rest of the FDs.
        """
        closed_fds = []

        def remember_and_throw(fd):
            closed_fds.append(fd)
            raise OSError("Bad FD!")

        with patch("os.close", side_effect=remember_and_throw) as close_mock:
            with self.mock_getrlimit(10) as getrlimit_mock:
                clean_fds()

        getrlimit_mock.assert_called_once_with(resource.RLIMIT_NOFILE)
        expected_fds = list(range(3, 10))
        calls = [call(i) for i in expected_fds]
        close_mock.assert_has_calls(calls, any_order=True)
        self.assertEqual(closed_fds, expected_fds)

    def test_dont_ignore_other_errors(self):
        """
        If other errors are raised from os.close, L{clean_fds} propagates them.
        """
        with patch("os.close", side_effect=MemoryError()):
            with self.mock_getrlimit(10):
                self.assertRaises(MemoryError, clean_fds)
