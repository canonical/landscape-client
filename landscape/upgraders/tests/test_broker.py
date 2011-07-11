from landscape.tests.helpers import LandscapeTest
from landscape.patch import UpgradeManager

from landscape.upgraders import broker


class TestBrokerUpgraders(LandscapeTest):

    def test_broker_upgrade_manager(self):
        self.assertEqual(type(broker.upgrade_manager), UpgradeManager)
