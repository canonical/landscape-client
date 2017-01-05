"""Provide backward and py2/3 compatible access to hashlib functions."""
import sys


try:
    _hashlib = __import__("hashlib")
except ImportError:
    from md5 import md5 as md5_func
    from sha import sha as sha1
else:
    md5_func = _hashlib.md5
    sha1 = _hashlib.sha1


def md5(inp):
    if sys.version_info > (3,):
        return md5_func(inp.encode('utf8'))
    return md5_func(inp)


__all__ = ["md5", "sha1"]
