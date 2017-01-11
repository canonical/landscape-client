from twisted.python.compat import _PY3

if _PY3:
    from configparser import ConfigParser, NoOptionError
    SafeConfigParser = ConfigParser

    import _thread as thread

    from io import StringIO
    stringio = cstringio = StringIO

else:
    from ConfigParser import ConfigParser, NoOptionError, SafeConfigParser
    from ConfigParser import SafeConfigParser

    import thread

    from StringIO import StringIO
    stringio = StringIO
    from cStringIO import StringIO as cstringio


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
        return d.iterkeys()


def convert_buffer_to_string(mem_view):
    """
    Converts a buffer in Python 2 or a memoryview in Python 3 to str.
    @param mem_view: The view to convert.
    """
    if _PY3:
        result = mem_view.decode('ascii')
    else:
        result = str(mem_view)
    return result
