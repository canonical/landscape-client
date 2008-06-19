import os
import sys
import time
import signal

from dbus.service import method
import dbus.glib
from dbus import DBusException, Array, Byte

from twisted.internet.defer import Deferred

from landscape.lib.dbus_util import (get_bus, get_object,
                                     method as async_method,
                                     byte_array, array_to_string,
                                     Object, ServiceUnknownError,
                                     SecurityError)
from landscape.tests.helpers import (
    LandscapeIsolatedTest, DBusHelper, LandscapeTest)
from landscape.tests.mocker import ARGS, KWARGS


class BoringService(Object):

    bus_name = "sample.service"
    object_path = "/com/example/BoringService"
    iface_name = "com.example.BoringService"

    @method(iface_name)
    def return1(self):
        return 1

    @method(iface_name)
    def error(self):
        1 / 0

    @method(iface_name)
    def return_none(self):
        return


class AsynchronousWrapperTests(LandscapeIsolatedTest):

    helpers = [DBusHelper]

    def setUp(self):
        super(AsynchronousWrapperTests, self).setUp()
        self.service = BoringService(self.bus)
        self.remote_service = get_object(self.bus,
                                         self.service.bus_name,
                                         self.service.object_path,
                                         self.service.iface_name)

    def test_get_bus(self):
        self.assertEquals(type(get_bus("session")), dbus.SessionBus)
        self.assertEquals(type(get_bus("system")), dbus.SystemBus)
        self.assertRaises(ValueError, get_bus, "nope")

    def test_get_object_returns_deferred(self):
        """
        There is a L{dbus.Bus.get_object} replacement, L{get_object}, which
        returns an object which returns Deferreds on method calls
        """
        result = self.remote_service.return1()
        self.assertTrue(isinstance(result, Deferred))
        result.addCallback(self.assertEquals, 1)
        return result

    def test_get_object_returns_failing_deferred(self):
        """
        The asynchronous method wrapper deals with errors appropriately, by
        converting them to errbacks on a Deferred.
        """
        result = self.remote_service.error()
        self.assertTrue(isinstance(result, Deferred))
        self.assertFailure(result, DBusException)
        return result

    def test_return_none(self):
        """
        L{get_object} has no problems with methods that don't return values.
        """
        result = self.remote_service.return_none()
        result.addCallback(self.assertEquals, ())
        return result

    def test_helper_methods(self):
        """The wrapper shouldn't get in the way of standard methods."""
        self.remote_service.connect_to_signal("nononono", lambda: None)

    def test_default_interface_name(self):
        """
        When an interface isn't provided to get_object(), one is automatically
        generated from the object_path.  This allows us to work with older
        versions of Python dbus without too much pain.
        """
        class MyService(Object):
            bus_name = "my.bus.name"
            object_path = "/my/Service"
            @method("my.Service")
            def return2(self):
                return 2
        service = MyService(self.bus)
        remote_service = get_object(self.bus, MyService.bus_name,
                                    MyService.object_path)

        result = remote_service.return2()
        result.addCallback(self.assertEquals, 2)
        return result


class HalfSynchronousService(Object):

    bus_name = "sample.service"
    object_path = "/com/example/UnitedStatesOfWhatever"
    iface_name = "com.example.UnitedStatesOfWhateverIface"

    def __init__(self, bus):
        super(HalfSynchronousService, self).__init__(bus)
        self.deferred = Deferred()

    @async_method(iface_name)
    def add1(self, i):
        return i + 1

    @async_method(iface_name)
    def return_none(self):
        return

    @async_method(iface_name)
    def sync_error(self):
        1 / 0

    @async_method(iface_name)
    def async(self):
        return self.deferred


class AsynchronousMethodTests(LandscapeIsolatedTest):

    helpers = [DBusHelper]

    def setUp(self):
        super(AsynchronousMethodTests, self).setUp()
        self.service = HalfSynchronousService(self.bus)
        self.remote_service = get_object(self.bus,
                                         self.service.bus_name,
                                         self.service.object_path,
                                         self.service.iface_name)

    def test_synchronous_method(self):
        """
        Using the L{landscape.lib.dbus_util.method} decorator to declare a
        method basically works the same as L{dbus.service.method}, if you
        return a value synchronously.
        """
        return self.remote_service.add1(3).addCallback(self.assertEquals, 4)

    def test_return_None(self):
        """
        Methods should be able to return None, and this will be translated to a
        return of no values.
        """
        d = self.remote_service.return_none()
        return d.addCallback(self.assertEquals, ())

    def test_asynchronous_method(self):
        """
        However, when a Deferred is returned, it will be handled so that the
        return value of the method is the ultimate result of the Deferred.
        """
        d = self.remote_service.async()
        d.addCallback(self.assertEquals, "hi")
        self.service.deferred.callback("hi")
        return d

    def test_synchronous_error(self):
        """
        Synchronous exceptions are propagated as normal.
        """
        self.log_helper.ignore_errors(ZeroDivisionError)
        d = self.remote_service.sync_error()
        def got_error(dbus_exception):
            # This is pretty much the best we can do, afaict; it doesn't
            # include any more information but the type.
            self.assertTrue("ZeroDivisionError" in str(dbus_exception))
        # assertFailure to make sure it *actually* fails
        # assertFailure causes the next callback to get the *exception* object
        # (not a Failure). That means we should add a callback to check stuff
        # about the exception, not an errback.
        self.assertFailure(d, DBusException)
        d.addCallback(got_error)
        return d

    def test_asynchronous_error(self):
        """
        Returning a Deferred which fails is propagated in the same way as a
        synchronous exception is.
        """
        self.log_helper.ignore_errors(ZeroDivisionError)
        # ignore the result of the method and convert it to an exception
        self.service.deferred.addCallback(lambda ignored: 1/0)
        d = self.remote_service.async()

        def got_error(dbus_exception):
            # This is pretty much the best we can do, afaict; it doesn't
            # include any more information but the type.
            self.assertTrue("ZeroDivisionError" in str(dbus_exception),
                            str(dbus_exception))

        # fire off the result of the async method call
        self.service.deferred.callback("ignored")

        # assertFailure to make sure it *actually* fails
        # assertFailure causes the next callback to get the *exception* object
        # (not a Failure). That means we should add a callback to check stuff
        # about the exception, not an errback.
        self.assertFailure(d, DBusException)
        d.addCallback(got_error)
        return d

    def test_errors_get_logged(self):
        """
        An exception raised during processing of a method call should be
        logged.
        """
        self.log_helper.ignore_errors(ZeroDivisionError)
        d = self.remote_service.sync_error()
        def got_error(failure):
            log = self.logfile.getvalue()
            self.assertTrue("Traceback" in log)
            self.assertTrue("ZeroDivisionError" in log)
        return d.addErrback(got_error)


class ErrorHandlingTests(LandscapeIsolatedTest):

    helpers = [DBusHelper]

    def test_service_unknown(self):
        remote_service = get_object(self.bus, "com.foo", "/com/foo/Bar",
                                    "com.foo", retry_timeout=0)
        d = remote_service.foo()
        self.assertFailure(d, ServiceUnknownError)
        return d



class SecurityErrorTests(LandscapeTest):
    """Tests for cases that SecurityError is raised."""

    def setUp(self):
        super(SecurityErrorTests, self).setUp()
        self.bus = self.mocker.mock()
        self.service = self.mocker.mock()
        self.bus.get_object("com.foo", "/com/foo", introspect=False)
        self.mocker.result(self.service)
        self.mocker.count(0, None)
        self.remote = get_object(self.bus, "com.foo", "/com/foo")

    def _test_security_error(self, error_message):
        def raise_dbus_error(*args, **kw):
            kw["error_handler"](DBusException(error_message))

        self.service.send_message(ARGS, KWARGS)
        self.mocker.call(raise_dbus_error)
        self.mocker.replay()

        d = self.remote.send_message({"type": "text-message",
                                      "message": "hello"})
        self.assertFailure(d, SecurityError)
        return d

    def test_feisty_security_error(self):
        """
        When an exception that looks like a security error from DBUS
        0.80.x is raised, this should be translated to a
        L{SecurityError}.
        """
        return self._test_security_error(
            "A security policy in place prevents this sender from sending "
            "this message to this recipient, see message bus configuration "
            "file (rejected message had interface "
            '"com.canonical.landscape" member "send_message" error name '
            '"(unset)" destination ":1.107")')

    def test_gutsy_security_error(self):
        """
        When an exception that looks like a security error on DBUS 0.82.x
        is raised, this should be translated to a L{SecurityError}.
        """
        return self._test_security_error(
            "org.freedesktop.DBus.Error.AccessDenied: A security "
            "policy in place prevents this sender from sending this "
            "message to this recipient, see message bus configuration "
            "file (rejected message had interface "
            '"com.canonical.landscape" member "send_message" error '
            'name "(unset)" destination ":1.15")')




class RetryTests(LandscapeIsolatedTest):

    helpers = [DBusHelper]

    def setUp(self):
        super(RetryTests, self).setUp()
        self.pids = []
        self.remote_service = get_object(self.bus,
                                         HalfSynchronousService.bus_name,
                                         HalfSynchronousService.object_path,
                                         HalfSynchronousService.iface_name)

    def tearDown(self):
        super(RetryTests, self).tearDown()
        for pid in self.pids:
            try:
                os.kill(pid, signal.SIGKILL)
                os.waitpid(pid, 0)
            except OSError:
                pass #LOL!

    def test_retry_on_first_call(self):
        """
        If an object is unavailable when a method is called,
        AsynchronousProxyMethod will continue trying to get it for a while.
        """
        d = self.remote_service.add1(0)
        HalfSynchronousService(self.bus)
        return d.addCallback(self.assertEquals, 1)

    def _start_service_in_subprocess(self):
        executable = self.make_path("""\
#!%s
from twisted.internet.glib2reactor import install
install()
from twisted.internet import reactor

from dbus import SessionBus

import sys
sys.path = %r

from landscape.lib.tests.test_dbus_util import HalfSynchronousService

bus = SessionBus()
HalfSynchronousService(bus)
reactor.run()
""" % (sys.executable, sys.path))
        os.chmod(executable, 0755)
        pid = os.fork()
        if pid == 0:
            os.execlp(executable, executable)
        self.pids.append(pid)

    def _stop_service_in_subprocess(self):
        os.kill(self.pids[-1], signal.SIGKILL)
        os.waitpid(self.pids[-1], 0)

    def test_retry_on_second_call(self):
        """
        Either get_object or an actual method call may raise an exception about
        an object not being available. This test ensures that the exception
        raised from the method call is handled to retry, by causing the object
        to be cached with an initial successful call.
        """
        self._start_service_in_subprocess()
        result = self.remote_service.add1(0)
        def got_first_result(result):
            self.assertEquals(result, 1)
            self._stop_service_in_subprocess()
            second_result = self.remote_service.add1(1)
            self._start_service_in_subprocess()
            return second_result
        result.addCallback(got_first_result)
        result.addCallback(self.assertEquals, 2)
        return result

    def test_timeout_time(self):
        """
        It's possible to specify the retry timout to use, and when the timeout
        is reached, the underlying dbus error will be raised.
        """
        remote_service = get_object(self.bus,
                                    HalfSynchronousService.bus_name,
                                    HalfSynchronousService.object_path,
                                    retry_timeout=1)

        start_time = time.time()
        result = remote_service.add1(0)
        self.assertFailure(result, ServiceUnknownError)

        def got_error(exception):
            self.assertTrue(time.time() - start_time > 1)
        return result.addCallback(got_error)


    def test_catch_synchronous_errors_from_method(self):
        """
        DBus sometimes raises synchronous errors from calling the method, for
        example, when the value passed does not match the signature. The
        asynchronous call wrapper should handle this case and fail the
        deferred.
        """
        self.log_helper.ignore_errors(".*Unable to set arguments.*")
        HalfSynchronousService(self.bus)
        d = self.remote_service.add1(None)
        self.assertFailure(d, TypeError)
        return d


class UtilityTests(LandscapeTest):
    def test_array_to_string(self):
        self.assertEquals(array_to_string([102, 111, 111]), "foo")
        self.assertEquals(
            array_to_string(Array([Byte(102), Byte(111), Byte(111)])),
            "foo")

    def test_byte_array(self):
        self.assertEquals(byte_array("foo"), [102, 111, 111])
        self.assertEquals(byte_array("foo"),
                          Array([Byte(102), Byte(111), Byte(111)]))

    def test_array_to_string_with_horrible_dapper_signing_bug(self):
        """
        In older versions of dbus, bytes would be deserialized incorrectly as
        signed. array_to_string compensates for this.
        """
        self.assertEquals(array_to_string([-56, -127]), chr(200) + chr(129))
