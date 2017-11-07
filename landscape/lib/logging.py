from __future__ import absolute_import

import logging
import os
import os.path
import sys


FORMAT = '%(asctime)s %(levelname)-8s [%(threadName)-10s] %(message)s'


def add_cli_options(parser, level='info', logdir=None):
    """Add common logging-related CLI options to the given arg parser."""
    parser.add_option('-q', '--quiet', default=False, action='store_true',
                      help='Do not log to the standard output.')

    logdirhelp = 'The directory in which to write log files'
    if logdir:
        logdirhelp += ' (default: {!r}).'.format(logdir)
    parser.add_option('-l', '--log-dir', metavar='FILE', default=logdir,
                      help=logdirhelp)

    parser.add_option('--log-level', default=level,
                      help='One of debug, info, warning, error or critical.')


def init_app_logging(logdir, level='info', progname=None, quiet=False):
    """Given a log dir, set up logging for an application."""
    if progname is None:
        progname = os.path.basename(sys.argv[0])
    level = logging.getLevelName(level.upper())
    _init_logging(
            logging.getLogger(),
            level,
            logdir,
            progname,
            logging.Formatter(FORMAT),
            sys.stdout if not quiet else None,
            )
    return logging.getLogger()


def _init_logging(logger, level, logdir, logname, formatter, stdout=None):
    # Set the log level.
    logger.setLevel(level)

    # Set up the log file.
    if not os.path.exists(logdir):
        os.makedirs(logdir)
    filename = os.path.join(logdir, logname + '.log')

    # Set the handlers.
    handlers = [
        logging.FileHandler(filename),
        ]
    if stdout:
        handlers.append(logging.StreamHandler(stdout))
    for handler in handlers:
        logger.addHandler(handler)
        handler.setFormatter(formatter)


def rotate_logs():
    """
    This closes and reopens the underlying files in the logging module's
    root logger. If called after logrotate (or something similar) has
    moved the old log file out of the way, this will start writing to a new
    new log file...
    """
    for handler in logging.getLogger().handlers:
        if isinstance(handler, logging.FileHandler):
            handler.acquire()
            try:
                handler.stream.close()
                handler.stream = open(handler.baseFilename,
                                      handler.mode)
            finally:
                handler.release()
    logging.info("Landscape Logs rotated")
