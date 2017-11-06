
from landscape.deployment import BaseConfiguration  # NOQA


def add_cli_options(parser, filename=None):
    """Add common config-related CLI options to the given arg parser."""
    cfgfilehelp = ("Use config from this file (any command line "
                   "options override settings from the file).")
    if filename is not None:
        filename += " (default: {!r})".format(filename)
    parser.add_option("-c", "--config", metavar="FILE", default=filename,
                      help=cfgfilehelp)
