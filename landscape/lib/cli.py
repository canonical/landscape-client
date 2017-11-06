
def add_cli_options(parser, cfgfile=None, datadir=None):
    """Add common CLI options to the given arg parser."""
    from . import config
    config.add_cli_options(parser, cfgfile)

    datadirhelp = "The directory in which to store data files."
    if datadir:
        datadirhelp += " (default: {!r})".format(datadir)
    parser.add_option("-d", "--data-path", metavar="PATH", default=datadir,
                      help=datadirhelp)
