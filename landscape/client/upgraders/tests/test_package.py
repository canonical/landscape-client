from landscape.client.tests.helpers import LandscapeTest
from landscape.client.patch import SQLiteUpgradeManager

from landscape.client.upgraders import package


class TestPackageUpgraders(LandscapeTest):

    def test_package_upgrade_manager(self):
        self.assertEqual(type(package.upgrade_manager), SQLiteUpgradeManager)
