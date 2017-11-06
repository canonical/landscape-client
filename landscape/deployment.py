import os.path
import sys

from logging import (getLevelName, getLogger,
                     FileHandler, StreamHandler, Formatter)

from optparse import SUPPRESS_HELP

from landscape import VERSION
from landscape.lib.config import BaseConfiguration as _BaseConfiguration
from landscape.lib.persist import Persist

from landscape.upgraders import UPGRADE_MANAGERS


def init_logging(configuration, program_name):
    """Given a basic configuration, set up logging."""
    handlers = []
    if not os.path.exists(configuration.log_dir):
        os.makedirs(configuration.log_dir)
    log_filename = os.path.join(configuration.log_dir, program_name + ".log")
    handlers.append(FileHandler(log_filename))
    if not configuration.quiet:
        handlers.append(StreamHandler(sys.stdout))
    getLogger().setLevel(getLevelName(configuration.log_level.upper()))
    for handler in handlers:
        getLogger().addHandler(handler)
        format = ("%(asctime)s %(levelname)-8s [%(threadName)-10s] "
                  "%(message)s")
        handler.setFormatter(Formatter(format))


def _is_script(filename=sys.argv[0],
               _scriptdir=os.path.abspath("scripts")):
    filename = os.path.abspath(filename)
    return (os.path.dirname(filename) == _scriptdir)


class BaseConfiguration(_BaseConfiguration):

    version = VERSION

    default_config_filenames = ["/etc/landscape/client.conf"]
    if _is_script():
        default_config_filenames.insert(0, "landscape-client.conf")
    default_config_filenames = tuple(default_config_filenames)
    default_data_dir = "/var/lib/landscape/client/"
    config_section = "client"

    def __init__(self):
        super(BaseConfiguration, self).__init__()

        self._command_line_defaults["config"] = None

    def make_parser(self):
        """Parser factory for supported options.

        @return: An OptionParser preset with options that all
            programs commonly accept. These include
              - config
              - data_path
        """
        return super(BaseConfiguration, self).make_parser(
                cfgfile="/etc/landscape/client.conf",
                datadir="/var/lib/landscape/client/",
                )


class Configuration(BaseConfiguration):
    """Configuration data for Landscape client.

    This contains all simple data, some of it calculated.
    """

    DEFAULT_URL = "https://landscape.canonical.com/message-system"

    def make_parser(self):
        """Parser factory for supported options.

        @return: An L{OptionParser} preset for all options
            from L{BaseConfiguration.make_parser} plus:
              - C{quiet} (C{False})
              - C{log_dir} (C{"/var/log/landscape"})
              - C{log_level} (C{"info"})
              - C{url} (C{"http://landscape.canonical.com/message-system"})
              - C{ping_url} (C{"http://landscape.canonical.com/ping"})
              - C{ssl_public_key}
              - C{ignore_sigint} (C{False})
        """
        parser = super(Configuration, self).make_parser()
        parser.add_option("-q", "--quiet", default=False, action="store_true",
                          help="Do not log to the standard output.")
        parser.add_option("-l", "--log-dir", metavar="FILE",
                          help="The directory to write log files to "
                               "(default: '/var/log/landscape').",
                          default="/var/log/landscape")
        parser.add_option("--log-level", default="info",
                          help="One of debug, info, warning, error or "
                               "critical.")
        parser.add_option("-u", "--url", default=self.DEFAULT_URL,
                          help="The server URL to connect to.")
        parser.add_option("--ping-url",
                          help="The URL to perform lightweight exchange "
                               "initiation with.",
                          default="http://landscape.canonical.com/ping")
        parser.add_option("-k", "--ssl-public-key",
                          help="The public SSL key to verify the server. "
                               "Only used if the given URL is https.")
        parser.add_option("--ignore-sigint", action="store_true",
                          default=False, help="Ignore interrupt signals.")
        parser.add_option("--ignore-sigusr1", action="store_true",
                          default=False, help="Ignore SIGUSR1 signal to "
                                              "rotate logs.")
        parser.add_option("--package-monitor-interval", default=30 * 60,
                          type="int",
                          help="The interval between package monitor runs "
                               "(default: 1800).")
        parser.add_option("--apt-update-interval", default=6 * 60 * 60,
                          type="int",
                          help="The interval between apt update runs "
                               "(default: 21600).")
        parser.add_option("--flush-interval", default=5 * 60, type="int",
                          metavar="INTERVAL",
                          help="The number of seconds between flushes to disk "
                               "for persistent data.")

        # Hidden options, used for load-testing to run in-process clones
        parser.add_option("--clones", default=0, type=int, help=SUPPRESS_HELP)
        parser.add_option("--start-clones-over", default=25 * 60, type=int,
                          help=SUPPRESS_HELP)

        return parser

    @property
    def sockets_path(self):
        """Return the path to the directory where Unix sockets are created."""
        return os.path.join(self.data_path, "sockets")

    @property
    def annotations_path(self):
        """
        Return the path to the directory where additional annotation files can
        be stored.
        """
        return os.path.join(self.data_path, "annotations.d")

    @property
    def juju_filename(self):
        """The path to the previously sinlge juju-info file for
        backwards-compatibility."""
        return os.path.join(self.data_path, "juju-info.json")


def get_versioned_persist(service):
    """Get a L{Persist} database with upgrade rules applied.

    Load a L{Persist} database for the given C{service} and upgrade or
    mark as current, as necessary.
    """
    persist = Persist(filename=service.persist_filename)
    upgrade_manager = UPGRADE_MANAGERS[service.service_name]
    if os.path.exists(service.persist_filename):
        upgrade_manager.apply(persist)
    else:
        upgrade_manager.initialize(persist)
    persist.save(service.persist_filename)
    return persist
