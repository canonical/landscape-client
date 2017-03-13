"""File-system utils"""

import codecs
import os
import time


from twisted.python.compat import long


def create_file(path, content, encoding=None):
    """Create a file with the given content.

    @param path: The path to the file.
    @param content: The content to be written in the file.
    @param encoding: An optional encoding. If set, the content will be encoded
        with C{encoding} before writing to the file.
    """
    if encoding:
        content = codecs.encode(content, encoding)
    # XXX: Due to a very specific mock of `open()` in landscape.broker.tests.\
    # test_store.MessageStoreTest.test_atomic_message_writing it is hard to
    # write this file opening as context manager.
    fd = open(path, "wb")
    try:
        fd.write(content)
    finally:
        fd.close()


def append_file(path, content):
    """Append a file with the given content.

    The file is created, if it doesn't exist already.

    @param path: The path to the file.
    @param content: The content to be written in the file at the end.
    """
    with open(path, "a") as fd:
        fd.write(content)


def read_file(path, limit=None, encoding=None):
    """Return the content of the given file.

    @param path: The path to the file.
    @param limit: An optional read limit. If positive, read up to that number
        of bytes from the beginning of the file. If negative, read up to that
        number of bytes from the end of the file.
    @param encoding: An optional encoding. If set, the content will be returned
        decoded with C{encoding}.
    @return content: The content of the file as bytes or unicode string
        (depending on C{encoding}), possibly trimmed to C{limit}.
    """
    # Use binary mode since opening a file in text mode in Python 3 does not
    # allow non-zero offset seek from the end of the file.
    with open(path, "rb") as fd:
        if limit and os.path.getsize(path) > abs(limit):
            whence = 0
            if limit < 0:
                whence = 2
            fd.seek(limit, whence)
        content = fd.read()
    if encoding:
        content = codecs.decode(content, encoding)
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
