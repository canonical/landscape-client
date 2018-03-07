"""Deployment code for the sysinfo tool."""
import os
import sys
from logging import getLogger, Formatter
from logging.handlers import RotatingFileHandler

from twisted.python.reflect import namedClass
from twisted.internet.defer import Deferred, maybeDeferred

from landscape import VERSION
from landscape.lib.config import BaseConfiguration
from landscape.sysinfo.sysinfo import SysInfoPluginRegistry, format_sysinfo


ALL_PLUGINS = ["Load", "Disk", "Memory", "Temperature", "Processes",
               "LoggedInUsers", "Network"]


class SysInfoConfiguration(BaseConfiguration):
    """Specialized configuration for the Landscape sysinfo tool."""

    version = VERSION

    default_config_filenames = ("/etc/landscape/client.conf",)
    if os.getuid() != 0:
        default_config_filenames += (
            os.path.expanduser("~/.landscape/sysinfo.conf"),)
    default_data_dir = "/var/lib/landscape/client/"

    config_section = "sysinfo"

    def __init__(self):
        super(SysInfoConfiguration, self).__init__()

        self._command_line_defaults["config"] = None

    def make_parser(self):
        """
        Specialize L{Configuration.make_parser}, adding any
        sysinfo-specific options.
        """
        parser = super(SysInfoConfiguration, self).make_parser()

        parser.add_option("--sysinfo-plugins", metavar="PLUGIN_LIST",
                          help="Comma-delimited list of sysinfo plugins to "
                               "use. Default is to use all plugins.")

        parser.add_option("--exclude-sysinfo-plugins", metavar="PLUGIN_LIST",
                          help="Comma-delimited list of sysinfo plugins to "
                               "NOT use. This always take precedence over "
                               "plugins to include.")

        parser.epilog = "Default plugins: %s" % (", ".join(ALL_PLUGINS))
        return parser

    def get_plugin_names(self, plugin_spec):
        return [x.strip() for x in plugin_spec.split(",")]

    def get_plugins(self):
        if self.sysinfo_plugins is None:
            include = ALL_PLUGINS
        else:
            include = self.get_plugin_names(self.sysinfo_plugins)
        if self.exclude_sysinfo_plugins is None:
            exclude = []
        else:
            exclude = self.get_plugin_names(self.exclude_sysinfo_plugins)
        plugins = [x for x in include if x not in exclude]
        return [namedClass("landscape.sysinfo.%s.%s"
                           % (plugin_name.lower(), plugin_name))()
                for plugin_name in plugins]


def get_landscape_log_directory(landscape_dir=None):
    """
    Work out the correct path to store logs in depending on the effective
    user id of the current process.
    """
    if landscape_dir is None:
        if os.getuid() == 0:
            landscape_dir = "/var/log/landscape"
        else:
            landscape_dir = os.path.expanduser("~/.landscape")
    return landscape_dir


def setup_logging(landscape_dir=None):
    landscape_dir = get_landscape_log_directory(landscape_dir)
    logger = getLogger("landscape-sysinfo")
    logger.propagate = False
    if not os.path.isdir(landscape_dir):
        os.mkdir(landscape_dir)
    log_filename = os.path.join(landscape_dir, "sysinfo.log")
    handler = RotatingFileHandler(log_filename,
                                  maxBytes=500 * 1024, backupCount=1)
    logger.addHandler(handler)
    handler.setFormatter(Formatter("%(asctime)s %(levelname)-8s %(message)s"))


def run(args, reactor=None, sysinfo=None):
    """
    @param reactor: The reactor to (optionally) run the sysinfo plugins in.
    """
    try:
        setup_logging()
    except IOError as e:
        sys.exit("Unable to setup logging. %s" % e)

    if sysinfo is None:
        sysinfo = SysInfoPluginRegistry()
    config = SysInfoConfiguration()
    # landscape-sysinfo needs to work where there's no
    # /etc/landscape/client.conf See lp:1293990
    config.load(args, accept_nonexistent_default_config=True)
    for plugin in config.get_plugins():
        sysinfo.add(plugin)

    def show_output(result):
        print(format_sysinfo(sysinfo.get_headers(), sysinfo.get_notes(),
                             sysinfo.get_footnotes(), indent="  "))

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
