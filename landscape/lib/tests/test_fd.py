"""Tests for L{landscape.lib.fd}"""

import resource
from mock import Mock, patch, call
from landscape.tests.mocker import ANY

from landscape.lib.fd import clean_fds
from landscape.tests.helpers import LandscapeTest


class CleanFDsTests(LandscapeTest):
    """Tests for L{clean_fds}."""

    # def mock_rlimit(self, limit):
    #     getrlimit_mock = self.mocker.replace("resource.getrlimit")
    #     getrlimit_mock(resource.RLIMIT_NOFILE)
    #     self.mocker.result([None, limit])

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
        with self.mock_rlimit(10) as getrlimit_mock:
            clean_fds()
            
        calls = [call(i) for i in range(3, 10)]
        close_mock.assert_has_calls(calls, any_order=True)
        self.assert_rlimit(getrlimit_mock)
                


    # def test_clean_fds_sanity(self):
    #     """
    #     If the process limit for file descriptors is very high (> 4096), then
    #     we only close 4096 file descriptors.
    #     """
    #     self.mocker.order()
    #     self.mock_rlimit(4100)
    #     close_mock = self.mocker.replace("os.close", passthrough=False)
    #     closed_fds = []
    #     close_mock(ANY)
    #     self.mocker.call(closed_fds.append)
    #     self.mocker.count(4093)
    #     self.mocker.replay()
    #     clean_fds()
    #     self.assertEqual(closed_fds, range(3, 4096))

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

    #     close_mock = self.mocker.replace("os.close", passthrough=False)
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
