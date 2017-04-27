"""Expose the methods of a remote object over AMP.

This module implements an AMP-based protocol for performing remote procedure
calls in a convenient and easy way. It's conceptually similar to DBus in that
it supports exposing a Python object to a remote process, with communication
happening over any Twisted-supported transport, e.g. Unix domain sockets.

For example let's say we have a Python process "A" that creates an instance of
this class::

    class Greeter(object):

        def hello(self, name):
            return "hi %s!" % name

    greeter = Greeter()

Process A can "publish" the greeter object by defining which methods are
exposed remotely and opening a Unix socket for incoming connections::

    factory = MethodCallServerFactory(greeter, ["hello"])
    reactor.listenUNIX("/some/socket/path", factory)

Then a second Python process "B" can connect to that socket and build a
"remote" greeter object, i.e. a proxy that forwards method calls to the
real greeter object living in process A::

    factory = MethodCallClientFactory()
    reactor.connectUNIX("/some/socket/path", factory)

    def got_remote(remote_greeter):
        deferred = remote_greeter.hello("Ted")
        deferred.addCallback(lambda result: ... # result == "hi Ted!")

    factory.getRemoteObject().addCallback(got_remote)

Note that when invoking a method via the remote proxy, the parameters
are required to be serializable with bpickle, so they can be sent over
the wire.

See also::

    http://twistedmatrix.com/documents/current/core/howto/amp.html

for more details about the Twisted AMP protocol.
"""
from uuid import uuid4

from twisted.internet.defer import Deferred, maybeDeferred, succeed
from twisted.internet.protocol import ServerFactory, ReconnectingClientFactory
from twisted.python.failure import Failure
from twisted.python.compat import xrange

from twisted.protocols.amp import (
    Argument, String, Integer, Command, AMP, MAX_VALUE_LENGTH, CommandLocator)

from landscape.lib import bpickle


class MethodCallArgument(Argument):
    """A bpickle-compatible argument."""

    def toString(self, inObject):
        """Serialize an argument."""
        return bpickle.dumps(inObject)

    def fromString(self, inString):
        """Unserialize an argument."""
        return bpickle.loads(inString)

    @classmethod
    def check(cls, inObject):
        """Check if an argument is serializable."""
        return type(inObject) in bpickle.dumps_table


class MethodCallError(Exception):
    """Raised when a L{MethodCall} command fails."""


class MethodCall(Command):
    """Call a method on the object exposed by a L{MethodCallServerFactory}.

    The command arguments have the following semantics:

    - C{sequence}: An integer uniquely indentifying a the L{MethodCall}
      being issued. The name 'sequence' is a bit misleading because it's
      really a uuid, since its values in practice are not in sequential
      order, they are just random values. The name is kept just for backward
      compatibility.

    - C{method}: The name of the method to invoke on the remote object.

    - C{arguments}: A BPickled binary tuple of the form C{(args, kwargs)},
      where C{args} are the positional arguments to be passed to the method
      and C{kwargs} the keyword ones.
    """

    arguments = [(b"sequence", Integer()),
                 (b"method", String()),
                 (b"arguments", String())]

    response = [(b"result", MethodCallArgument())]

    errors = {MethodCallError: b"METHOD_CALL_ERROR"}


class MethodCallChunk(Command):
    """Send a chunk of L{MethodCall} containing a portion of the arguments.

    When a the arguments of a L{MethodCall} are bigger than 64k, they get split
    in several L{MethodCallChunk}s that are buffered on the receiver side.

    The command arguments have the following semantics:

    - C{sequence}: The unique integer associated with the L{MethodCall} that
      this L{MethodCallChunk} is part of.

    - C{chunk}: A portion of the big BPickle C{arguments} string which is
      being split and buffered.
    """

    arguments = [(b"sequence", Integer()),
                 (b"chunk", String())]

    response = [(b"result", Integer())]

    errors = {MethodCallError: b"METHOD_CALL_ERROR"}


class MethodCallReceiver(CommandLocator):
    """Expose methods of a local object over AMP.

    @param obj: The Python object to be exposed.
    @param methods: The list of the object's methods that can be called
         remotely.
    """

    def __init__(self, obj, methods):
        CommandLocator.__init__(self)
        self._object = obj
        self._methods = methods
        self._pending_chunks = {}

    @MethodCall.responder
    def receive_method_call(self, sequence, method, arguments):
        """Call an object's method with the given arguments.

        If a connected client sends a L{MethodCall} for method C{foo_bar}, then
        the actual method C{foo_bar} of the object associated with the protocol
        will be called with the given C{args} and C{kwargs} and its return
        value delivered back to the client as response to the command.

        @param sequence: The integer that uniquely identifies the L{MethodCall}
            being received.
        @param method: The name of the object's method to call.
        @param arguments: A bpickle'd binary tuple of (args, kwargs) to be
           passed to the method. In case this L{MethodCall} has been preceded
           by one or more L{MethodCallChunk}s, C{arguments} is the last chunk
           of data.
        """
        chunks = self._pending_chunks.pop(sequence, None)
        if chunks is not None:
            # We got some L{MethodCallChunk}s before, this is the last.
            chunks.append(arguments)
            arguments = b"".join(chunks)

        # Pass the the arguments as-is without reinterpreting strings.
        args, kwargs = bpickle.loads(arguments, as_is=True)

        # We encoded the method name in `send_method_call` and have to decode
        # it here again.
        method = method.decode("utf-8")
        if method not in self._methods:
            raise MethodCallError("Forbidden method '%s'" % method)

        method_func = getattr(self._object, method)

        def handle_result(result):
            return {"result": self._check_result(result)}

        def handle_failure(failure):
            raise MethodCallError(failure.value)

        deferred = maybeDeferred(method_func, *args, **kwargs)
        deferred.addCallback(handle_result)
        deferred.addErrback(handle_failure)
        return deferred

    @MethodCallChunk.responder
    def receive_method_call_chunk(self, sequence, chunk):
        """Receive a part of a multi-chunk L{MethodCall}.

        Add the received C{chunk} to the buffer of the L{MethodCall} identified
        by C{sequence}.
        """
        self._pending_chunks.setdefault(sequence, []).append(chunk)
        return {"result": sequence}

    def _check_result(self, result):
        """Check that the C{result} we're about to return is serializable.

        @return: The C{result} itself if valid.
        @raises: L{MethodCallError} if C{result} is not serializable.
        """
        if not MethodCallArgument.check(result):
            raise MethodCallError("Non-serializable result")
        return result


class MethodCallSender(object):
    """Call methods on a remote object over L{AMP} and return the result.

    @param protocol: A connected C{AMP} protocol.
    @param clock: An object implementing the C{IReactorTime} interface.

    @ivar timeout: A timeout for remote method class, see L{send_method_call}.
    """
    timeout = 60

    _chunk_size = MAX_VALUE_LENGTH

    def __init__(self, protocol, clock):
        self._protocol = protocol
        self._clock = clock

    def _call_remote_with_timeout(self, command, **kwargs):
        """Send an L{AMP} command that will errback in case of a timeout.

        @return: A deferred resulting in the command's response (or failure) if
            the peer responds within C{self.timeout} seconds, or that errbacks
            with a L{MethodCallError} otherwise.
        """
        deferred = Deferred()

        def handle_response(response):
            if not call.active():
                # Late response for a request that has timeout,
                # just ignore it.
                return
            call.cancel()
            deferred.callback(response)

        def handle_timeout():
            # The peer didn't respond on time, raise an error.
            deferred.errback(MethodCallError("timeout"))

        call = self._clock.callLater(self.timeout, handle_timeout)

        result = self._protocol.callRemote(command, **kwargs)
        result.addBoth(handle_response)
        return deferred

    def send_method_call(self, method, args=[], kwargs={}):
        """Send a L{MethodCall} command with the given arguments.

        If a response from the server is not received within C{self.timeout}
        seconds, the returned deferred will errback with a L{MethodCallError}.

        @param method: The name of the remote method to invoke.
        @param args: The positional arguments to pass to the remote method.
        @param kwargs: The keyword arguments to pass to the remote method.

        @return: A C{Deferred} firing with the return value of the method
            invoked on the remote object. If the remote method itself returns
            a deferred, we fire with the callback value of such deferred.
        """
        arguments = bpickle.dumps((args, kwargs))
        sequence = uuid4().int
        # As we send the method name to remote, we need bytes.
        method = method.encode("utf-8")

        # Split the given arguments in one or more chunks
        chunks = [arguments[i:i + self._chunk_size]
                  for i in xrange(0, len(arguments), self._chunk_size)]

        result = Deferred()
        if len(chunks) > 1:
            # If we have N chunks, send the first N-1 as MethodCallChunk's
            for chunk in chunks[:-1]:

                def create_send_chunk(sequence, chunk):
                    send_chunk = (lambda x: self._protocol.callRemote(
                        MethodCallChunk, sequence=sequence, chunk=chunk))
                    return send_chunk

                result.addCallback(create_send_chunk(sequence, chunk))

        def send_last_chunk(ignored):
            chunk = chunks[-1]
            return self._call_remote_with_timeout(
                MethodCall, sequence=sequence, method=method, arguments=chunk)

        result.addCallback(send_last_chunk)
        result.addCallback(lambda response: response["result"])
        result.callback(None)
        return result


class MethodCallServerProtocol(AMP):
    """Receive L{MethodCall} commands over the wire and send back results."""

    def __init__(self, obj, methods):
        AMP.__init__(self, locator=MethodCallReceiver(obj, methods))


class MethodCallClientProtocol(AMP):
    """Send L{MethodCall} commands over the wire using the AMP protocol."""

    factory = None

    def connectionMade(self):
        """Notify our factory that we're ready to go."""
        if self.factory is not None:  # Factory can be None in unit-tests
            self.factory.clientConnectionMade(self)


class RemoteObject(object):
    """An object able to transparently call methods on a remote object.

    Any method call on a L{RemoteObject} instance will return a L{Deferred}
    resulting in the return value of the same method call performed on
    the remote object exposed by the peer.
    """

    def __init__(self, factory):
        """
        @param factory: The L{MethodCallClientFactory} used for connecting to
            the other peer. Look there if you need to tweak the behavior of
            this L{RemoteObject}.
        """
        self._sender = None
        self._pending_requests = {}
        self._factory = factory
        self._factory.notifyOnConnect(self._handle_connect)

    def __getattr__(self, method):
        """Return a function sending a L{MethodCall} for the given C{method}.

        When the created function is called, it sends the an appropriate
        L{MethodCall} to the remote peer passing it the arguments and
        keyword arguments it was called with, and returning a L{Deferred}
        resulting in the L{MethodCall}'s response value.
        """
        def send_method_call(*args, **kwargs):
            deferred = Deferred()
            self._send_method_call(method, args, kwargs, deferred)
            return deferred

        return send_method_call

    def _send_method_call(self, method, args, kwargs, deferred, call=None):
        """Send a L{MethodCall} command, adding callbacks to handle retries."""
        result = self._sender.send_method_call(method=method,
                                               args=args,
                                               kwargs=kwargs)
        result.addCallback(self._handle_result, deferred, call=call)
        result.addErrback(self._handle_failure, method, args, kwargs,
                          deferred, call=call)

        if self._factory.fake_connection is not None:
            # Transparently flush the connection after a send_method_call
            # invocation letting tests simulate a synchronous transport.
            # This is needed because the Twisted's AMP implementation
            # assume that the transport is asynchronous.
            self._factory.fake_connection.flush()

    def _handle_result(self, result, deferred, call=None):
        """Handles a successful C{send_method_call} result.

        @param response: The L{MethodCall} response.
        @param deferred: The deferred that was returned to the caller.
        @param call: If not C{None}, the scheduled timeout call associated with
            the given deferred.
        """
        if call is not None:
            call.cancel()  # This is a successful retry, cancel the timeout.
        deferred.callback(result)

    def _handle_failure(self, failure, method, args, kwargs, deferred,
                        call=None):
        """Called when a L{MethodCall} command fails.

        If a failure is due to a connection error and if C{retry_on_reconnect}
        is C{True}, we will try to perform the requested L{MethodCall} again
        as soon as a new connection becomes available, giving up after the
        specified C{timeout}, if any.

        @param failure: The L{Failure} raised by the requested L{MethodCall}.
        @param name: The method name associated with the failed L{MethodCall}.
        @param args: The positional arguments of the failed L{MethodCall}.
        @param kwargs: The keyword arguments of the failed L{MethodCall}.
        @param deferred: The deferred that was returned to the caller.
        @param call: If not C{None}, the scheduled timeout call associated with
            the given deferred.
        """
        is_method_call_error = failure.type is MethodCallError
        dont_retry = self._factory.retryOnReconnect is False

        if is_method_call_error or dont_retry:
            # This means either that the connection is working, and a
            # MethodCall protocol error occured, or that we gave up
            # trying and raised a timeout. In any case just propagate
            # the error.
            if deferred in self._pending_requests:
                self._pending_requests.pop(deferred)
            if call:
                call.cancel()
            deferred.errback(failure)
            return

        if self._factory.retryTimeout and call is None:
            # This is the first failure for this request, let's schedule a
            # timeout call.
            timeout = Failure(MethodCallError("timeout"))
            call = self._factory.clock.callLater(self._factory.retryTimeout,
                                                 self._handle_failure,
                                                 timeout, method, args,
                                                 kwargs, deferred=deferred)

        self._pending_requests[deferred] = (method, args, kwargs, call)

    def _handle_connect(self, protocol):
        """Handles a reconnection.

        @param protocol: The newly connected protocol instance.
        """
        self._sender = MethodCallSender(protocol, self._factory.clock)
        if self._factory.retryOnReconnect:
            self._retry()

    def _retry(self):
        """Try to perform again requests that failed."""

        # We need to copy the requests list before iterating over it, because
        # if we are actually still disconnected, callRemote will return a
        # failed deferred and the _handle_failure errback will be executed
        # synchronously during the loop, modifing the requests list itself.
        requests = self._pending_requests.copy()
        self._pending_requests.clear()

        while requests:
            deferred, (method, args, kwargs, call) = requests.popitem()
            self._send_method_call(method, args, kwargs, deferred, call=call)


class MethodCallServerFactory(ServerFactory):
    """Expose a Python object using L{MethodCall} commands over C{AMP}."""

    protocol = MethodCallServerProtocol

    def __init__(self, obj, methods):
        """
        @param object: The object exposed by the L{MethodCallProtocol}s
            instances created by this factory.
        @param methods: A list of the names of the methods that remote peers
            are allowed to call on the C{object} that we publish.
        """
        self.object = obj
        self.methods = methods

    def buildProtocol(self, addr):
        protocol = self.protocol(self.object, self.methods)
        protocol.factory = self
        return protocol


class MethodCallClientFactory(ReconnectingClientFactory):
    """
    Factory for L{MethodCallClientProtocol}s exposing an object or connecting
    to L{MethodCall} servers.

    When used to connect, if the connection fails or is lost the factory
    will keep retrying to establish it.

    @ivar factor: The time factor by which the delay between two subsequent
        connection retries will increase.
    @ivar maxDelay: Maximum number of seconds between connection attempts.
    @ivar protocol: The factory used to build protocol instances.
    @ivar remote: The factory used to build remote object instances.
    @ivar retryOnReconnect: If C{True}, the remote object returned by the
        C{getRemoteObject} method will retry requests that failed, as a
        result of a lost connection, as soon as a new connection is available.
    @param retryTimeout: A timeout for retrying requests, if the remote object
        can't perform them again successfully within this number of seconds,
        they will errback with a L{MethodCallError}.
    """

    factor = 1.6180339887498948
    maxDelay = 30

    protocol = MethodCallClientProtocol
    remote = RemoteObject

    retryOnReconnect = False
    retryTimeout = None

    # XXX support exposing fake asynchronous connections created by tests, so
    # they can be flushed transparently and emulate a synchronous behavior. See
    # also http://twistedmatrix.com/trac/ticket/6502, once that's fixed this
    # hack can be removed.
    fake_connection = None

    def __init__(self, clock):
        """
        @param object: The object exposed by the L{MethodCallProtocol}s
            instances created by this factory.
        @param reactor: The reactor used by the created protocols
            to schedule notifications and timeouts.
        """
        self.clock = clock
        self.delay = self.initialDelay
        self._connects = []
        self._requests = []
        self._remote = None

    def getRemoteObject(self):
        """Get a L{RemoteObject} as soon as the connection is ready.

        @return: A C{Deferred} firing with a connected L{RemoteObject}.
        """
        if self._remote is not None:
            return succeed(self._remote)
        deferred = Deferred()
        self._requests.append(deferred)
        return deferred

    def notifyOnConnect(self, callback):
        """Invoke the given C{callback} when a connection is re-established."""
        self._connects.append(callback)

    def dontNotifyOnConnect(self, callback):
        """Remove the given C{callback} from listeners."""
        self._connects.remove(callback)

    def clientConnectionMade(self, protocol):
        """Called when a newly built protocol gets connected."""
        if self._remote is None:
            # This is the first time we successfully connect
            self._remote = self.remote(self)

        for callback in self._connects:
            callback(protocol)

        # In all cases fire pending requests
        self._fire_requests(self._remote)

    def clientConnectionFailed(self, connector, reason):
        """Try to connect again or errback pending request."""
        ReconnectingClientFactory.clientConnectionFailed(self, connector,
                                                         reason)
        if self._callID is None:
            # The factory won't retry to connect, so notify that we failed
            self._fire_requests(reason)

    def buildProtocol(self, addr):
        self.resetDelay()
        protocol = ReconnectingClientFactory.buildProtocol(self, addr)
        return protocol

    def _fire_requests(self, result):
        """
        Fire all pending L{getRemoteObject} deferreds with the given C{result}.
        """
        requests = self._requests[:]
        self._requests = []

        for deferred in requests:
            deferred.callback(result)
