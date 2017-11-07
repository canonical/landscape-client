import logging


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
