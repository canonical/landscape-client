from landscape.client.tests.helpers import LandscapeTest
from landscape.client.patch import UpgradeManager

from landscape.client.upgraders import monitor


class TestMonitorUpgraders(LandscapeTest):

    def test_monitor_upgrade_manager(self):
        self.assertEqual(type(monitor.upgrade_manager), UpgradeManager)
