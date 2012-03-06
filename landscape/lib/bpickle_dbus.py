"""
Different versions of the Python DBus bindings return different types
to represent integers, strings, lists, etc.  Older versions return
builtin Python types: C{int}, C{str}, C{list}, etc.  Newer versions
return DBus-specific wrappers: C{Int16}, C{String}, C{Array}, etc.
Failures occur when DBus types are used because bpickle doesn't know
that an C{Int16} is really an C{int} and that an C{Array} is really a
C{list}.

L{install} and L{uninstall} can install and remove extensions that
make bpickle work with DBus types.
"""

import dbus

from landscape.lib import bpickle


def install():
    """Install bpickle extensions for DBus types."""
    for type, function in get_dbus_types():
        bpickle.dumps_table[type] = function


def uninstall():
    """Uninstall bpickle extensions for DBus types."""
    for type, function in get_dbus_types():
        del bpickle.dumps_table[type]


def dumps_utf8string(obj):
    """
    Convert the specified L{dbus.types.UTF8String} to bpickle's
    representation for C{unicode} data.
    """
    return "u%s:%s" % (len(obj), obj)


def dumps_double(obj):
    """
    Convert a dbus.types.Double into a floating point representation.
    """
    return "f%r;" % float(obj)


def get_dbus_types():
    """
    Generator yields C{(type, bpickle_function)} for available DBus
    types.
    """
    for (type_name, function) in [("Boolean", bpickle.dumps_bool),
                                  ("Int16", bpickle.dumps_int),
                                  ("UInt16", bpickle.dumps_int),
                                  ("Int32", bpickle.dumps_int),
                                  ("UInt32", bpickle.dumps_int),
                                  ("Int64", bpickle.dumps_int),
                                  ("UInt64", bpickle.dumps_int),
                                  ("Double", dumps_double),
                                  ("Array", bpickle.dumps_list),
                                  ("Dictionary", bpickle.dumps_dict),
                                  ("String", bpickle.dumps_unicode),
                                  ("UTF8String", dumps_utf8string)]:
        type = getattr(dbus.types, type_name, None)
        if type is not None:
            yield type, function
