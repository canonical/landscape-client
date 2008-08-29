"""Deployment code for the sysinfo tool."""

import os
from logging import getLogger, Formatter
from logging.handlers import RotatingFileHandler

from twisted.python.reflect import namedClass
from twisted.internet.defer import Deferred, maybeDeferred

from landscape.deployment import Configuration
from landscape.sysinfo.sysinfo import SysInfoPluginRegistry, format_sysinfo


ALL_PLUGINS = ["Load", "Disk", "Memory", "Temperature", "Processes",
               "LoggedInUsers"]


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


def setup_logging(landscape_dir=os.path.expanduser("~/.landscape")):
    logger = getLogger("landscape-sysinfo")
    logger.propagate = False
    if not os.path.isdir(landscape_dir):
        os.mkdir(landscape_dir)
    log_filename = os.path.join(landscape_dir,  "sysinfo.log")
    handler = RotatingFileHandler(log_filename,
                                  maxBytes=500 * 1024, backupCount=1)
    logger.addHandler(handler)
    handler.setFormatter(Formatter("%(asctime)s %(levelname)-8s %(message)s"))


def run(args, reactor=None, sysinfo=None):
    """
    @param reactor: The reactor to (optionally) run the sysinfo plugins in.
    """
    setup_logging()

    if sysinfo is None:
        sysinfo = SysInfoPluginRegistry()
    config = SysInfoConfiguration()
    config.load(args)
    for plugin in config.get_plugins():
        sysinfo.add(plugin)

    def show_output(result):
        print format_sysinfo(sysinfo.get_headers(), sysinfo.get_notes(),
                             sysinfo.get_footnotes(), indent="  ")

    def run_sysinfo():
        return sysinfo.run().addCallback(show_output)

    if reactor is not None:
        # In case any plugins run processes or do other things that require the
        # reactor to already be started, we delay them until the reactor is
        # running.
        done = Deferred()
        reactor.callWhenRunning(
            lambda: maybeDeferred(run_sysinfo).chainDeferred(done))
        def stop_reactor(result):
            # We won't need to use callLater here once we use Twisted >8.
            # tm:3011
            reactor.callLater(0, reactor.stop)
            return result
        done.addBoth(stop_reactor)
        reactor.run()
    else:
        done = run_sysinfo()
    return done
