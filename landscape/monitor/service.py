"""Deployment code for the monitor."""

import os

from twisted.python.reflect import namedClass

from landscape.service import LandscapeService, run_landscape_service
from landscape.broker.amp import RemoteBrokerCreator
from landscape.monitor.config import MonitorConfiguration
from landscape.monitor.monitor import Monitor


class MonitorService(LandscapeService):
    """
    The core Twisted Service which creates and runs all necessary monitoring
    components when started.
    """

    service_name = "monitor"

    def __init__(self, config):
        self.persist_filename = os.path.join(config.data_path,
                                             "%s.bpickle" % self.service_name)
        super(MonitorService, self).__init__(config)
        self.plugins = self.get_plugins()

    def get_plugins(self):
        return [namedClass("landscape.monitor.%s.%s"
                           % (plugin_name.lower(), plugin_name))()
                for plugin_name in self.config.plugin_factories]

    def startService(self):
        """Start the monitor."""
        super(MonitorService, self).startService()

        def start_plugins(broker):
            self.broker = broker
            self.monitor = Monitor(self.broker, self.reactor,
                                   self.config, self.persist,
                                   persist_filename=self.persist_filename)

            for plugin in self.plugins:
                self.monitor.add(plugin)

            return self.broker.register_client(self.service_name)

        self.creator = RemoteBrokerCreator(self.reactor, self.config)
        connected = self.creator.connect()
        return connected.addCallback(start_plugins)

    def stopService(self):
        """Stop the monitor.

        The monitor is flushed to ensure that things like persist databases
        get saved to disk.
        """
        self.monitor.flush()
        self.creator.disconnect()
        super(MonitorService, self).stopService()


def run(args):
    run_landscape_service(MonitorConfiguration, MonitorService, args)
