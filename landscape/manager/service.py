from twisted.python.reflect import namedClass

from landscape.service import LandscapeService, run_landscape_service
from landscape.manager.config import ManagerConfiguration
from landscape.broker.amp import (
    BrokerClientProtocolFactory, RemoteBrokerConnector)
from landscape.manager.manager import Manager


class ManagerService(LandscapeService):
    """
    The core Twisted Service which creates and runs all necessary managing
    components when started.
    """

    service_name = Manager.name

    def __init__(self, config):
        super(ManagerService, self).__init__(config)
        self.plugins = self.get_plugins()
        self.manager = Manager(self.reactor, self.config)
        self.factory = BrokerClientProtocolFactory(object=self.manager)

    def get_plugins(self):
        return [namedClass("landscape.manager.%s.%s"
                           % (plugin_name.lower(), plugin_name))()
                for plugin_name in self.config.plugin_factories]

    def startService(self):
        super(ManagerService, self).startService()

        def start_plugins(broker):
            self.broker = broker
            self.manager.broker = broker
            for plugin in self.plugins:
                self.manager.add(plugin)
            return self.broker.register_client(self.service_name)

        self.connector = RemoteBrokerConnector(self.reactor, self.config)
        connected = self.connector.connect()
        return connected.addCallback(start_plugins)

    def stopService(self):
        """Stop the manager and close the connection with the broker."""
        self.connector.disconnect()
        super(ManagerService, self).stopService()


def run(args):
    run_landscape_service(ManagerConfiguration, ManagerService, args)
