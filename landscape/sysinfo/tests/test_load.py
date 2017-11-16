import unittest

import mock

from landscape.lib.testing import TwistedTestCase
from landscape.sysinfo.sysinfo import SysInfoPluginRegistry
from landscape.sysinfo.load import Load


class LoadTest(TwistedTestCase, unittest.TestCase):

    def setUp(self):
        super(LoadTest, self).setUp()
        self.load = Load()
        self.sysinfo = SysInfoPluginRegistry()
        self.sysinfo.add(self.load)

    def test_run_returns_succeeded_deferred(self):
        self.assertIs(None, self.successResultOf(self.load.run()))

    @mock.patch("os.getloadavg", return_value=(1.5, 0, 0))
    def test_run_adds_header(self, mock_getloadavg):
        self.load.run()

        mock_getloadavg.assert_called_once_with()
        self.assertEqual(self.sysinfo.get_headers(),
                         [("System load", "1.5")])
