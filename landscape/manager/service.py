from twisted.python.reflect import namedClass
from twisted.internet.protocol import ClientCreator

from landscape.deployment import LandscapeService
from landscape.broker.amp import BrokerClientProtocol, RemoteBroker
from landscape.manager.manager import Manager


class ManagerService(LandscapeService):
    """
    The core Twisted Service which creates and runs all necessary managing
    components when started.
    """

    service_name = "manager"

    def __init__(self, config):
        super(ManagerService, self).__init__(config)
        self.plugins = self.get_plugins()

    def get_plugins(self):
        return [namedClass("landscape.manager.%s.%s"
                           % (plugin_name.lower(), plugin_name))()
                for plugin_name in self.config.plugin_factories]

    def startService(self):
        super(ManagerService, self).startService()

        def start_plugins(protocol):
            self.broker = RemoteBroker(protocol)
            self.manager = Manager(self.broker, self.reactor, self.config)

            for plugin in self.plugins:
                self.manager.register_plugin(plugin)

            return self.broker.register_client(self.service_name)

        connector = ClientCreator(self.reactor._reactor, BrokerClientProtocol)
        connected = connector.connectUNIX(self.config.broker_socket_filename)
        return connected.addCallback(start_plugins)
