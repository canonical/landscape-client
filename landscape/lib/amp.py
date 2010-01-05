from uuid import uuid4

from twisted.internet.defer import Deferred
from twisted.internet.protocol import ServerFactory
from twisted.protocols.amp import Argument, String, Integer, Command, AMP
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


class FireDeferred(Command):
    """Fire a L{Deferred} associated with an outstanding method call result."""

    arguments = [("uuid", String()),
                 ("result", MethodCallArgument(optional=True)),
                 ("failure", String(optional=True))]
    requiresAnswer = False


class MethodCallProtocol(AMP):
    """A protocol for calling methods on a remote object.

    @cvar methods: A list of L{Method}s describing the methods that can be
        called with the protocol. It must be defined by sub-classes.
    @cvar timeout: A timeout for remote methods returning L{Deferred}s, if a
        response for the deferred is not received within this amount of
        seconds, the remote method call will errback with a L{MethodCallError}.
    """

    methods = []
    timeout = 60

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
        self._object = object
        self._methods_by_name = {}
        self._pending_methods = {}
        for method in self.methods:
            self._methods_by_name[method.name] = method
        self.remote = RemoteObject(self)

    @MethodCall.responder
    def method_call_responder(self, name, args, kwargs):
        """Call an object method with the given arguments.

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

        method_func = getattr(self._object, name)
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
            result.addCallback(self.send_success, uuid)
            result.addErrback(self.send_failure, uuid)
            return {"result": None, "deferred": uuid}

        if not MethodCallArgument.check(result):
            raise MethodCallError("Non-serializable result")
        return {"result": result}

    def send_success(self, result, uuid):
        """Send a successful L{FireDeferred} for the given C{uuid}."""
        self.callRemote(FireDeferred, uuid=uuid, result=result)

    def send_failure(self, error, uuid):
        """Send a failed L{FireDeferred} for the given C{uuid}."""
        failure = str(error.value)
        self.callRemote(FireDeferred, uuid=uuid, failure=failure)

    @FireDeferred.responder
    def fire_deferred(self, uuid, result, failure):
        """Receive the deferred L{MethodCall} result.

        @param uuid: The id of the L{MethodCall} we're getting the result of.
        @param result: The result of the associated deferred if successful.
        @param failure: The failure message of the deferred if it failed.
        """
        deferred, call = self._pending_methods.pop(uuid)
        call.cancel()
        if failure is None:
            deferred.callback({"result": result})
        else:
            deferred.errback(MethodCallError(failure))
        return {}

    def cancel_deferred(self, uuid):
        if uuid in self._pending_methods:
            deferred, call = self._pending_methods.pop(uuid)
            deferred.errback(MethodCallError("timeout"))

    def handle_response(self, response):

        if response["deferred"]:
            uuid = response["deferred"]
            deferred = Deferred()
            call = self._reactor.callLater(self.timeout,
                                           self.cancel_deferred, uuid)
            self._pending_methods[uuid] = (deferred, call)
            return deferred

        return response

    def callRemote(self, *args, **kwargs):
        result = super(MethodCallProtocol, self).callRemote(*args, **kwargs)
        if result is not None:
            return result.addCallback(self.handle_response)


class RemoteObject(object):
    """An object able to transparently call methods on a remote object."""

    def __init__(self, protocol):
        self._protocol = protocol

    def __getattr__(self, name):
        return self.__method_call_sender(name)

    def __method_call_sender(self, name):
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
            sent = self._protocol.callRemote(MethodCall,
                                             name=method_call_name,
                                             args=method_call_args,
                                             kwargs=method_call_kwargs)
            sent.addCallback(lambda response: response["result"])
            return sent

        return send_method_call

    def __method_call_timeout(self, uuid):
        pass


class MethodCallFactory(ServerFactory):
    """Factory for building L{MethodCallProtocol}s."""

    protocol = MethodCallProtocol

    def __init__(self, *args, **kwargs):
        """
        @param args: Arguments to pass to the protocol constructor.
        @param kwargs: Keyword arguments for the protocol constructor.
        """
        self._args = args
        self._kwargs = kwargs

    def buildProtocol(self, addr):
        """Create a new protocol instance."""
        protocol = self.protocol(*self._args, **self._kwargs)
        protocol.factory = self
        return protocol


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
