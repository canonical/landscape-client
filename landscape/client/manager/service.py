import logging

from twisted.python.reflect import namedClass

from landscape.client.amp import ComponentPublisher
from landscape.client.broker.amp import RemoteBrokerConnector
from landscape.client.manager.config import ManagerConfiguration
from landscape.client.manager.manager import Manager
from landscape.client.service import LandscapeService
from landscape.client.service import run_landscape_service


class ManagerService(LandscapeService):
    """
    The core Twisted Service which creates and runs all necessary managing
    components when started.
    """

    service_name = Manager.name

    def __init__(self, config):
        super().__init__(config)
        self.plugins = self.get_plugins()
        self.manager = Manager(self.reactor, self.config)
        self.publisher = ComponentPublisher(
            self.manager,
            self.reactor,
            self.config,
        )

    def get_plugins(self):
        """Return instances of all the plugins enabled in the configuration."""
        plugins = []

        for plugin_name in self.config.plugin_factories:
            try:
                plugin = namedClass(
                    "landscape.client.manager."
                    f"{plugin_name.lower()}.{plugin_name}",
                )
                plugins.append(plugin())
            except ModuleNotFoundError:
                logging.warning(
                    f"Invalid manager plugin specified: '{plugin_name}'"
                    "See `example.conf` for a full list of monitor plugins.",
                )
            except Exception as exc:
                logging.warning(
                    f"Unable to load manager plugin '{plugin_name}': {exc}",
                )

        return plugins

    def startService(self):  # noqa: N802
        """Start the manager service.

        This method does 3 things, in this order:

          - Start listening for connections on the manager socket.
          - Connect to the broker.
          - Add all configured plugins, that will in turn register themselves.
        """
        super().startService()
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

    def stopService(self):  # noqa: N802
        """Stop the manager and close the connection with the broker."""
        self.connector.disconnect()
        deferred = self.publisher.stop()
        super().stopService()
        return deferred


def run(args):
    run_landscape_service(ManagerConfiguration, ManagerService, args)
