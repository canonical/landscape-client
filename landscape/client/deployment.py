import json
import os.path
import subprocess
import sys
import time
from argparse import SUPPRESS
from datetime import datetime
from datetime import timezone
from logging import debug
from logging import info
from typing import Sequence

from twisted.logger import globalLogBeginner

from landscape import VERSION
from landscape.client import DEFAULT_CONFIG
from landscape.client import GROUP
from landscape.client import snap_http
from landscape.client import USER
from landscape.client.snap_utils import get_snap_info
from landscape.client.upgraders import UPGRADE_MANAGERS
from landscape.lib import logging
from landscape.lib.config import BaseConfiguration as _BaseConfiguration
from landscape.lib.format import expandvars
from landscape.lib.network import get_active_device_info
from landscape.lib.network import get_fqdn
from landscape.lib.persist import Persist


def init_logging(configuration, program_name):
    """Given a basic configuration, set up logging."""
    logging.init_app_logging(
        configuration.log_dir,
        configuration.log_level,
        progname=program_name,
        quiet=configuration.quiet,
    )
    # Initialize twisted logging, even if we don't explicitly use it,
    # because of leaky logs https://twistedmatrix.com/trac/ticket/8164
    globalLogBeginner.beginLoggingTo(
        [lambda _: None],
        redirectStandardIO=False,
        discardBuffer=True,
    )


def _is_script(filename=sys.argv[0], _scriptdir=os.path.abspath("scripts")):
    filename = os.path.abspath(filename)
    return os.path.dirname(filename) == _scriptdir


class BaseConfiguration(_BaseConfiguration):

    version = VERSION

    default_config_filename = DEFAULT_CONFIG
    if _is_script():
        default_config_filenames: Sequence[str] = (
            "landscape-client.conf",
            default_config_filename,
        )
    else:
        default_config_filenames = (default_config_filename,)
    default_data_dir = "/var/lib/landscape/client/"

    config_section = "client"

    def __init__(self):
        super().__init__()

        self._command_line_defaults["config"] = None

    def make_parser(self):
        """Parser factory for supported options.

        @return: An ArgumentParser preset with options that all
            programs commonly accept. These include
              - config
              - data_path
        """
        return super().make_parser(
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

        @return: An L{ArgumentParser} preset for all options
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
        parser = super().make_parser()
        logging.add_cli_options(parser, logdir="/var/log/landscape")
        parser.add_argument(
            "-u",
            "--url",
            default=self.DEFAULT_URL,
            help="The server URL to connect to.",
        )
        parser.add_argument(
            "--ping-url",
            help="The URL to perform lightweight exchange initiation with.",
            default="http://landscape.canonical.com/ping",
        )
        parser.add_argument(
            "-k",
            "--ssl-public-key",
            help="The public SSL key to verify the server. "
            "Only used if the given URL is https.",
        )
        parser.add_argument(
            "--ignore-sigint",
            action="store_true",
            default=False,
            help="Ignore interrupt signals.",
        )
        parser.add_argument(
            "--ignore-sigusr1",
            action="store_true",
            default=False,
            help="Ignore SIGUSR1 signal to " "rotate logs.",
        )
        parser.add_argument(
            "--package-monitor-interval",
            default=30 * 60,
            type=int,
            help="The interval between package monitor runs "
            "(default: 1800).",
        )
        parser.add_argument(
            "--apt-update-interval",
            default=6 * 60 * 60,
            type=int,
            help="The interval between apt update runs (default: 21600).",
        )
        parser.add_argument(
            "--flush-interval",
            default=5 * 60,
            type=int,
            metavar="INTERVAL",
            help="The number of seconds between flushes to disk "
            "for persistent data.",
        )
        parser.add_argument(
            "--stagger-launch",
            metavar="STAGGER_RATIO",
            dest="stagger_launch",
            default=0.1,
            type=float,
            help="Ratio, between 0 and 1, by which to stagger "
            "various tasks of landscape.",
        )
        parser.add_argument(
            "--snap-monitor-interval",
            default=30 * 60,
            type=int,
            help="The interval between snap monitor runs (default 1800).",
        )

        # Hidden options, used for load-testing to run in-process clones
        parser.add_argument("--clones", default=0, type=int, help=SUPPRESS)
        parser.add_argument(
            "--start-clones-over",
            default=25 * 60,
            type=int,
            help=SUPPRESS,
        )

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

    def auto_configure(self, retry=False, delay=15, max_retries=7):
        """Automatically configure the client snap."""
        client_conf = snap_http.get_conf("landscape-client").result
        auto_enroll_conf = client_conf.get("auto-register", {})

        enabled = auto_enroll_conf.get("enabled", False)
        configured = auto_enroll_conf.get("configured", False)
        if not enabled or configured:
            return

        for _ in range(max_retries):
            title = generate_computer_title(auto_enroll_conf)
            if title:
                self.computer_title = title
                self.write()

                auto_enroll_conf["configured"] = True
                client_conf["auto-register"] = auto_enroll_conf
                snap_http.set_conf("landscape-client", client_conf)
                break

            if not retry:
                break

            # Retry until we get the computer title (with exponential backoff)
            # The number of retries is capped by `max_retries`
            # With the defaults (delay=15s, max_retries=7), we'll
            # retry over a period of ~30 minutes.
            time.sleep(delay)
            delay *= 2


def get_versioned_persist(service):
    """Get a L{Persist} database with upgrade rules applied.

    Load a L{Persist} database for the given C{service} and upgrade or
    mark as current, as necessary.
    """
    persist = Persist(
        filename=service.persist_filename,
        user=USER,
        group=GROUP,
    )
    upgrade_manager = UPGRADE_MANAGERS[service.service_name]
    if os.path.exists(service.persist_filename):
        upgrade_manager.apply(persist)
    else:
        upgrade_manager.initialize(persist)
    persist.save(service.persist_filename)
    return persist


def generate_computer_title(auto_enroll_config):
    """Generate the computer title.

    This follows the LA017 specification and falls back to `hostname`
    if generating the title fails due to missing data.
    """
    snap_info = get_snap_info()
    wait_for_serial = auto_enroll_config.get("wait-for-serial-as", True)
    if "serial" not in snap_info and wait_for_serial:
        debug(f"No serial assertion in snap info {snap_info}, waiting...")
        return

    hostname = get_fqdn()
    wait_for_hostname = auto_enroll_config.get("wait-for-hostname", False)
    if hostname == "localhost" and wait_for_hostname:
        debug("Waiting for hostname...")
        return

    nics = get_active_device_info(default_only=True)
    nic = nics[0] if nics else {}

    lshw = subprocess.run(
        ["lshw", "-json", "-quiet", "-c", "system"],
        capture_output=True,
        text=True,
    )
    hardware = json.loads(lshw.stdout)[0]

    computer_title_pattern = auto_enroll_config.get(
        "computer-title-pattern",
        "${hostname}",
    )
    title = expandvars(
        computer_title_pattern,
        serial=snap_info.get("serial", ""),
        model=snap_info.get("model", ""),
        brand=snap_info.get("brand", ""),
        hostname=hostname,
        ip=nic.get("ip_address", ""),
        mac=nic.get("mac_address", ""),
        prodiden=hardware.get("product", ""),
        serialno=hardware.get("serial", ""),
        datetime=datetime.now(timezone.utc),
    )

    if title == "":  # on the off-chance substitute values are missing
        title = hostname

    return title


def convert_arg_to_bool(value: str) -> bool:
    """
    Converts an argument provided that is in string format
    to be a boolean value.
    """
    TRUTHY_VALUES = {"true", "yes", "y", "1", "on"}
    FALSY_VALUES = {"false", "no", "n", "0", "off"}

    if value.lower() in TRUTHY_VALUES:
        return True
    elif value.lower() in FALSY_VALUES:
        return False
    else:
        info(
            "Error. Invalid boolean provided in config or parameters. "
            + "Defaulting to False.",
        )
        return False
