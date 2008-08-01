"""Deployment code for the sysinfo tool."""
import os

from twisted.python.reflect import namedClass

from landscape.deployment import Configuration
from landscape.monitor.monitor import (MonitorPluginRegistry,
                                       MonitorDBusObject)
from landscape.broker.remote import (RemoteBroker,
                                     DBusSignalToReactorTransmitter)


ALL_PLUGINS = ["Load"]


class SysInfoConfiguration(Configuration):
    """Specialized configuration for the Landscape sysinfo tool."""

    def make_parser(self):
        """
        Specialize L{Configuration.make_parser}, adding any
        sysinfo-specific options.
        """
        parser = super(SysInfoConfiguration, self).make_parser()

        parser.add_option("--sysinfo-plugins", metavar="PLUGIN_LIST",
                          help="Comma-delimited list of sysinfo plugins to "
                               "use. ALL means use all plugins.",
                          default="ALL")
        return parser

    @property
    def plugin_factories(self):
        if self.sysinfo_plugins == "ALL":
            return ALL_PLUGINS
        return [x.strip() for x in self.sysinfo_plugins.split(",")]

    def get_plugins(self):
        return [namedClass("landscape.sysinfo.%s.%s"
                           % (plugin_name.lower(), plugin_name))()
                for plugin_name in self.plugin_factories]


def run(args):
    pass
