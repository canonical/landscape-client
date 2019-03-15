import os.path
import sys

from optparse import SUPPRESS_HELP
from twisted.logger import globalLogBeginner

from landscape import VERSION
from landscape.lib import logging
from landscape.lib.config import BaseConfiguration as _BaseConfiguration
from landscape.lib.persist import Persist

from landscape.client.upgraders import UPGRADE_MANAGERS


def init_logging(configuration, program_name):
    """Given a basic configuration, set up logging."""
    logging.init_app_logging(configuration.log_dir, configuration.log_level,
                             progname=program_name,
                             quiet=configuration.quiet)
    # Initialize twisted logging, even if we don't explicitly use it,
    # because of leaky logs https://twistedmatrix.com/trac/ticket/8164
    globalLogBeginner.beginLoggingTo(
        [lambda _: None], redirectStandardIO=False, discardBuffer=True)


def _is_script(filename=sys.argv[0],
               _scriptdir=os.path.abspath("scripts")):
    filename = os.path.abspath(filename)
    return (os.path.dirname(filename) == _scriptdir)


class BaseConfiguration(_BaseConfiguration):

    version = VERSION

    default_config_filename = "/etc/landscape/client.conf"
    if _is_script():
        default_config_filenames = ("landscape-client.conf",
                                    default_config_filename)
    else:
        default_config_filenames = (default_config_filename,)
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
                cfgfile=self.default_config_filename,
                datadir=self.default_data_dir,
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
              - C{stagger_launch} (C{0.1})
        """
        parser = super(Configuration, self).make_parser()
        logging.add_cli_options(parser, logdir="/var/log/landscape")
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
        parser.add_option("--stagger-launch", metavar="STAGGER_RATIO",
                          dest="stagger_launch", default=0.1, type=float,
                          help="Ratio, between 0 and 1, by which to scatter "
                               "various tasks of landscape.")

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
