from uuid import uuid4

from twisted.internet.defer import Deferred
from twisted.internet.error import ConnectError
from twisted.internet.protocol import ServerFactory, ClientCreator
from twisted.protocols.amp import Argument, String, Command, AMP
from twisted.python.failure import Failure

from landscape.lib.bpickle import loads, dumps, dumps_table


class Method(object):
    """A callable method in the object of a L{MethodCallProtocol}.

    This class is used when sub-classing a L{MethodCallProtocol} for declaring
    the methods call the protocol will respond to.
    """

    def __init__(self, name, **kwargs):
        """
        @param name: The name of a callable method.
        @param kwargs: Optional additional protocol-specific keyword
            argument that must be passed to the method when call it.  Their
            default value  will be treated as a protocol attribute name
            to be passed to the object method as extra argument.  It useful
            when the remote object method we want to call needs to be passed
            some extra protocol-specific argument that the connected client
            can't know (for example the protocol object itself).
        """
        self.name = name
        self.kwargs = kwargs


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
    """Raised when trying to call a non accessible method."""


class MethodCall(Command):
    """Call a method on the object associated with a L{MethodCallProtocol}."""

    arguments = [("name", String()),
                 ("args", MethodCallArgument(optional=True)),
                 ("kwargs", MethodCallArgument(optional=True))]

    response = [("result", MethodCallArgument()),
                ("deferred", String(optional=True))]

    errors = {MethodCallError: "METHOD_CALL_ERROR"}


class _DeferredResponse(Command):
    """Fire a L{Deferred} associated with an outstanding method call result."""

    arguments = [("uuid", String()),
                 ("result", MethodCallArgument(optional=True)),
                 ("failure", String(optional=True))]
    requiresAnswer = False


class RemoteObject(object):
    """An object able to transparently call methods on a remote object.

    @ivar protocol: A reference to a connected L{MethodCallProtocol}, which
        will be used to send L{MethodCall} commands.
    """

    def __init__(self, protocol):
        self._protocol = protocol

    @property
    def protocol(self):
        """Return a reference to the connected L{MethodCallProtocol}."""
        return self._protocol

    def __getattr__(self, name):
        return self._create_method_call_sender(name)

    def _create_method_call_sender(self, name):
        """Create a L{MethodCall} sender for the method with the given C{name}.

        When the created function is called, it sends the an appropriate
        L{MethodCall} to the remote peer passing it the arguments and
        keyword arguments it was called with, and returing a L{Deferred}
        resulting in the L{MethodCall}'s response value.

        The generated L{MethodCall} will invoke the remote object method
        named C{name}..
        """

        def send_method_call(*args, **kwargs):
            method_call_name = name
            method_call_args = args[:]
            method_call_kwargs = kwargs.copy()
            called = self.protocol.callRemote(MethodCall,
                                              name=method_call_name,
                                              args=method_call_args,
                                              kwargs=method_call_kwargs)
            return called.addCallback(lambda response: response["result"])

        return send_method_call


class MethodCallProtocol(AMP):
    """A protocol for calling methods on a remote object.

    @cvar methods: A list of L{Method}s describing the methods that can be
        called with the protocol. It must be defined by sub-classes.
    @cvar timeout: A timeout for remote methods returning L{Deferred}s, if a
        response for the deferred is not received within this amount of
        seconds, the remote method call will errback with a L{MethodCallError}.
    @cvar remote_factory: The factory used to build the C{remote} attribute.
    @ivar object: The object exposed by the protocol instance, it can be passed
        to the constructor or set later on the protocol instance itself.
    @ivar remote: A L{RemoteObject} able to transparently call methods on
        to the actuall object associated with the remote peer protocol.
    """

    methods = []
    timeout = 60
    remote_factory = RemoteObject

    def __init__(self, reactor, object=None):
        """
        @param reactor: The reactor used by L{RemoteObject} associated with the
            protocol to schedule timeouts for methods returning L{Deferred}s.
        @param object: The object the requested methods will be called on. Each
            L{Method} declared in the C{methods} attribute is supposed to match
            an actuall method of the given C{object}. If C{None} is given, the
            protocol can only be used to invoke methods.
        """
        super(MethodCallProtocol, self).__init__()
        self._reactor = reactor
        self.object = object
        self.remote = self.remote_factory(self)

        self._methods_by_name = {}
        self._pending_responses = {}
        for method in self.methods:
            self._methods_by_name[method.name] = method

    @MethodCall.responder
    def _call_object_method(self, name, args, kwargs):
        """Call an object's method with the given arguments.

        If a connected client sends a L{MethodCall} with name C{foo_bar}, then
        the actual method C{foo_bar} of the object associated with the protocol
        will be called with the given C{args} and C{kwargs} and its return
        value delivered back to the client as response to the command.

        The L{MethodCall}'s C{args} and C{kwargs} arguments  will be passed to
        the actual method when calling it.
        """
        method = self._methods_by_name.get(name, None)
        if method is None:
            raise MethodCallError("Forbidden method '%s'" % name)

        method_func = getattr(self.object, name)
        method_args = []
        method_kwargs = {}

        if args:
            method_args.extend(args)
        if kwargs:
            method_kwargs.update(kwargs)
        if method.kwargs:
            for key, value in method.kwargs.iteritems():
                method_kwargs[key] = get_nested_attr(self, value)

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
            call = self._reactor.callLater(self.timeout, self._fire_deferred,
                                           uuid, None, "timeout")
            self._pending_responses[uuid] = (deferred, call)
            return deferred

        return response

    def callRemote(self, *args, **kwargs):
        result = super(MethodCallProtocol, self).callRemote(*args, **kwargs)
        if result is not None:
            return result.addCallback(self._handle_response)


class MethodCallFactory(ServerFactory):
    """Factory for building L{MethodCallProtocol}s."""

    protocol = MethodCallProtocol

    def __init__(self, reactor, object=None):
        """
        @param reactor: The reactor that will passed to the protocol.
        @param object: The object that will be associated with the created
            protocol.
        """
        self._reactor = reactor
        self.object = object

    def buildProtocol(self, addr):
        """Create a new protocol instance."""
        protocol = self.protocol(self._reactor, self.object)
        protocol.factory = self
        return protocol


class RemoteObjectCreator(object):
    """Connect to remote objects exposed by a L{MethodCallProtocol}."""

    protocol = MethodCallProtocol

    def __init__(self, reactor, socket):
        """
        @param reactor: A reactor able to connect to Unix sockets.
        @param socket: The path to the socket to connect to.
        """
        self._socket = socket
        self._reactor = reactor
        self._deferred = None

    def connect(self, retry_interval=None, max_retries=None):
        """Connect to the remote L{BrokerServer}.

        @param retry_interval: An optional interval in seconds, if the first
            connection attempt fails, this method will retry.
        @param max_retries: If not C{None}, the method will give up after this
            amount of retries.
        """

        def retry(failure):
            failure.trap(ConnectError)

            if not self._deferred:
                self._deferred = Deferred()

            next_max_retries = max_retries
            if next_max_retries is not None:
                next_max_retries -= 1
                if next_max_retries == 0:
                    self._deferred.errback(failure)
                    return

            self._reactor.callLater(retry_interval, self.connect,
                                    retry_interval=retry_interval,
                                    max_retries=next_max_retries)
            return self._deferred

        def set_protocol(protocol):
            self._protocol = protocol
            if self._deferred:
                self._deferred.callback(protocol.remote)
                self._deferred = None
            else:
                return protocol.remote

        connector = ClientCreator(self._reactor, self.protocol, self._reactor)
        connected = connector.connectUNIX(self._socket)
        connected.addCallback(set_protocol)
        if retry:
            connected.addErrback(retry)
        return connected

    def disconnect(self):
        """Disconnect from the remote L{BrokerServer}."""
        self._protocol.transport.loseConnection()


def get_nested_attr(obj, path):
    """Like C{getattr} but works with nested attributes as well.

    @param obj: The object we want to get the attribute of.
    @param path: The path to the attribute, like C{.some.nested.attr},
        if C{.} is given the object itself is returned.
    """
    attr = obj
    if path != "":
        for name in path.split(".")[:]:
            attr = getattr(attr, name)
    return attr
