"""Expose the methods of a remote object over AMP."""

from twisted.internet.defer import Deferred
from twisted.internet.protocol import ServerFactory, ClientFactory
from twisted.protocols.amp import Argument, String, Command, AMP

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

    response = [("result", MethodCallArgument())]

    errors = {MethodCallError: "METHOD_CALL_ERROR"}


class MethodCallProtocol(AMP):
    """Expose methods of a local object over AMP.

    The object to be exposed is expected to be the C{object} attribute of our
    protocol factory.

    @cvar methods: The list of exposed object's methods that can be called with
        the protocol. It must be defined by sub-classes.
    """

    methods = []

    @MethodCall.responder
    def call_object_method(self, method, args, kwargs):
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
        if not MethodCallArgument.check(result):
            raise MethodCallError("Non-serializable result")
        return {"result": result}


class MethodCallServerFactory(ServerFactory):
    """Factory for building L{MethodCallProtocol}s exposing an object."""

    protocol = MethodCallProtocol

    def __init__(self, object):
        """
        @param object: The object exposed by the L{MethodCallProtocol}s
            instances created by this factory.
        """
        self.object = object


class MethodCallClientFactory(ClientFactory):
    """Factory for building L{AMP} connections to L{MethodCall} servers."""

    protocol = AMP

    def __init__(self, reactor, notifier):
        """
        @param reactor: The reactor used to schedule connection callbacks.
        @param notifier: A function that will be called when the connection is
            established. It will be passed the protocol instance as argument.
        """
        self._reactor = reactor
        self._notifier = notifier

    def buildProtocol(self, addr):
        protocol = self.protocol()
        self._reactor.callLater(0, self._notifier, protocol)
        return protocol


class RemoteObject(object):
    """An object able to transparently call methods on a remote object.

    Any method call on a L{RemoteObject} instance will return a L{Deferred}
    resulting in the return value of the same method call performed on
    the remote object exposed by the peer.
    """

    def __init__(self, protocol):
        """
        @param protocol: A reference to a connected L{AMP} protocol instance,
            which will be used to send L{MethodCall} commands.
        """
        self._protocol = protocol

    def __getattr__(self, method):
        """Return a function sending a L{MethodCall} for the given C{method}.

        When the created function is called, it sends the an appropriate
        L{MethodCall} to the remote peer passing it the arguments and
        keyword arguments it was called with, and returning a L{Deferred}
        resulting in the L{MethodCall}'s response value.
        """

        def send_method_call(*args, **kwargs):
            result = self._protocol.callRemote(MethodCall,
                                               method=method,
                                               args=args[:],
                                               kwargs=kwargs.copy())
            return result.addCallback(lambda response: response["result"])

        return send_method_call


class RemoteObjectCreator(object):
    """Connect to remote objects exposed by a L{MethodCallProtocol}."""

    factory = MethodCallClientFactory
    remote = RemoteObject

    def __init__(self, reactor, socket):
        """
        @param reactor: A reactor able to connect to Unix sockets.
        @param socket: The path to the socket we want to connect to.
        """
        self._socket = socket
        self._reactor = reactor
        self._remote = None

    def connect(self):
        """Connect to a remote object exposed by a L{MethodCallProtocol}.

        This method will connect to the socket provided in the constructor
        and return a L{Deferred} resulting in a connected L{RemoteObject}.
        """
        deferred = Deferred()
        factory = self.factory(self._reactor, deferred.callback)
        self._reactor.connectUNIX(self._socket, factory)
        deferred.addCallback(self._connection_made)
        return deferred

    def _connection_made(self, protocol):
        """Called when the connection has been established"""
        self._remote = self.remote(protocol)
        return self._remote

    def disconnect(self):
        """Disconnect the L{RemoteObject} that we have created."""
        self._remote._protocol.transport.loseConnection()
