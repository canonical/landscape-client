from twisted.python.reflect import namedClass

from landscape.deployment import LandscapeService
from landscape.broker.amp import RemoteBrokerCreator
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

        def start_plugins(broker):
            self.broker = broker
            self.manager = Manager(self.broker, self.reactor, self.config)

            for plugin in self.plugins:
                self.manager.register_plugin(plugin)

            return self.broker.register_client(self.service_name)

        socket = self.config.broker_socket_filename
        self.creator = RemoteBrokerCreator(self.reactor._reactor, socket)
        connected = self.creator.connect()
        return connected.addCallback(start_plugins)

    def stopService(self):
        """Stop the manager and close the connection with the broker."""
        self.creator.disconnect()
        super(ManagerService, self).stopService()
