from landscape.sysinfo.sysinfo import SysInfoPluginRegistry
from landscape.sysinfo.load import Load
from landscape.tests.helpers import LandscapeTest


class LoadTest(LandscapeTest):

    def setUp(self):
        super(LoadTest, self).setUp()
        self.load = Load()
        self.sysinfo = SysInfoPluginRegistry()
        self.sysinfo.add(self.load)

    def test_run_returns_succeeded_deferred(self):
        self.assertIs(None, self.successResultOf(self.load.run()))

    def test_run_adds_header(self):
        mock = self.mocker.replace("os.getloadavg")
        mock()
        self.mocker.result((1.5, 0, 0))
        self.mocker.replay()

        self.load.run()

        self.assertEqual(self.sysinfo.get_headers(),
                         [("System load", "1.5")])
