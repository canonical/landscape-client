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
