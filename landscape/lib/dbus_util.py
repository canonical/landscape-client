"""DBus utilities, especially for helping with asynchronous use of DBUS.

Notable things in this module:

 - L{get_object} - Get a DBUS object which returns Deferreds.
 - L{method} - Declare a server-side DBUS method responder that can return a
   Deferred in order to delay the return of a DBUS method call.

Importing this module will call L{hack_dbus_get_object}.
"""
import sys
import time
import traceback

from twisted.internet.defer import Deferred, execute
from twisted.python.failure import Failure
from twisted.python.reflect import namedClass

from dbus.service import Object, BusName, method as dbus_method
from dbus import Array, Byte
from dbus.exceptions import DBusException
import dbus

from landscape.lib.log import log_failure

# These should perhaps be registered externally
SAFE_EXCEPTIONS = ["landscape.schema.InvalidError",
                   "landscape.broker.registration.InvalidCredentialsError"]
PYTHON_EXCEPTION_PREFIX = "org.freedesktop.DBus.Python."

class ServiceUnknownError(Exception):
    """Raised when the DBUS Service cannot be found."""

class SecurityError(Exception):
    """Raised when the DBUS Service is inaccessible."""

class NoReplyError(Exception):
    """Raised when a DBUS service doesn't respond."""


class Object(Object):
    """
    Convenience for creating dbus objects with a particular bus name and object
    path.

    @cvar bus_name: The bus name to listen on.
    @cvar object_path: The path to listen on.
    """
    def __init__(self, bus):
        super(Object, self).__init__(
            BusName(self.bus_name, bus), object_path=self.object_path)
        self.bus = bus

def _method_reply_error(connection, message, exception):
    from dbus import dbus_bindings
    if '_dbus_error_name' in exception.__dict__:
        name = exception._dbus_error_name
    elif exception.__module__ == '__main__':
        name = 'org.freedesktop.DBus.Python.%s' % exception.__class__.__name__
    else:
        name = 'org.freedesktop.DBus.Python.%s.%s' % (
            exception.__module__, exception.__class__.__name__)

    # LS CUSTOM
    current_exception = sys.exc_info()[1]
    if exception is current_exception:
        contents = traceback.format_exc()
    elif hasattr(exception, "_ls_traceback_string"):
        contents = exception._ls_traceback_string
    else:
        contents = ''.join(traceback.format_exception_only(exception.__class__,
                                                           exception))
    # Explicitly jam the name on the front of the contents so that our error
    # detection works.
    contents = "%s: %s" % (name, contents)
    # END LS CUSTOM

    reply = dbus_bindings.Error(message, name, contents)

    connection.send(reply)

if dbus.version[:2] <= (0, 70):
    import dbus.service
    dbus.service._method_reply_error = _method_reply_error


def method(interface, **kwargs):
    """
    Factory for decorators used export methods of a L{dbus.service.Object}
    to be exported on the D-Bus.

    If a method returns a L{Deferred}, it will automatically be handled.
    """
    def decorator(function):
        def inner(self, *args, **kwargs):
            __cb = kwargs.pop("__cb")
            __eb = kwargs.pop("__eb")

            def callback(result):
                # dbus can't serialize None; convert it to a return of 0
                # values.
                if result is None:
                    __cb()
                else:
                    __cb(result)

            def errback(failure):
                # An idea: If we ever want to be able to intentionally send
                # exceptions to the other side and don't want to log them, we
                # could have an exception type of which subclasses won't be
                # logged, but only passed to __eb.
                log_failure(failure, "Error while running DBUS method handler!")
                exception = failure.value
                exception._ls_traceback_string = failure.getTraceback()
                __eb(exception)

            # don't look. The intent of all of this is to allow failure.tb to
            # be live by the time our errback is called. If we use
            # maybeDeferred, the .tb will never be available in a callback.
            d = Deferred()
            d.addCallback(lambda ignored: function(self, *args, **kwargs))
            d.addCallbacks(callback, errback)
            d.callback(None)

        byte_arrays = kwargs.pop("byte_arrays", False)
        if byte_arrays:
            raise NotImplementedError(
                "Please don't use byte_arrays; it doesn't work on old "
                "versions of python-dbus.")

        inner = dbus_method(interface, **kwargs)(inner)
        # We don't pass async_callbacks to dbus_method, because it does some
        # dumb introspection on arguments of the function. Basically it
        # requires the callbacks to be declared as named parameters, instead of
        # using **kw, which is problematic for us because we also want to take
        # arbitrary arguments to pass on to the original function.

        # To get around this we just set the internal attribute which
        # dbus_method would set itself that specifies what the callback keyword
        # arguments are.
        inner._dbus_async_callbacks = ("__cb", "__eb")
        return inner
    return decorator


DBUS_CALL_TIMEOUT = 70

class AsynchronousProxyMethod(object):
    """
    A wrapper for L{dbus.proxies.ProxyMethod}s that causes calls
    to return L{Deferred}s.
    """

    def __init__(self, wrapper, method_name, dbus_interface,
                 retry_timeout):
        self.wrapper = wrapper
        self.method_name = method_name
        self._dbus_interface = dbus_interface
        self._retry_timeout = retry_timeout

    def __call__(self, *args, **kwargs):
        result = Deferred()
        self._call_with_retrying(result, args, kwargs)
        result.addErrback(self._massage_errors)
        return result

    def _massage_errors(self, failure):
        """Python DBUS has terrible exception reporting.

        Convert many types of errors which into things which are
        actually catchable.
        """
        failure.trap(DBusException)
        message = failure.getErrorMessage()
        # handle different crappy error messages from various versions
        # of DBUS.
        if ("Did not receive a reply" in message
            or "No reply within specified time" in message):
            raise NoReplyError(message)
        if (message.startswith("A security policy in place")
            or message.startswith("org.freedesktop.DBus.Error.AccessDenied")):
            raise SecurityError()
        if "was not provided by any .service" in message:
            raise ServiceUnknownError()

        if message.startswith(PYTHON_EXCEPTION_PREFIX):
            python_exception = message[len(PYTHON_EXCEPTION_PREFIX)
                                       :message.find(":")]
            if python_exception in SAFE_EXCEPTIONS:
                raise namedClass(python_exception)(message)

        return failure

    def _retry_on_failure(self, failure, result,
                          args, kwargs, first_failure_time):
        failure.trap(DBusException)
        failure_repr = str(failure) # Yay dbus. :-(
        if (("org.freedesktop.DBus.Error.ServiceUnknown" in failure_repr or
             "was not provided by any .service files" in failure_repr) and
            self._retry_timeout > time.time() - first_failure_time):
            from twisted.internet import reactor
            reactor.callLater(0.1, self._call_with_retrying,
                              result, args, kwargs, first_failure_time)
        else:
            result.errback(failure)

    def _call_with_retrying(self, result, args, kwargs,
                            first_failure_time=None):
        reset_cache = bool(first_failure_time)
        if first_failure_time is None:
            first_failure_time = time.time()
        execute_result = execute(self.wrapper.get_object, reset_cache)
        execute_result.addCallback(self._actually_call, result, args, kwargs,
                                   first_failure_time)
        execute_result.addErrback(self._retry_on_failure,
                                  result, args, kwargs, first_failure_time)

    def _actually_call(self, object, result, args, kwargs, first_failure_time):
        if self.method_name in dir(object):
            # It's a normal method call, such as connect_to_signal().
            local_method = getattr(object, self.method_name)
            result.callback(local_method(*args, **kwargs))
        else:
            method = getattr(object, self.method_name)
            def got_result(*result_args):
                if len(result_args) == 1:
                    result.callback(result_args[0])
                else:
                    result.callback(result_args)

            def got_error(exception):
                failure = Failure(exception)
                self._retry_on_failure(failure, result, args, kwargs,
                                       first_failure_time)
            kwargs["reply_handler"] = got_result
            kwargs["error_handler"] = got_error
            kwargs["dbus_interface"] = self._dbus_interface
            try:
                method(*args, **kwargs)
            except Exception, e:
                result.errback()

class AsynchronousDBUSObjectWrapper(object):
    """
    A wrapper for L{dbus.proxies.ProxyObject}s which causes all method method
    calls to return L{Deferred}s (by way of L{AsynchronousProxyMethod}).
    """
    def __init__(self, bus, bus_name, path, retry_timeout,
                 dbus_interface=None):
        """
        @param bus: The bus.
        """
        self._bus = bus
        self._bus_name = bus_name
        self._path = path
        self._object = None
        if dbus_interface is None:
            dbus_interface = path.strip("/").replace("/", ".")
        self._dbus_interface = dbus_interface
        self._retry_timeout = retry_timeout

    def get_object(self, reset_cache=False):
        if reset_cache:
            self._object = None
        if self._object is None:
            self._object = self._bus.get_object(self._bus_name, self._path,
                                                introspect=False)
        return self._object

    def __getattr__(self, name):
        """
        Get a L{AsynchronousProxyMethod} wrapped around the original attribute
        of the C{dbus_object}.
        """
        return AsynchronousProxyMethod(self, name, self._dbus_interface,
                                       self._retry_timeout)

    def __repr__(self):
        return "<AsynchronousDBUSObjectWrapper at 0x%x on %r>" % (
            id(self), self.dbus_object)


def get_bus(name):
    """Create a DBUS bus by name."""
    bus_class_name = name.capitalize() + "Bus"
    try:
        bus_class = getattr(dbus, bus_class_name)
    except AttributeError:
        raise ValueError("Invalid bus name: %r" % name)
    return bus_class()


def get_object(bus, bus_name, object_path, interface=None, retry_timeout=None):
    """Fetch a DBUS object on which all methods will be asynchronous."""
    if retry_timeout is None:
        retry_timeout = DBUS_CALL_TIMEOUT
    return AsynchronousDBUSObjectWrapper(bus, bus_name, object_path,
                                         retry_timeout, interface)


def hack_dbus_get_object():
    """
    Old versions of dbus did not support the 'introspect' argument to
    Bus.get_object. This method installs a version that does.
    """
    def get_object(self, service_name, object_path, introspect=True):
        return self.ProxyObjectClass(self, service_name,
                                     object_path, introspect=introspect)
    dbus.Bus.get_object = get_object

if dbus.version[:2] < (0, 80):
    hack_dbus_get_object()


def byte_array(bytestring):
    """Convert a Python str to an L{Array} of L{Byte}s.

    This should be used instead of L{dbus.ByteArray} because in old versions of
    dbus it is not serialized properly.
    """
    return Array(Byte(ord(c)) for c in bytestring)


def array_to_string(array):
    """Convert an L{Array} of L{Byte}s (or integers) to a Python str.
    """
    result = []
    # HOLY LORD dbus has horrible bugs
    for item in array:
        if item < 0:
            item = item + 256
        result.append(chr(item))
    return "".join(result)
