"""File-system utils"""

import os
import time


def create_file(path, content):
    """Create a file with the given binary content.

    @param path: The path to the file.
    @param content: The content to be written in the file.
    """
    # Due to a very specific mock of `open()` in landscape.broker.tests.\
    # test_store.MessageStoreTest.test_atomic_message_writing it is hard to
    # write this file opening as context manager.
    fd = open(path, "wb")
    try:
        fd.write(content)
    finally:
        fd.close()


def append_file(path, content):
    """Append a file with the given binary content.

    The file is created, if it doesn't exist already.

    @param path: The path to the file.
    @param content: The content to be written in the file at the end.
    """
    with open(path, "a") as fd:
        fd.write(content)


def read_file(path, limit=None):
    """Return the content of the given file.

    @param path: The path to the file.
    @param limit: An optional read limit. If positive, read up to that number
        of bytes from the beginning of the file. If negative, read up to that
        number of bytes from the end of the file.
    @return content: The content of the file, possibly trimmed to C{limit}.
    """
    fd = open(path, "r")
    if limit and os.path.getsize(path) > abs(limit):
        whence = 0
        if limit < 0:
            whence = 2
        fd.seek(limit, whence)
    content = fd.read()
    fd.close()
    return content


def touch_file(path, offset_seconds=None):
    """Touch a file, creating it if it doesn't exist.

    @param path: the path to the file to be touched.
    @param offset_seconds: a signed integer number of seconds to offset the
        atime and mtime of the file from the current time.

    """
    fd = open(path, "a")
    fd.close()
    if offset_seconds is not None:
        offset_time = long(time.time()) + offset_seconds
        touch_time = (offset_time, offset_time)
    else:
        touch_time = None
    os.utime(path, touch_time)
