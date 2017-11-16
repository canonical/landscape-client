from landscape.client.deployment import Configuration


ALL_PLUGINS = ["ActiveProcessInfo", "ComputerInfo",
               "LoadAverage", "MemoryInfo", "MountInfo", "ProcessorInfo",
               "Temperature", "PackageMonitor", "UserMonitor",
               "RebootRequired", "AptPreferences", "NetworkActivity",
               "NetworkDevice", "UpdateManager", "CPUUsage", "SwiftUsage",
               "CephUsage"]


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
        return parser

    @property
    def plugin_factories(self):
        if self.monitor_plugins == "ALL":
            return ALL_PLUGINS
        return [x.strip() for x in self.monitor_plugins.split(",")]
