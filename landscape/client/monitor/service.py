"""Deployment code for the monitor."""
import logging
import os

from twisted.python.reflect import namedClass

from landscape.client.amp import ComponentPublisher
from landscape.client.broker.amp import RemoteBrokerConnector
from landscape.client.monitor.config import MonitorConfiguration
from landscape.client.monitor.monitor import Monitor
from landscape.client.service import LandscapeService
from landscape.client.service import run_landscape_service


class MonitorService(LandscapeService):
    """
    The core Twisted Service which creates and runs all necessary monitoring
    components when started.
    """

    service_name = Monitor.name

    def __init__(self, config):
        self.persist_filename = os.path.join(
            config.data_path,
            f"{self.service_name}.bpickle",
        )
        super().__init__(config)
        self.plugins = self.get_plugins()
        self.monitor = Monitor(
            self.reactor,
            self.config,
            self.persist,
            persist_filename=self.persist_filename,
        )
        self.publisher = ComponentPublisher(
            self.monitor,
            self.reactor,
            self.config,
        )

    def get_plugins(self):
        plugins = []

        for plugin_name in self.config.plugin_factories:
            try:
                plugin = namedClass(
                    "landscape.client.monitor."
                    f"{plugin_name.lower()}.{plugin_name}",
                )
                plugins.append(plugin())
            except ModuleNotFoundError:
                logging.warning(
                    f"Invalid monitor plugin specified: '{plugin_name}'. "
                    "See `example.conf` for a full list of monitor plugins.",
                )
            except Exception as exc:
                logging.warning(
                    f"Unable to load monitor plugin '{plugin_name}': {exc}",
                )

        return plugins

    def startService(self):  # noqa: N802
        """Start the monitor."""
        super().startService()
        self.publisher.start()

        def start_plugins(broker):
            self.broker = broker
            self.monitor.broker = broker
            for plugin in self.plugins:
                self.monitor.add(plugin)
            return self.broker.register_client(self.service_name)

        self.connector = RemoteBrokerConnector(self.reactor, self.config)
        connected = self.connector.connect()
        return connected.addCallback(start_plugins)

    def stopService(self):  # noqa: N802
        """Stop the monitor.

        The monitor is flushed to ensure that things like persist databases
        get saved to disk.
        """
        deferred = self.publisher.stop()
        self.monitor.flush()
        self.connector.disconnect()
        super().stopService()
        return deferred


def run(args):
    run_landscape_service(MonitorConfiguration, MonitorService, args)
