from twisted.python.compat import _PY3


def coerce_unicode(s, encoding='ascii', errors='strict'):
    """
    Coerce byte strings into unicode for Python 2.
    In Python 2 C{unicode(b'bytes')} returns a unicode string C{'bytes'}. In
    Python 3, the equivalent C{str(b'bytes')} will return C{"b'bytes'"}
    instead. This function mimics the behavior for Python 2. It will decode the
    byte string as the given encoding (default ascii). In Python 3 it simply
    raises a L{TypeError} when passing a byte string.
    Unicode strings are returned as-is.
    @param s: The string to coerce.
    @type s: L{bytes} or L{unicode}
    @raise UnicodeError: The input L{bytes} is not decodable
    with given encoding.
    @raise TypeError: The input is L{bytes} on Python 3.
    """
    if isinstance(s, bytes):
        if _PY3:
            raise TypeError("Expected str not %r (bytes)" % (s,))
        else:
            return s.decode(encoding, errors)
    else:
        return s


if _PY3:
    def iterkeys(d):
        return d.keys()
else:
    def iterkeys(d):
        return d.iteritems()
