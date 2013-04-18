"""Expose the methods of a remote object over AMP.

This module implements an AMP-based protocol for performing remote procedure
calls in a convenient and easy way. It's conceptually similar to DBus in that
it supports exposing a Python object to a remote process, with communication
happening over plain Unix domain sockets.

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

        factory.deferred.addCallback(do_other_stuff)

    factory.getRemoteObject().addCallback(got_remote)

Note that when invoking a method via the remote proxy, the parameters
are required to be serializable with bpickle, so that they can be sent
over the wire.

See also::

    http://twistedmatrix.com/documents/current/core/howto/amp.html

for more details about the Twisted AMP protocol.
"""

from twisted.internet.defer import Deferred, maybeDeferred
from twisted.internet.protocol import ReconnectingClientFactory
from twisted.python.failure import Failure

from twisted.protocols.amp import (
    Argument, String, Integer, Command, AMP, MAX_VALUE_LENGTH, CommandLocator)

from landscape.lib.bpickle import loads, dumps, dumps_table


class MethodCallArgument(Argument):
    """A bpickle-compatible argument."""

    def toString(self, inObject):
        """Serialize an argument."""
        return dumps(inObject)

    def fromString(self, inString):
        """Unserialize an argument."""
        return loads(inString)

    @classmethod
    def check(cls, inObject):
        """Check if an argument is serializable."""
        return type(inObject) in dumps_table


class MethodCallError(Exception):
    """Raised when a L{MethodCall} command fails."""


class MethodCall(Command):
    """Call a method on the object exposed by a L{MethodCallProtocol}."""

    arguments = [("sequence", Integer()),
                 ("method", String()),
                 ("arguments", String())]

    response = [("result", MethodCallArgument())]

    errors = {MethodCallError: "METHOD_CALL_ERROR"}


class MethodCallChunk(Command):
    """Send a chunk of L{MethodCall} containing a portion of the arguments.

    When a the arguments of a L{MethodCall} are bigger than 64k, they get split
    in several L{MethodCallChunk}s that are buffered on the receiver side.
    """

    arguments = [("sequence", Integer()),
                 ("chunk", String())]

    response = [("result", Integer())]

    errors = {MethodCallError: "METHOD_CALL_ERROR"}


class MethodCallReceiver(CommandLocator):
    """Expose methods of a local object over AMP.

    @param object: The Python object to be exposed.
    @param methods: The list of the object's methods that can be called
         remotely.
    """

    def __init__(self, object, methods):
        CommandLocator.__init__(self)
        self._object = object
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
            arguments = "".join(chunks)

        args, kwargs = loads(arguments)

        if not method in self._methods:
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
        self.protocol = protocol
        self.clock = clock
        self._sequence = 0

    def _create_sequence(self):
        """Return a unique sequence number for a L{MethodCall}."""
        self._sequence += 1
        return self._sequence

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

        call = self.clock.callLater(self.timeout, handle_timeout)

        result = self.protocol.callRemote(command, **kwargs)
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
        arguments = dumps((args, kwargs))
        sequence = self._create_sequence()

        # Split the given arguments in one or more chunks
        chunks = [arguments[i:i + self._chunk_size]
                  for i in xrange(0, len(arguments), self._chunk_size)]

        result = Deferred()
        if len(chunks) > 1:
            # If we have N chunks, send the first N-1 as MethodCallChunk's
            for chunk in chunks[:-1]:

                def create_send_chunk(sequence, chunk):
                    send_chunk = lambda x: self.protocol.callRemote(
                        MethodCallChunk, sequence=sequence, chunk=chunk)
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
    """XXX Placeholder"""


class MethodCallClientProtocol(AMP):
    """XXX Placeholder"""


class MethodCallProtocol(MethodCallServerProtocol, MethodCallClientProtocol):
    """Can be used both for sending and receiving L{MethodCall}s."""

    def __init__(self):
        MethodCallServerProtocol.__init__(self)
        MethodCallClientProtocol.__init__(self)


class MethodCallFactory(ReconnectingClientFactory):
    """
    Factory for L{MethodCallProtocol}s exposing an object or connecting to
    L{MethodCall} servers.

    When used to connect, if the connection fails or is lost the factory
    will keep retrying to establish it.

    @cvar protocol: The factory used to build protocol instances.
    @cvar factor: The time factor by which the delay between two subsequent
        connection retries will increase.
    @cvar maxDelay: Maximum number of seconds between connection attempts.
    """

    protocol = MethodCallProtocol
    factor = 1.6180339887498948
    maxDelay = 30

    def __init__(self, object=None, reactor=None):
        """
        @param object: The object exposed by the L{MethodCallProtocol}s
            instances created by this factory.
        @param reactor: The reactor used by the created protocols
            to schedule notifications and timeouts.
        """
        self.object = object
        self.reactor = reactor
        self.clock = self.reactor
        self.delay = self.initialDelay
        self._notifiers = []

    def add_notifier(self, callback, errback=None):
        """Call the given function on connection, reconnection or give up.

        @param notifier: A function that will be called when the factory builds
            a new connected protocol or gives up connecting.  It will be passed
            the new protocol instance as argument, or the connectionf failure.
        """
        self._notifiers.append((callback, errback))

    def remove_notifier(self, callback, errback=None):
        """Remove a notifier."""
        self._notifiers.remove((callback, errback))

    def notify_success(self, *args, **kwargs):
        """Notify all registered notifier callbacks."""
        for callback, _ in self._notifiers:
            self.reactor.callLater(0, callback, *args, **kwargs)

    def notify_failure(self, failure):
        """Notify all registered notifier errbacks."""
        for _, errback in self._notifiers:
            if errback is not None:
                self.reactor.callLater(0, errback, failure)

    def clientConnectionFailed(self, connector, reason):
        ReconnectingClientFactory.clientConnectionFailed(self, connector,
                                                         reason)
        if self.maxRetries is not None and (self.retries > self.maxRetries):
            self.notify_failure(reason)  # Give up

    def buildProtocol(self, addr):
        self.resetDelay()
        if self.object is not None:
            # XXX temporary hack to emulate the behavior of this code before
            # MethodCallReceiver was introduced
            locator = MethodCallReceiver(self.object, self.protocol.methods)
            protocol = AMP(locator=locator)
            protocol.factory = self
        else:
            protocol = ReconnectingClientFactory.buildProtocol(self, addr)
        self.notify_success(protocol)
        return protocol


class RemoteObject(object):
    """An object able to transparently call methods on a remote object.

    Any method call on a L{RemoteObject} instance will return a L{Deferred}
    resulting in the return value of the same method call performed on
    the remote object exposed by the peer.
    """

    def __init__(self, sender, retry_on_reconnect=False, timeout=None,
                 factory=None):
        """
        @param protocol: A reference to a connected L{AMP} protocol instance,
            which will be used to send L{MethodCall} commands.
        @param retry_on_reconnect: If C{True}, this L{RemoteObject} will retry
            to perform again requests that failed due to a lost connection, as
            soon as a new connection is available.
        @param timeout: A timeout for failed requests, if the L{RemoteObject}
            can't perform them again successfully within this number of
            seconds, they will errback with a L{MethodCallError}.
        """
        self._sender = sender
        self._factory = factory
        self._retry_on_reconnect = retry_on_reconnect
        self._timeout = timeout
        self._pending_requests = {}
        if self._factory:
            # XXX temporary hack to emulate the behavior of this code before
            # MethodCallReceiver was introduced
            self._reactor = factory.reactor
            self._factory.add_notifier(self._handle_reconnect)

    def __getattr__(self, method):
        """Return a function sending a L{MethodCall} for the given C{method}.

        When the created function is called, it sends the an appropriate
        L{MethodCall} to the remote peer passing it the arguments and
        keyword arguments it was called with, and returning a L{Deferred}
        resulting in the L{MethodCall}'s response value.
        """

        def send_method_call(*args, **kwargs):
            result = self._sender.send_method_call(method=method,
                                                   args=args,
                                                   kwargs=kwargs)
            deferred = Deferred()
            result.addCallback(self._handle_result, deferred)
            result.addErrback(self._handle_failure, method, args, kwargs,
                              deferred)
            return deferred

        return send_method_call

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
        dont_retry = self._retry_on_reconnect is False

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

        if self._timeout and call is None:
            # This is the first failure for this request, let's schedule a
            # timeout call.
            timeout = Failure(MethodCallError("timeout"))
            call = self._reactor.callLater(self._timeout,
                                           self._handle_failure,
                                           timeout, method, args,
                                           kwargs, deferred=deferred)

        self._pending_requests[deferred] = (method, args, kwargs, call)

    def _handle_reconnect(self, protocol):
        """Handles a reconnection.

        @param protocol: The newly connected protocol instance.
        """
        self._sender.protocol = protocol
        if self._retry_on_reconnect:
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
            result = self._sender.send_method_call(method, args, kwargs)
            result.addCallback(self._handle_result,
                               deferred=deferred, call=call)
            result.addErrback(self._handle_failure, method, args, kwargs,
                              deferred=deferred, call=call)


class RemoteObjectConnector(object):
    """Connect to remote objects exposed by a L{MethodCallProtocol}."""

    factory = MethodCallFactory
    remote = RemoteObject

    def __init__(self, reactor, socket_path, *args, **kwargs):
        """
        @param reactor: A reactor able to connect to Unix sockets.
        @param socket: The path to the socket we want to connect to.
        @param args: Arguments to be passed to the created L{RemoteObject}.
        @param kwargs: Keyword arguments for the created L{RemoteObject}.
        """
        self._socket_path = socket_path
        self._reactor = reactor
        self._args = args
        self._kwargs = kwargs
        self._remote = None
        self._factory = None

    def connect(self, max_retries=None, factor=None):
        """Connect to a remote object exposed by a L{MethodCallProtocol}.

        This method will connect to the socket provided in the constructor
        and return a L{Deferred} resulting in a connected L{RemoteObject}.

        @param max_retries: If not C{None} give up try to connect after this
            amount of times, otherwise keep trying to connect forever.
        @param factor: Optionally a float indicating by which factor the
            delay between subsequent retries should increase. Smaller values
            result in a faster reconnection attempts pace.
        """
        self._connected = Deferred()
        self._factory = self.factory(reactor=self._reactor)
        self._factory.maxRetries = max_retries
        if factor:
            self._factory.factor = factor
        self._factory.add_notifier(self._success, self._failure)
        self._reactor.connectUNIX(self._socket_path, self._factory)
        return self._connected

    def _success(self, result):
        """Called when the first connection has been established"""

        # We did our job, remove our own notifier and let the remote object
        # handle reconnections.
        self._factory.remove_notifier(self._success, self._failure)
        sender = MethodCallSender(result, self._reactor)
        # XXX temporary hack to emulate the behavior of this code before
        # MethodCallReceiver was introduced
        self._kwargs["factory"] = self._factory
        self._remote = self.remote(sender, *self._args, **self._kwargs)
        self._connected.callback(self._remote)

    def _failure(self, failure):
        """Called when the first connection has failed"""
        self._connected.errback(failure)

    def disconnect(self):
        """Disconnect the L{RemoteObject} that we have created."""
        if self._factory:
            self._factory.stopTrying()
        if self._remote:
            if self._remote._sender.protocol.transport:
                self._remote._sender.protocol.transport.loseConnection()
            self._remote = None
