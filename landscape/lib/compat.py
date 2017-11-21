# flake8: noqa

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
