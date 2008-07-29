from landscape.tests.helpers import LandscapeTest
from landscape.sysinfo.deployment import SysInfoConfiguration, ALL_PLUGINS
from landscape.sysinfo.dummy import Dummy


class DeploymentTest(LandscapeTest):

    def test_get_plugins(self):
        configuration = SysInfoConfiguration()
        configuration.load(["--sysinfo-plugins", "Dummy",
                            "-d", self.make_path()])
        plugins = configuration.get_plugins()
        self.assertEquals(len(plugins), 1)
        self.assertTrue(isinstance(plugins[0], Dummy))

    def test_get_all_plugins(self):
        configuration = SysInfoConfiguration()
        configuration.load(["--sysinfo-plugins", "ALL",
                            "-d", self.make_path()])
        plugins = configuration.get_plugins()
        self.assertEquals(len(plugins), len(ALL_PLUGINS))
