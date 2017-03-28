from twisted.python.compat import _PY3


if _PY3:
    import _pickle as cPickle
    from configparser import ConfigParser, NoOptionError
    SafeConfigParser = ConfigParser

    import _thread as thread

    from io import StringIO
    stringio = cstringio = StringIO
    from builtins import input

else:
    import cPickle
    from ConfigParser import ConfigParser, NoOptionError, SafeConfigParser

    import thread

    from StringIO import StringIO
    stringio = StringIO
    from cStringIO import StringIO as cstringio
    input = raw_input


def coerce_unicode(s, encoding='ascii', errors='strict'):
    """
    Coerce byte strings into unicode for Python 2.

    In Python 2, decodes a byte string L{s} into unicode using the L{encoding},
    returns unmodified if any other type. In Python 3, raises a L{TypeError}
    when passed a byte string in L{s}, returns unmodified otherwise.

    @param s: The string to be converted to unicode.
    @type s: L{bytes} or L{unicode}
    @raise UnicodeError: The input L{bytes} is not decodable
        with given encoding.
    @raise TypeError: The input is L{bytes} on Python 3.
    """
    # In Python 2 C{unicode(b'bytes')} returns a unicode string C{'bytes'}. In
    # Python 3, the equivalent C{str(b'bytes')} will return C{"b'bytes'"}
    # instead.
    if isinstance(s, bytes):
        if _PY3:
            raise TypeError("Expected str not %r (bytes)" % (s,))
        else:
            return s.decode(encoding, errors)
    else:
        return s
