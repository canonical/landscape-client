"""Deployment code for the monitor."""

import os

from twisted.python.reflect import namedClass

from landscape.deployment import (LandscapeService, Configuration,
                                  run_landscape_service)
from landscape.monitor.monitor import (MonitorPluginRegistry,
                                       MonitorDBusObject)
from landscape.broker.remote import (RemoteBroker,
                                     DBusSignalToReactorTransmitter)


ALL_PLUGINS = ["ActiveProcessInfo", "ComputerInfo", "HardwareInventory",
               "LoadAverage", "MemoryInfo", "MountInfo", "ProcessorInfo",
               "Temperature", "PackageMonitor",
               "UserMonitor"]


class MonitorConfiguration(Configuration):
    """Specialized configuration for the Landscape Monitor."""

    def make_parser(self):
        """
        Specialize L{Configuration.make_parser}, adding many
        monitor-specific options.
        """
        parser = super(MonitorConfiguration, self).make_parser()

        parser.add_option("--monitor-plugins", metavar="PLUGIN_LIST",
                          help="Comma-delimited list of monitor plugins to "
                               "use. ALL means use all plugins.",
                          default="ALL")
        parser.add_option("--flush-interval", default=5*60, type="int",
                          metavar="INTERVAL",
                          help="The number of seconds between flushes.")
        return parser

    @property
    def plugin_factories(self):
        if self.monitor_plugins == "ALL":
            return ALL_PLUGINS
        return [x.strip() for x in self.monitor_plugins.split(",")]


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
        super(MonitorService, self).startService()

        # If this raises ServiceUnknownError, we should do something nice.
        self.remote_broker = RemoteBroker(self.bus)

        self.registry = MonitorPluginRegistry(self.remote_broker, self.reactor,
                                              self.config, self.bus,
                                              self.persist,
                                              self.persist_filename)
        self.dbus_service = MonitorDBusObject(self.bus, self.registry)
        DBusSignalToReactorTransmitter(self.bus, self.reactor)

        for plugin in self.plugins:
            self.registry.add(plugin)

        self.flush_call_id = self.reactor.call_every(
            self.config.flush_interval, self.registry.flush)

        def broker_started():
            self.remote_broker.register_plugin(self.dbus_service.bus_name,
                                               self.dbus_service.object_path)
            self.registry.broker_started()

        broker_started()
        self.bus.add_signal_receiver(broker_started, "broker_started")

    def stopService(self):
        """Stop the monitor.

        The monitor is flushed to ensure that things like persist
        databases get saved to disk.
        """
        self.registry.flush()
        if self.flush_call_id:
            self.reactor.cancel_call(self.flush_call_id)
            self.flush_call_id = None
        super(MonitorService, self).stopService()


def run(args):
    run_landscape_service(MonitorConfiguration, MonitorService, args,
                          MonitorDBusObject.bus_name)
