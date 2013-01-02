"""Provide backward compatible access to hashlib functions."""


try:
    _hashlib = __import__("hashlib")
except ImportError:
    from md5 import md5
    from sha import sha as sha1
else:
    md5 = _hashlib.md5
    sha1 = _hashlib.sha1


__all__ = ["md5", "sha1"]


def md5sum_file(filename, block_size=128):
    """
    Return the MD5 hex digest of a  file by splitting it into chunks of
    C{block_size} so as to fit all the file in memory.
    """
    result = md5()
    with open(filename, "r") as the_file:
        while True:
            data = the_file.read(block_size)
            if not data:  # EOF
                break
            result.update(data)
    return result.hexdigest()
