from landscape.manager.store import ManagerStore
from landscape.broker.client import BrokerClient

# Protocol messages! Same constants are defined in the server.
FAILED = 5
SUCCEEDED = 6


class Manager(BrokerClient):
    """Central point of integration for the Landscape Manager."""

    name = "manager"

    def __init__(self, reactor, config):
        super(Manager, self).__init__(reactor)
        self.reactor = reactor
        self.config = config
        self.store = ManagerStore(self.config.store_filename)
