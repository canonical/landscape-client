from landscape.client.manager.store import ManagerStore

from landscape.client.tests.helpers import LandscapeTest, ManagerHelper


class ManagerTest(LandscapeTest):

    helpers = [ManagerHelper]

    def test_reactor(self):
        """
        A L{Manager} instance has a proper C{reactor} attribute.
        """
        self.assertIs(self.manager.reactor, self.reactor)

    def test_broker(self):
        """
        A L{Manager} instance has a proper C{broker} attribute referencing
        a connected L{RemoteBroker}.
        """
        return self.assertSuccess(self.manager.broker.ping(), True)

    def test_config(self):
        """
        A L{Manager} instance has a proper C{config} attribute.
        """
        self.assertIs(self.manager.config, self.config)

    def test_store(self):
        """
        A L{Manager} instance has a proper C{store} attribute.
        """
        self.assertTrue(isinstance(self.manager.store, ManagerStore))
