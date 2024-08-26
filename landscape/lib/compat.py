# flake8: noqa
# TiCS: disabled

_PY3 = True

import pickle as cPickle
from configparser import ConfigParser, NoOptionError

SafeConfigParser = ConfigParser

import _thread as thread

from io import StringIO

stringio = cstringio = StringIO
from builtins import input

unicode = str
long = int
