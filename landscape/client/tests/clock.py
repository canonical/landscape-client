# Copyright (c) 2001-2007 Twisted Matrix Laboratories.

# Permission is hereby granted, free of charge, to any person obtaining
# a copy of this software and associated documentation files (the
# "Software"), to deal in the Software without restriction, including
# without limitation the rights to use, copy, modify, merge, publish,
# distribute, sublicense, and/or sell copies of the Software, and to
# permit persons to whom the Software is furnished to do so, subject to
# the following conditions:

# The above copyright notice and this permission notice shall be
# included in all copies or substantial portions of the Software.

# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
# NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE
# LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION
# OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION
# WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

"""
Copies of certain classes from Twisted 2.5, so that we can use the
functionality they provide with Twisted 2.2 and up. These should
really only be used from the test suite for now.

Currently:

 * L{twisted.internet.task.Clock}, which is new in Twisted 2.5.
 * L{twisted.internet.base.DelayedCall}, which didn't grow its
   C{seconds} argument until after Twisted 2.2.
"""
from twisted.internet import error
from twisted.python.runtime import seconds as runtimeSeconds
from twisted.python import reflect
from twisted.python.compat import iteritems

import traceback


class Clock:
    """
    Provide a deterministic, easily-controlled implementation of
    L{IReactorTime.callLater}.  This is commonly useful for writing
    deterministic unit tests for code which schedules events using this API.
    """
    rightNow = 0.0

    def __init__(self):
        self.calls = []

    def seconds(self):
        """
        Pretend to be time.time().  This is used internally when an operation
        such as L{IDelayedCall.reset} needs to determine a a time value
        relative to the current time.

        @rtype: C{float}
        @return: The time which should be considered the current time.
        """
        return self.rightNow

    def callLater(self, when, what, *a, **kw):
        """
        See L{twisted.internet.interfaces.IReactorTime.callLater}.
        """
        self.calls.append(
            DelayedCall(self.seconds() + when,
                        what, a, kw,
                        self.calls.remove,
                        (lambda c: None),
                        self.seconds))
        self.calls.sort(key=lambda a: a.getTime())
        return self.calls[-1]

    def advance(self, amount):
        """
        Move time on this clock forward by the given amount and run whatever
        pending calls should be run.

        @type amount: C{float}
        @param amount: The number of seconds which to advance this clock's
        time.
        """
        self.rightNow += amount
        while self.calls and self.calls[0].getTime() <= self.seconds():
            call = self.calls.pop(0)
            call.called = 1
            call.func(*call.args, **call.kw)

    def pump(self, timings):
        """
        Advance incrementally by the given set of times.

        @type timings: iterable of C{float}
        """
        for amount in timings:
            self.advance(amount)


class DelayedCall:

    # enable .debug to record creator call stack, and it will be logged if
    # an exception occurs while the function is being run
    debug = False
    _str = None

    def __init__(self, time, func, args, kw, cancel, reset,
                 seconds=runtimeSeconds):
        """
        @param time: Seconds from the epoch at which to call C{func}.
        @param func: The callable to call.
        @param args: The positional arguments to pass to the callable.
        @param kw: The keyword arguments to pass to the callable.
        @param cancel: A callable which will be called with this
            DelayedCall before cancellation.
        @param reset: A callable which will be called with this
            DelayedCall after changing this DelayedCall's scheduled
            execution time. The callable should adjust any necessary
            scheduling details to ensure this DelayedCall is invoked
            at the new appropriate time.
        @param seconds: If provided, a no-argument callable which will be
            used to determine the current time any time that information is
            needed.
        """
        self.time, self.func, self.args, self.kw = time, func, args, kw
        self.resetter = reset
        self.canceller = cancel
        self.seconds = seconds
        self.cancelled = self.called = 0
        self.delayed_time = 0
        if self.debug:
            self.creator = traceback.format_stack()[:-2]

    def getTime(self):
        """Return the time at which this call will fire

        @rtype: C{float}
        @return: The number of seconds after the epoch at which this call is
        scheduled to be made.
        """
        return self.time + self.delayed_time

    def cancel(self):
        """Unschedule this call

        @raise AlreadyCancelled: Raised if this call has already been
        unscheduled.

        @raise AlreadyCalled: Raised if this call has already been made.
        """
        if self.cancelled:
            raise error.AlreadyCancelled
        elif self.called:
            raise error.AlreadyCalled
        else:
            self.canceller(self)
            self.cancelled = 1
            if self.debug:
                self._str = str(self)
            del self.func, self.args, self.kw

    def reset(self, secondsFromNow):
        """Reschedule this call for a different time

        @type secondsFromNow: C{float}
        @param secondsFromNow: The number of seconds from the time of the
        C{reset} call at which this call will be scheduled.

        @raise AlreadyCancelled: Raised if this call has been cancelled.
        @raise AlreadyCalled: Raised if this call has already been made.
        """
        if self.cancelled:
            raise error.AlreadyCancelled
        elif self.called:
            raise error.AlreadyCalled
        else:
            newTime = self.seconds() + secondsFromNow
            if newTime < self.time:
                self.delayed_time = 0
                self.time = newTime
                self.resetter(self)
            else:
                self.delayed_time = newTime - self.time

    def delay(self, secondsLater):
        """Reschedule this call for a later time

        @type secondsLater: C{float}
        @param secondsLater: The number of seconds after the originally
        scheduled time for which to reschedule this call.

        @raise AlreadyCancelled: Raised if this call has been cancelled.
        @raise AlreadyCalled: Raised if this call has already been made.
        """
        if self.cancelled:
            raise error.AlreadyCancelled
        elif self.called:
            raise error.AlreadyCalled
        else:
            self.delayed_time += secondsLater
            if self.delayed_time < 0:
                self.activate_delay()
                self.resetter(self)

    def activate_delay(self):
        self.time += self.delayed_time
        self.delayed_time = 0

    def active(self):
        """Determine whether this call is still pending

        @rtype: C{bool}
        @return: True if this call has not yet been made or cancelled,
        False otherwise.
        """
        return not (self.cancelled or self.called)

    def __le__(self, other):
        return self.time <= other.time

    def __str__(self):
        if self._str is not None:
            return self._str
        if hasattr(self, 'func'):
            if hasattr(self.func, 'func_name'):
                func = self.func.func_name
                if hasattr(self.func, 'im_class'):
                    func = self.func.im_class.__name__ + '.' + func
            else:
                func = reflect.safe_repr(self.func)
        else:
            func = None

        now = self.seconds()
        L = ["<DelayedCall %s [%ss] called=%s cancelled=%s" % (
                id(self), self.time - now, self.called, self.cancelled)]
        if func is not None:
            L.extend((" ", func, "("))
            if self.args:
                L.append(", ".join([reflect.safe_repr(e) for e in self.args]))
                if self.kw:
                    L.append(", ")
            if self.kw:
                L.append(", ".join([
                    '%s=%s' % (k, reflect.safe_repr(v))
                    for (k, v) in iteritems(self.kw)]))
            L.append(")")

        if self.debug:
            L.append(("\n\ntraceback at creation: \n\n%s"
                      ) % ('    '.join(self.creator)))
        L.append('>')

        return "".join(L)
