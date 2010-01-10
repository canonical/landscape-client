"""Expose the methods of a remote object over AMP. """

from uuid import uuid4
from twisted.internet.defer import Deferred
from twisted.internet.protocol import (
    ServerFactory, ReconnectingClientFactory)
from twisted.protocols.amp import Argument, String, Command, AMP
from twisted.python.failure import Failure

from landscape.lib.bpickle import loads, dumps, dumps_table


class MethodCallArgument(Argument):
    """A bpickle-compatbile argument."""

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

    arguments = [("method", String()),
                 ("args", MethodCallArgument()),
                 ("kwargs", MethodCallArgument())]

    response = [("result", MethodCallArgument()),
                ("deferred", String(optional=True))]

    errors = {MethodCallError: "METHOD_CALL_ERROR"}


class _DeferredResponse(Command):
    """Fire a L{Deferred} associated with an outstanding method call result."""

    arguments = [("uuid", String()),
                 ("result", MethodCallArgument(optional=True)),
                 ("failure", String(optional=True))]
    requiresAnswer = False


class MethodCallServerProtocol(AMP):
    """Expose methods of a local object over AMP.

    The object to be exposed is expected to be the C{object} attribute of our
    protocol factory.

    @cvar methods: The list of exposed object's methods that can be called with
        the protocol. It must be defined by sub-classes.
    """

    methods = []

    @MethodCall.responder
    def _call_object_method(self, method, args, kwargs):
        """Call an object's method with the given arguments.

        If a connected client sends a L{MethodCall} for method C{foo_bar}, then
        the actual method C{foo_bar} of the object associated with the protocol
        will be called with the given C{args} and C{kwargs} and its return
        value delivered back to the client as response to the command.

        @param method: The name of the object's method to call.
        @param args: The arguments to pass to the method.
        @param kwargs: The keywords arguments to pass to the method.
        """
        if not method in self.methods:
            raise MethodCallError("Forbidden method '%s'" % method)

        method_func = getattr(self.factory.object, method)
        method_args = args[:]
        method_kwargs = kwargs.copy()

        result = method_func(*method_args, **method_kwargs)

        # If the method returns a Deferred, register callbacks that will
        # eventually notify the remote peer of its success or failure.
        if isinstance(result, Deferred):

            # If the Deferred was already fired, we can return its result
            if result.called:
                if isinstance(result.result, Failure):
                    failure = str(result.result.value)
                    result.addErrback(lambda x: None)
                    raise MethodCallError(failure)
                return {"result": result.result}

            uuid = str(uuid4())
            result.addBoth(self._send_deferred_response, uuid)
            return {"result": None, "deferred": uuid}

        if not MethodCallArgument.check(result):
            raise MethodCallError("Non-serializable result")
        return {"result": result}

    def _send_deferred_response(self, result, uuid):
        """Send a successful L{FireDeferred} for the given C{uuid}."""
        kwargs = {"uuid": uuid}
        if isinstance(result, Failure):
            kwargs["failure"] = str(result.value)
        else:
            kwargs["result"] = result
        self.callRemote(_DeferredResponse, **kwargs)


class MethodCallClientProtocol(AMP):
    """Calls methods of a remote object over L{AMP}.

    @note: If the remote method returns a deferreds, the associated local
        deferred returned by L{callRemote} will result in the same callback
        value of the remote deferred.
    @cvar timeout: A timeout for remote methods returning L{Deferred}s, if a
        response for the deferred is not received within this amount of
        seconds, the remote method call will errback with a L{MethodCallError}.
    """
    timeout = 60

    def __init__(self):
        AMP.__init__(self)
        self._pending_responses = {}

    @_DeferredResponse.responder
    def _receive_deferred_response(self, uuid, result, failure):
        """Receive the deferred L{MethodCall} response.

        @param uuid: The id of the L{MethodCall} we're getting the result of.
        @param result: The result of the associated deferred if successful.
        @param failure: The failure message of the deferred if it failed.
        """
        self._fire_deferred(uuid, result, failure)
        return {}

    def _fire_deferred(self, uuid, result, failure):
        """Receive the deferred L{MethodCall} result.

        @param uuid: The id of the L{MethodCall} we're getting the result of.
        @param result: The result of the associated deferred if successful.
        @param failure: The failure message of the deferred if it failed.
        """
        deferred, call = self._pending_responses.pop(uuid)
        if not call.called:
            call.cancel()
        if failure is None:
            deferred.callback({"result": result})
        else:
            deferred.errback(MethodCallError(failure))

    def _handle_response(self, response):
        """Handle a L{MethodCall} response, possibly queing it as pending."""

        if response["deferred"]:
            uuid = response["deferred"]
            deferred = Deferred()
            call = self.factory.reactor.callLater(self.timeout,
                                                  self._fire_deferred,
                                                  uuid, None, "timeout")
            self._pending_responses[uuid] = (deferred, call)
            return deferred

        return response

    def callRemote(self, *args, **kwargs):
        result = AMP.callRemote(self, *args, **kwargs)
        # The result can be C{None} only if the requested command is a
        # _DeferredResponse, which has requiresAnswer set to False
        if result is not None:
            return result.addCallback(self._handle_response)


class MethodCallServerFactory(ServerFactory):
    """Factory for building L{MethodCallProtocol}s exposing an object."""

    protocol = MethodCallServerProtocol

    def __init__(self, object):
        """
        @param object: The object exposed by the L{MethodCallProtocol}s
            instances created by this factory.
        """
        self.object = object


class MethodCallClientFactory(ReconnectingClientFactory):
    """Factory for building L{AMP} connections to L{MethodCall} servers.

    If the connection fails or is lost the factory will keep retrying to
    establish it.

    @cvar protocol: The factory used to build protocol instances.
    @cvar factor: The factor by which the delay between two subsequent
        connection retries will decrease.
    @ivar notifier: If not C{None}, a callable that will be called when the
        factory builds a new connected protocol.  It will be passed the new
        protocol instance as argument.
    """

    protocol = MethodCallClientProtocol
    factor = 1.6180339887498948

    def __init__(self, reactor):
        """
        @param reactor: The reactor that will used by the created protocols
            to schedule timeouts for methods returning deferreds.
        """
        self.reactor = reactor
        self.notifier = None

    def buildProtocol(self, addr):
        self.resetDelay()
        protocol = self.protocol()
        protocol.factory = self
        if self.notifier:
            self.reactor.callLater(0, self.notifier, protocol)
        return protocol


class RemoteObject(object):
    """An object able to transparently call methods on a remote object.

    Any method call on a L{RemoteObject} instance will return a L{Deferred}
    resulting in the return value of the same method call performed on
    the remote object exposed by the peer.
    """

    def __init__(self, protocol, retry_on_reconnect=False, timeout=None):
        """
        @param protocol: A reference to a connected L{AMP} protocol instance,
            which will be used to send L{MethodCall} commands.
        @param retry_on_reconnect: If C{True}, this L{RemoteObject} will retry
            to perfom requests that failed due to a lost connection, as soon
            as a new connection is available.
        @param timeout: A timeout for failed requests, if the L{RemoteObject}
            can't perform them again successfully within this amout of seconds,
            the will errback with a L{MethodCallError}.
        """
        self._protocol = protocol
        self._reactor = self._protocol.factory.reactor
        self._retry_on_reconnect = retry_on_reconnect
        self._timeout = timeout
        self._pending_requests = {}
        self._retry_call = None

    def __getattr__(self, method):
        """Return a function sending a L{MethodCall} for the given C{method}.

        When the created function is called, it sends the an appropriate
        L{MethodCall} to the remote peer passing it the arguments and
        keyword arguments it was called with, and returing a L{Deferred}
        resulting in the L{MethodCall}'s response value.
        """

        def send_method_call(*args, **kwargs):
            result = self._call_remote(method, args, kwargs)
            result.addCallback(self._handle_response)
            result.addErrback(self._handle_failure, method, args, kwargs)
            return result

        return send_method_call

    def _call_remote(self, method, args, kwargs):
        """Perform a L{MethodCall} with the given arguments."""
        return self._protocol.callRemote(MethodCall,
                                         method=method,
                                         args=args[:],
                                         kwargs=kwargs.copy())

    def _handle_reconnect(self, protocol):
        """Handles a reconnection.

        @param protocol: The newly connected protocol instance.
        """
        self._protocol = protocol
        if self._retry_on_reconnect:
            self._retry()

    def _handle_response(self, response, deferred=None, call=None):
        """Handles a successful L{MethodCall} response.

        @param response: The L{MethodCall} response.
        @param deferred: If not C{None}, the deferred that was returned to
            the caller when the first attempt failed.
        @param call: If not C{None}, the scheduled timeout call associated with
            the given deferred.
        """
        result = response["result"]
        if deferred:
            if call:
                call.cancel()
            deferred.callback(result)
        else:
            return result

    def _handle_failure(self, failure, method, args, kwargs, deferred=None,
                        call=None):
        """Called when a L{MethodCall} command fails.

        If a failure is due to a connection error}, and if C{retry_inteval} is
        not C{None} we will try to perform the requested L{MethodCall} again
        every C{retry_inteval} seconds, up to C{max_retries} times or
        indefinitely if C{max_retries} is C{None}.

        @param failure: The L{Failure} raised by the requested L{MethodCall}
        @param name: The method name associated with the failed L{MethodCall}
        @param args: The arguments of the failed L{MethodCall}.
        @param kwargs: The keyword arguments of the failed L{MethodCall}.
        @param deferred: If not C{None}, the deferred that was returned to
            the caller when the first attempt failed.
        @param call: If not C{None}, the scheduled timeout call associated with
            the given deferred.
        """
        is_first_failure = deferred is None
        is_method_call_error = failure.type is MethodCallError
        no_retry = self._retry_on_reconnect == False

        if is_method_call_error or no_retry:
            # This means that the connection is working, and a protocol
            # error occured, just propagate it.
            if is_first_failure:
                return failure
            else:
                if call:
                    call.cancel()
                deferred.errback(failure)
                return

        if is_first_failure:
            deferred = Deferred()
            if self._timeout:
                failure = Failure(MethodCallError("timeout"))
                call = self._reactor.callLater(self._timeout,
                                               self._handle_failure,
                                               failure, method, args,
                                               kwargs, deferred=deferred)

        self._pending_requests[deferred] = (method, args, kwargs, call)

        if is_first_failure:
            return deferred

    def _retry(self):
        """Try to perform again requests that failed."""

        # We need to copy the requests list before iterating over it, because
        # if we are still disconnected callRemote will immediately return a
        # failed deferred and the _handle_failure errback will be executed
        # during the iteration, modifing the requests list itself.
        requests = self._pending_requests
        self._pending_requests = {}

        while requests:
            deferred, (method, args, kwargs, call) = requests.popitem()
            result = self._call_remote(method, args, kwargs)
            result.addCallback(self._handle_response,
                               deferred=deferred, call=call)
            result.addErrback(self._handle_failure, method, args, kwargs,
                              deferred=deferred, call=call)


class RemoteObjectCreator(object):
    """Connect to remote objects exposed by a L{MethodCallProtocol}."""

    factory = MethodCallClientFactory
    remote = RemoteObject

    def __init__(self, reactor, socket, *args, **kwargs):
        """
        @param reactor: A reactor able to connect to Unix sockets.
        @param socket: The path to the socket we want to connect to.
        @param args: Arguments to passed to the created L{RemoteObject}.
        @param kwargs: Keyword arguments for the created L{RemoteObject}.
        """
        self._socket = socket
        self._reactor = reactor
        self._args = args
        self._kwargs = kwargs

    def connect(self):
        """Connect to a remote object exposed by a L{MethodCallProtocol}.

        This method will connect to the socket provided in the constructor
        and return a L{Deferred} resulting in a connected L{RemoteObject}.
        """
        self._connected = Deferred()
        self._factory = self.factory(self._reactor)
        self._factory.notifier = self._connection_made
        self._reactor.connectUNIX(self._socket, self._factory)
        return self._connected

    def _connection_made(self, protocol):
        """Called when the connection has been established"""
        self._remote = self.remote(protocol, *self._args, **self._kwargs)
        self._factory.notifier = self._remote._handle_reconnect
        self._connected.callback(self._remote)

    def disconnect(self):
        """Disconnect the L{RemoteObject} that we have created."""
        self._factory.stopTrying()
        self._remote._protocol.transport.loseConnection()
