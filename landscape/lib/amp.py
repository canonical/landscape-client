import inspect

from twisted.protocols.amp import Argument, String, Command, CommandLocator

from landscape.lib.bpickle import loads, dumps


class BPickle(Argument):
    """A bpickle-compatbile argument."""

    def toString(self, inObject):
        try:
            return dumps(inObject)
        except ValueError:
            return dumps(None)

    def fromString(self, inString):
        return loads(inString)


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


class MethodCallError(Exception):
    """Raised when trying to call a non accessible method."""


class MethodCall(Command):

    arguments = [("name", String()),
                 ("args", BPickle()),
                 ("kwargs", BPickle())]
    response = [("result", BPickle())]
    errors = {MethodCallError: "UNAUTHORIZED_METHOD_CALL"}

    @classmethod
    def responder(cls, protocol_method):
        """Decorator turning a protocol method into an L{MethodCall} responder.

        This decorator is used to implement remote procedure calls over AMP
        commands.  The decorated method must accept a C{name} parameter and
        return the callable associated with that name (typically and object's
        method with the same name).

        The idea is that if a connected AMP client sends a L{MethodCall} with
        name C{foo_bar}, then the actual method associated with C{foo_bar} as
        returned by the decorated method will be called and its return value
        delivered back to the client as response to the command.

        The L{MethodCall}'s C{args} and C{kwargs} arguments  will be passed to
        the actual method when calling it.

        @param cls: The L{MethodCall} class itself.
        @param method: A method of a L{MethodCallProtocol} sub-class.  The
            implementation of this method is supposed to be empty.
        """

        def call_object_method(self, **method_call_kwargs):
            name = method_call_kwargs["name"]
            args = method_call_kwargs["args"][:]
            kwargs = method_call_kwargs["kwargs"].copy()

            # Look for protocol attribute arguments
            for key, value in kwargs.iteritems():
                if key.startswith("_"):
                    kwargs.pop(key)
                    kwargs[key[1:]] = get_nested_attr(self, value)

            # Call the object method with the matching name
            object_method = protocol_method(self, name)
            if object_method is None:
                raise MethodCallError(name)
            result = object_method(*args, **kwargs)

            # Return an AMP response to be delivered to the remote caller
            if not cls.response:
                return {}
            else:
                return {"result": result}

        return CommandLocator._currentClassCommands.append(
            (MethodCall, call_object_method))

    @classmethod
    def sender(cls, method):
        """Decorator turning a method into an L{MethodCall} sender.

        Instances of the class of the method being decorated method must
        provide a C{_protocol} attribute, connected to the peer we want
        to send the L{MethodCall} command to.

        When the decorated method is called, it sends the an appropriate
        L{MethodCall} to the remote peer passing it the arguments and
        keyword arguments it was called with, and returing a L{Deferred}
        resulting in the L{MethodCall}'s response value.

        The generated L{MethodCall} will invoke the remote object method
        with the same name as the decorated method.

        The decorated method can include in its signature hidden keyword
        arguments starting with the prefix '_'.  Their default value
        will be treated as a protocol attribute name to be passed to the
        remote object method as extra argument.  It useful when the remote
        object method we want to call needs to be passed some extra
        protocol-specific argument that the connected AMP client can't know.
        """
        # The name of the decorated method must match the name of the
        # remote object method we want to call
        method_call_name = method.__name__

        # Check for protocol attributes arguments specified in the
        # method signature
        signature = inspect.getargspec(method)
        args = signature[0]
        defaults = signature[3]
        protocol_attributes_kwargs = {}
        if defaults is not None:
            for key, value in zip(args[-len(defaults):], defaults):
                if key.startswith("_"):
                    protocol_attributes_kwargs[key] = value

        def send_method_call(self, *args, **kwargs):
            method_call_args = args[:]
            method_call_kwargs = kwargs.copy()
            method_call_kwargs.update(protocol_attributes_kwargs)

            def unpack_response(response):
                if not cls.response:
                    return None
                else:
                    return response["result"]

            sent = self._protocol.callRemote(MethodCall,
                                             name=method_call_name,
                                             args=method_call_args,
                                             kwargs=method_call_kwargs)
            sent.addCallback(unpack_response)
            return sent

        return send_method_call
