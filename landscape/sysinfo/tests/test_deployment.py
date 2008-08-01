from landscape.tests.helpers import LandscapeTest
from landscape.sysinfo.deployment import SysInfoConfiguration, ALL_PLUGINS
from landscape.sysinfo.load import Load


class DeploymentTest(LandscapeTest):

    def test_get_plugins(self):
        configuration = SysInfoConfiguration()
        configuration.load(["--sysinfo-plugins", "Load",
                            "-d", self.make_path()])
        plugins = configuration.get_plugins()
        self.assertEquals(len(plugins), 1)
        self.assertTrue(isinstance(plugins[0], Load))

    def test_get_all_plugins(self):
        configuration = SysInfoConfiguration()
        configuration.load(["--sysinfo-plugins", "ALL",
                            "-d", self.make_path()])
        plugins = configuration.get_plugins()
        self.assertEquals(len(plugins), len(ALL_PLUGINS))
