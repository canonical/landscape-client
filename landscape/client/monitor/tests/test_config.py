from landscape.client.tests.helpers import LandscapeTest
from landscape.client.monitor.config import MonitorConfiguration, ALL_PLUGINS


class MonitorConfigurationTest(LandscapeTest):

    def setUp(self):
        super(MonitorConfigurationTest, self).setUp()
        self.config = MonitorConfiguration()

    def test_plugin_factories(self):
        """
        By default all plugins are enabled.
        """
        self.assertEqual(self.config.plugin_factories, ALL_PLUGINS)

    def test_plugin_factories_with_monitor_plugins(self):
        """
        The C{--monitor-plugins} command line option can be used to specify
        which plugins should be active.
        """
        self.config.load(["--monitor-plugins", "  ComputerInfo, LoadAverage "])
        self.assertEqual(
            self.config.plugin_factories, ["ComputerInfo", "LoadAverage"])

    def test_flush_interval(self):
        """
        The C{--flush-interval} command line option can be used to specify the
        flush interval.
        """
        self.config.load(["--flush-interval", "123"])
        self.assertEqual(self.config.flush_interval, 123)
