"""
Extend the regular Twisted reactor with event-handling features.
"""
from __future__ import absolute_import

import logging
import time

from twisted.internet.threads import deferToThread

from landscape.lib.format import format_object


class InvalidID(Exception):
    """Raised when an invalid ID is used with reactor.cancel_call()."""


class CallHookError(Exception):
    """Raised when hooking on a reactor incorrectly."""


class EventID(object):
    """Unique identifier for an event handler.

    @param event_type: Name of the event type handled by the handler.
    @param pair: Binary tuple C{(handler, priority)} holding the handler
        function and its priority.
    """

    def __init__(self, event_type, pair):
        self._event_type = event_type
        self._pair = pair


class EventHandlingReactorMixin(object):
    """Fire events identified by strings and register handlers for them.

    Note that event handlers are executed synchronously when the C{fire} method
    is called, so unit-tests can generally exercise events without needing to
    run the real Twisted reactor (except of course if the event handlers
    themselves contain asynchronous calls that need the Twisted reactor
    running).
    """

    def __init__(self):
        super(EventHandlingReactorMixin, self).__init__()
        self._event_handlers = {}

    def call_on(self, event_type, handler, priority=0):
        """Register an event handler.

        The handler will be invoked every time an event of the given type
        is fired (there's no need to re-register the handler after the
        event is fired).

        @param event_type: The name of the event type to handle.
        @param handler: The function handling the given event type.
        @param priority: The priority of the given handler function.

        @return: The L{EventID} of the registered handler.
        """
        pair = (handler, priority)

        handlers = self._event_handlers.setdefault(event_type, [])
        handlers.append(pair)
        handlers.sort(key=lambda pair: pair[1])

        return EventID(event_type, pair)

    def fire(self, event_type, *args, **kwargs):
        """Fire an event of a given type.

        Call all handlers registered for the given C{event_type}, in order
        of priority.

        @param event_type: The name of the event type to fire.
        @param args: Positional arguments to pass to the registered handlers.
        @param kwargs: Keyword arguments to pass to the registered handlers.
        """
        logging.debug("Started firing %s.", event_type)
        results = []
        # Make a copy of the handlers that are registered at this point in
        # time, so we have a stable list in case handlers are cancelled
        # dynamically by executing the handlers themselves.
        handlers = list(self._event_handlers.get(event_type, ()))
        for handler, priority in handlers:
            try:
                logging.debug("Calling %s for %s with priority %d.",
                              format_object(handler), event_type, priority)
                results.append(handler(*args, **kwargs))
            except KeyboardInterrupt:
                logging.exception("Keyboard interrupt while running event "
                                  "handler %s for event type %r with "
                                  "args %r %r.", format_object(handler),
                                  event_type, args, kwargs)
                self.stop()
                raise
            except Exception:
                logging.exception("Error running event handler %s for "
                                  "event type %r with args %r %r.",
                                  format_object(handler), event_type,
                                  args, kwargs)
        logging.debug("Finished firing %s.", event_type)
        return results

    def cancel_call(self, id):
        """Unregister an event handler.

        @param id: the L{EventID} of the handler to unregister.
        """
        if type(id) is EventID:
            self._event_handlers[id._event_type].remove(id._pair)
        else:
            raise InvalidID("EventID instance expected, received %r" % id)


class ReactorID(object):

    def __init__(self, timeout):
        self._timeout = timeout


class EventHandlingReactor(EventHandlingReactorMixin):
    """Wrap and add functionalities to the Twisted reactor.

    This is essentially a facade around the twisted.internet.reactor and
    will delegate to it for mostly everything except event handling features
    which are implemented using EventHandlingReactorMixin.
    """

    def __init__(self):
        from twisted.internet import reactor
        from twisted.internet.task import LoopingCall
        self._LoopingCall = LoopingCall
        self._reactor = reactor
        self._cleanup()
        self.callFromThread = reactor.callFromThread
        super(EventHandlingReactor, self).__init__()

    def time(self):
        """Get current time.

        @see L{time.time}
        """
        return time.time()

    def call_later(self, *args, **kwargs):
        """Call a function later.

        Simply call C{callLater(*args, **kwargs)} and return its result.

        @see: L{twisted.internet.interfaces.IReactorTime.callLater}.

        """
        return self._reactor.callLater(*args, **kwargs)

    def call_every(self, seconds, f, *args, **kwargs):
        """Call a function repeatedly.

        Create a new L{twisted.internet.task.LoopingCall} object and
        start it.

        @return: the created C{LoopingCall} object.
        """
        lc = self._LoopingCall(f, *args, **kwargs)
        lc.start(seconds, now=False)
        return lc

    def cancel_call(self, id):
        """Cancel a scheduled function or event handler.

        @param id: The function call or handler to remove. It can be an
            L{EventID}, a L{LoopingCall} or a C{IDelayedCall}, as returned
            by L{call_on}, L{call_every} and L{call_later} respectively.
        """
        if isinstance(id, EventID):
            return EventHandlingReactorMixin.cancel_call(self, id)
        if isinstance(id, self._LoopingCall):
            return id.stop()
        if id.active():
            id.cancel()

    def call_when_running(self, f):
        """Schedule a function to be called when the reactor starts running."""
        self._reactor.callWhenRunning(f)

    def call_in_main(self, f, *args, **kwargs):
        """Cause a function to be executed by the reactor thread.

        @param f: The callable object to execute.
        @param args: The arguments to call it with.
        @param kwargs: The keyword arguments to call it with.

        @see: L{twisted.internet.interfaces.IReactorThreads.callFromThread}
        """
        self._reactor.callFromThread(f, *args, **kwargs)

    def call_in_thread(self, callback, errback, f, *args, **kwargs):
        """
        Execute a callable object in a new separate thread.

        @param callback: A function to call in case C{f} was successful, it
            will be passed the return value of C{f}.
        @param errback: A function to call in case C{f} raised an exception,
            it will be pass a C{(type, value, traceback)} tuple giving
            information about the raised exception (see L{sys.exc_info}).

        @note: Both C{callback} and C{errback} will be executed in the
            the parent thread.
        """
        def on_success(result):
            if callback:
                return callback(result)

        def on_failure(failure):
            exc_info = (failure.type, failure.value, failure.tb)
            if errback:
                errback(*exc_info)
            else:
                logging.error(exc_info[1], exc_info=exc_info)

        deferred = deferToThread(f, *args, **kwargs)
        deferred.addCallback(on_success)
        deferred.addErrback(on_failure)

    def listen_unix(self, socket, factory):
        """Start listening on a Unix socket."""
        return self._reactor.listenUNIX(socket, factory, wantPID=True)

    def connect_unix(self, socket, factory):
        """Connect to a Unix socket."""
        return self._reactor.connectUNIX(socket, factory)

    def run(self):
        """Start the reactor, a C{"run"} event will be fired."""

        self.fire("run")
        self._reactor.run()
        self.fire("stop")

    def stop(self):
        """Stop the reactor, a C{"stop"} event will be fired."""
        self._reactor.stop()
        self._cleanup()

    def _cleanup(self):
        # Since the reactor is global, we should clean it up when we
        # initialize one of our wrappers.
        for call in self._reactor.getDelayedCalls():
            if call.active():
                call.cancel()
