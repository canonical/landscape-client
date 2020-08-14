from twisted.python.reflect import namedClass

from landscape.client.service import LandscapeService, run_landscape_service
from landscape.client.manager.config import ManagerConfiguration
from landscape.client.broker.amp import RemoteBrokerConnector
from landscape.client.amp import ComponentPublisher
from landscape.client.manager.manager import Manager


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
        self.publisher = ComponentPublisher(self.manager, self.reactor,
                                            self.config)

    def get_plugins(self):
        """Return instances of all the plugins enabled in the configuration."""
        return [namedClass("landscape.client.manager.%s.%s"
                           % (plugin_name.lower(), plugin_name))()
                for plugin_name in self.config.plugin_factories]

    def startService(self):
        """Start the manager service.

        This method does 3 things, in this order:

          - Start listening for connections on the manager socket.
          - Connect to the broker.
          - Add all configured plugins, that will in turn register themselves.
        """
        super(ManagerService, self).startService()
        self.publisher.start()

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
        deferred = self.publisher.stop()
        super(ManagerService, self).stopService()
        return deferred


def run(args):
    run_landscape_service(ManagerConfiguration, ManagerService, args)
