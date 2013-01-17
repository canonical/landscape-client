from landscape.deployment import Configuration


ALL_PLUGINS = ["ActiveProcessInfo", "ComputerInfo", "HardwareInventory",
               "LoadAverage", "MemoryInfo", "MountInfo", "ProcessorInfo",
               "Temperature", "PackageMonitor", "UserMonitor",
               "RebootRequired", "AptPreferences", "NetworkActivity",
               "NetworkDevice", "UpdateManager", "CPUUsage"]


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
        parser.add_option("--flush-interval", default=5 * 60, type="int",
                          metavar="INTERVAL",
                          help="The number of seconds between flushes.")
        return parser

    @property
    def plugin_factories(self):
        if self.monitor_plugins == "ALL":
            return ALL_PLUGINS
        return [x.strip() for x in self.monitor_plugins.split(",")]
