from __future__ import absolute_import

import logging


def log_failure(failure, msg=None, logger=None):
    """Log a L{twisted.python.failure.Failure} to the Python L{logging} module.

    The failure should be formatted as a regular exception, but a traceback may
    not be available.

    If C{msg} is passed, it will included before the traceback.
    """
    if logger is None:
        logger = logging
    logger.error(msg, exc_info=(failure.type, failure.value, failure.tb))
