from landscape.lib.persist import Persist
from landscape.tests.helpers import LandscapeTest
from landscape.patch import SQLiteUpgradeManager

from landscape.upgraders import package


class TestPackageUpgraders(LandscapeTest):

    def test_package_upgrade_manager(self):
        self.assertEquals(type(package.upgrade_manager), SQLiteUpgradeManager)
