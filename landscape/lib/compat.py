# flake8: noqa
# TiCS: disabled

_PY3 = True

from configparser import ConfigParser, NoOptionError

SafeConfigParser = ConfigParser

unicode = str
long = int
