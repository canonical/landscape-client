from landscape.lib.persist import Persist
from landscape.tests.helpers import LandscapeTest
from landscape.patch import UpgradeManager

from landscape.upgraders import monitor


class TestMonitorUpgraders(LandscapeTest):

    def test_monitor_upgrade_manager(self):
        self.assertEquals(type(monitor.upgrade_manager), UpgradeManager)
