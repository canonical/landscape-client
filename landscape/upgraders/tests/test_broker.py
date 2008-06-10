from landscape.lib.persist import Persist
from landscape.tests.helpers import LandscapeTest
from landscape.patch import UpgradeManager

from landscape.upgraders import broker


class TestBrokerUpgraders(LandscapeTest):

    def test_broker_upgrade_manager(self):
        self.assertEquals(type(broker.upgrade_manager), UpgradeManager)
