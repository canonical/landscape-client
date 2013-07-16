"""
Extend the regular Twisted reactor with event-handling features.
"""
import time
import sys
import logging
import bisect

from twisted.python.failure import Failure
from twisted.internet.error import ConnectError
from twisted.internet.threads import deferToThread

from landscape.log import format_object


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
            except:
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


class LandscapeReactor(EventHandlingReactorMixin):
    """Wrap and add functionalities to the Twisted reactor.

    This is essentially a facade around the L{twisted.internet.reactor} and
    will delegate to it for mostly everything except event handling features
    which are implemented using L{EventHandlingReactorMixin}.
    """

    def __init__(self):
        from twisted.internet import reactor
        from twisted.internet.task import LoopingCall
        self._LoopingCall = LoopingCall
        self._reactor = reactor
        self._cleanup()
        self.callFromThread = reactor.callFromThread
        super(LandscapeReactor, self).__init__()

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


class FakeReactorID(object):

    def __init__(self, data):
        self.active = True
        self._data = data


class FakeReactor(EventHandlingReactorMixin):
    """A fake reactor with the same API of L{LandscapeReactor}.

    This reactor emulates the asychronous interface of L{LandscapeReactor}, but
    implementing it in a synchronous way, for easier unit-testing.

    Note that the C{listen_unix} method is *not* emulated, but rather inherited
    blindly from L{UnixReactorMixin}, this means that there's no way to control
    it in a synchronous way (see the docstring of the mixin). A better approach
    would be to fake the AMP transport (i.e. fake the twisted abstractions
    around Unix sockets), and implement a fake version C{listen_unix}, but this
    hasn't been done yet.
    """
    # XXX probably this shouldn't be a class attribute, but we need client-side
    # FakeReactor instaces to be aware of listening sockets created by
    # server-side FakeReactor instances.
    _socket_paths = {}

    def __init__(self):
        super(FakeReactor, self).__init__()
        self._current_time = 0
        self._calls = []
        self.hosts = {}
        self._threaded_callbacks = []

        # XXX we need a reference to the Twisted reactor as well because
        # some tests use it
        from twisted.internet import reactor
        self._reactor = reactor

    def time(self):
        return float(self._current_time)

    def call_later(self, seconds, f, *args, **kwargs):
        scheduled_time = self._current_time + seconds
        call = (scheduled_time, f, args, kwargs)
        bisect.insort_left(self._calls, call)
        return FakeReactorID(call)

    def call_every(self, seconds, f, *args, **kwargs):

        def fake():
            # update the call so that cancellation will continue
            # working with the same ID. And do it *before* the call
            # because the call might cancel it!
            call._data = self.call_later(seconds, fake)._data
            try:
                f(*args, **kwargs)
            except:
                if call.active:
                    self.cancel_call(call)
                raise
        call = self.call_later(seconds, fake)
        return call

    def cancel_call(self, id):
        if type(id) is FakeReactorID:
            if id._data in self._calls:
                self._calls.remove(id._data)
            id.active = False
        else:
            super(FakeReactor, self).cancel_call(id)

    def call_when_running(self, f):
        # Just schedule a call that will be kicked by the run() method.
        self.call_later(0, f)

    def call_in_main(self, f, *args, **kwargs):
        """Schedule a function for execution in the main thread."""
        self._threaded_callbacks.append(lambda: f(*args, **kwargs))

    def call_in_thread(self, callback, errback, f, *args, **kwargs):
        """Emulate L{LandscapeReactor.call_in_thread} without spawning threads.

        Note that running threaded callbacks here doesn't reflect reality,
        since they're usually run while the main reactor loop is active. At
        the same time, this is convenient as it means we don't need to run
        the the real Twisted reactor with to test actions performed on
        completion of specific events (e.g. L{MessageExchange.exchange} uses
        call_in_thread to run the HTTP request in a separate thread, because
        we use libcurl which is blocking). IOW, it's easier to test things
        synchronously.
        """
        self._in_thread(callback, errback, f, args, kwargs)
        self._run_threaded_callbacks()

    def listen_unix(self, socket_path, factory):

        class FakePort(object):

            def stopListening(oself):
                self._socket_paths.pop(socket_path)

        self._socket_paths[socket_path] = factory
        return FakePort()

    def connect_unix(self, path, factory):
        server = self._socket_paths.get(path)
        from landscape.lib.tests.test_amp import FakeConnector
        if server:
            connector = FakeConnector(factory, server)
            connector.connect()
        else:
            connector = object()  # Fake connector
            failure = Failure(ConnectError("No such file or directory"))
            factory.clientConnectionFailed(connector, failure)
        return connector

    def run(self):
        """Continuously advance this reactor until reactor.stop() is called."""
        self.fire("run")
        self._running = True
        while self._running:
            self.advance(self._calls[0][0])
        self.fire("stop")

    def stop(self):
        self._running = False

    def advance(self, seconds):
        """Advance this reactor C{seconds} into the future.

        This method is not part of the L{LandscapeReactor} API and is specific
        to L{FakeReactor}. It's meant to be used only in unit tests for
        advancing time and triggering the relevant scheduled calls (see
        also C{call_later} and C{call_every}).
        """
        while (self._calls and self._calls[0][0]
               <= self._current_time + seconds):
            call = self._calls.pop(0)
            # If we find a call within the time we're advancing,
            # before calling it, let's advance the time *just* to
            # when that call is expecting to be run, so that if it
            # schedules any calls itself they will be relative to
            # the correct time.
            seconds -= call[0] - self._current_time
            self._current_time = call[0]
            try:
                call[1](*call[2], **call[3])
            except Exception, e:
                logging.exception(e)
        self._current_time += seconds

    def _in_thread(self, callback, errback, f, args, kwargs):
        try:
            result = f(*args, **kwargs)
        except Exception, e:
            exc_info = sys.exc_info()
            if errback is None:
                self.call_in_main(logging.error, e, exc_info=exc_info)
            else:
                self.call_in_main(errback, *exc_info)
        else:
            if callback:
                self.call_in_main(callback, result)

    def _run_threaded_callbacks(self):
        while self._threaded_callbacks:
            try:
                self._threaded_callbacks.pop(0)()
            except Exception, e:
                logging.exception(e)

    def _hook_threaded_callbacks(self):
        id = self.call_every(0.5, self._run_threaded_callbacks)
        self._run_threaded_callbacks_id = id

    def _unhook_threaded_callbacks(self):
        self.cancel_call(self._run_threaded_callbacks_id)
