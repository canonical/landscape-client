"""Deployment code for the sysinfo tool."""
from twisted.python.reflect import namedClass
from twisted.internet import reactor

from landscape.deployment import Configuration
from landscape.sysinfo.sysinfo import SysInfoPluginRegistry, format_sysinfo


ALL_PLUGINS = ["Load", "Memory", "LoggedUsers"]


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


def run(args, run_reactor=True):
    sysinfo = SysInfoPluginRegistry()
    config = SysInfoConfiguration()
    config.load(args)
    for plugin in config.get_plugins():
        sysinfo.add(plugin)
    def show_output(result):
        print format_sysinfo(sysinfo.get_headers(), sysinfo.get_notes(),
                             sysinfo.get_footnotes(), indent="  ")
    result = sysinfo.run()
    result.addCallback(show_output)

    if run_reactor:
        # XXX No unittests for this. :-(
        def stop_reactor(result):
            reactor.callLater(0.1, reactor.stop)
            return result
        result.addBoth(stop_reactor)
        reactor.run()
