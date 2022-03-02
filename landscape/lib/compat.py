# flake8: noqa

_PY3 = str != bytes


if _PY3:
    import _pickle as cPickle
    from configparser import ConfigParser, NoOptionError
    SafeConfigParser = ConfigParser

    import _thread as thread

    from io import StringIO
    stringio = cstringio = StringIO
    from builtins import input
    unicode = str
    long = int

else:
    import cPickle
    from ConfigParser import ConfigParser, NoOptionError, SafeConfigParser

    import thread

    from StringIO import StringIO
    stringio = StringIO
    from cStringIO import StringIO as cstringio
    input = raw_input
    long = long
    unicode = unicode
