import re
from twisted.protocols.amp import (
    Argument, String, Command, CommandLocator, AMP)

from landscape.lib.bpickle import loads, dumps


class StringOrNone(String):
    """An argument that can be a C{str} or C{None}."""

    def toString(self, inObject):
        if inObject is None:
            return ""
        else:
            return super(StringOrNone, self).toString(inObject)

    def fromString(self, inString):
        if inString == "":
            return None
        else:
            return super(StringOrNone, self).fromString(inString)


class BPickle(Argument):
    """A bpickle-compatbile argument."""

    def toString(self, inObject):
        return dumps(inObject)

    def fromString(self, inString):
        return loads(inString)


class ProtocolAttribute(Argument):
    """A protocol attribute that gets passed to the object as extra argument.

    This argument type works only with L{MethodCall}s commands. It useful
    the target object method we want to call needs to be passed some extra
    protocol-specific argument that the connected AMP client can't know.

    The argument name of a L{ProtocolAttribute} argument must always start
    with the C{__protocol_attribute} marker prefix and end with the name
    of the target object method argument it will be passed to.
    """

    def __init__(self, path):
        """
        @param attribute: The path to a possibly nested attribute of the
            protocol instance that should be passed to the target object
            method as extra argument.
        """
        self.optional = True
        self.retrieve = lambda d, name, proto: path
        self.toString = lambda x: path
        self.fromString = lambda x: path


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


class MethodCallProtocol(AMP):
    """An L{AMP}-based remote procedure call protocol."""

    @property
    def _object(self):
        """The object the remote L{MethodCall}s commands will be act on."""
        raise NotImplementedError()


class MethodCall(Command):

    @classmethod
    def get_method_name(cls):
        """
        Get the target object method name associated with this L{MethodCall}.
        """
        words = re.findall("[A-Z][a-z]+", cls.__name__)
        return "_".join(word.lower() for word in words)

    @classmethod
    def responder(cls, method):
        """Decorator turning a protocol method into an L{MethodCall} responder.

        This decorator is used to implement remote procedure calls over AMP
        commands.  The L{MethodCallProtocol} sub-class making use of it must
        define a C{_object} attribute, which must return an object that will
        be used as the target object to perform the remote procedure call on.

        The idea is that if a connected AMP client issues a C{FooBar} command,
        the target object method named L{foo_bar} will be called and its return
        value delivered back to the client as response to the command.  Note
        also that for this to work C{FooBar}'s C{attributes} and C{response}
        schemas must match the signature of the target object method.

        @param cls: The L{MethodCall} sub-class the given C{method} will be
            registered as responder of.
        @param method: A method of a L{MethodCallProtocol} sub-class.  The
            implementation of this method is supposed to be empty.
        """
        method_name = cls.get_method_name()

        def call_object_method(self, **command_kwargs):
            object_kwargs = command_kwargs.copy()

            # Look for protocol attribute arguments
            for key, value in object_kwargs.iteritems():
                prefix = "__protocol_attribute_"
                if key.startswith(prefix):
                    object_kwargs.pop(key)
                    object_kwargs[key[len(prefix):]] = get_nested_attr(self,
                                                                       value)

            # Call the model method with the matching name
            result = getattr(self._object, method_name)(**object_kwargs)

            # Return an AMP response to be delivered to the remote caller
            if not cls.response:
                return {}
            else:
                return {"result": result}

        return CommandLocator._currentClassCommands.append(
            (cls, call_object_method))

    @classmethod
    def sender(cls, method):
        """Decorator turning a protocol method into an L{MethodCall} sender.

        When the decorated method is called, it sends the associated
        L{MethodCall} to the remote peer passing it the arguments it
        was called with, and returing a L{Deferred} resulting in the
        command's response value.

        @param method: A method of a L{AMP} protocol.
        """

        def send_method_call(self, *method_args, **method_kwargs):
            command_kwargs = method_kwargs.copy()
            for method_arg, (name, kind) in zip(method_args, cls.arguments):
                command_kwargs[name] = method_arg

            def unpack_response(response):
                if not cls.response:
                    return None
                else:
                    return response["result"]

            sent = self.callRemote(cls, **command_kwargs)
            sent.addCallback(unpack_response)
            return sent

        return send_method_call
