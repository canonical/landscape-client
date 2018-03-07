import unittest

from landscape.lib.testing import TwistedTestCase
from landscape.sysinfo.sysinfo import SysInfoPluginRegistry
from landscape.sysinfo.landscapelink import LandscapeLink


class LandscapeLinkTest(TwistedTestCase, unittest.TestCase):

    def setUp(self):
        super(LandscapeLinkTest, self).setUp()
        self.landscape_link = LandscapeLink()
        self.sysinfo = SysInfoPluginRegistry()
        self.sysinfo.add(self.landscape_link)

    def test_run_returns_succeeded_deferred(self):
        self.assertIs(None, self.successResultOf(self.landscape_link.run()))

    def test_run_adds_footnote(self):
        self.landscape_link.run()
        self.assertEqual(
            self.sysinfo.get_footnotes(),
            ["Graph this data and manage this system at:\n"
             "    https://landscape.canonical.com/"])
