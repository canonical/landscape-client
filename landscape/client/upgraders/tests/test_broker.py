from landscape.client.tests.helpers import LandscapeTest
from landscape.client.patch import UpgradeManager

from landscape.client.upgraders import broker


class TestBrokerUpgraders(LandscapeTest):

    def test_broker_upgrade_manager(self):
        self.assertEqual(type(broker.upgrade_manager), UpgradeManager)
