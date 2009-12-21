import inspect

from twisted.protocols.amp import Argument

from landscape.lib.bpickle import loads, dumps


class BPickle(Argument):

    def toString(self, inObject):
        return dumps(inObject)

    def fromString(self, inString):
        return loads(inString)


class Hidden(Argument):
    """A hidden argument passed to the model but not exposed to the caller.

    This is useful when using the L{amp_rpc_decorator}, if the target model
    method needs to be passed some extra protocol-specific argument that the
    AMP client can't know.

    The argument name of a L{Hidden} argument must always start with the
    prefix C{__amp_rpc_} and end with the name of the target model method
    argument it is associated with.
    """

    def __init__(self, attribute):
        """
        @param attribute: A the path to a possibly nested attribute of the
            protocol object, that should be passed to the model method as
            extra argument.
        """
        self.optional = True
        self.retrieve = lambda d, name, proto: attribute
        self.toString = lambda x: attribute
        self.fromString = lambda x: attribute


def amp_rpc_responder(method):
    """Decorator turning a protocol method into an L{Command} responder.

    This decorator is used to implement remote procedure calls over AMP
    commands.  The L{AMP}-based protocol instance making use of it must
    define an C{__amp_rpc_model__} attribute, which is the name of an
    attribute of the protocol itself that will be used as model object
    to perform the remote procedure call on.  The idea is that if a
    connected AMP client issues a C{FooBar} command, the model method
    call L{foo_bar} will be called and its return value delivered back
    to the client as response to the command.  Note also that for this
    to work the C{FooBar.attributes} and C{FooBar.response} schemas must
    match the signature of the target model method.

    @param method: A method of an L{AMP}-based protocol matching the name of
        the target model method that we want to call.  A L{Command} sub-class
        with equivalent appropriate name must exist, and the given C{method}
        will be registered as its responder.
    @result: An AMP response message, holding the result of the model call
        in its "result" key.
    """
    # Lookup the Command class the decorated method is associated with, for
    # example if method.__name__ is "foo_bar" the associated Command class
    # must be named "FooBar""
    outer_frame = inspect.stack()[1][0]
    command = outer_frame.f_globals["".join(
        [word.capitalize() for word in method.__name__.split("_")])]

    def call_model_method(self, **amp_kwargs):
        model_kwargs = amp_kwargs.copy()

        def get_nested_attr(path):
            """Like C{getattr} but works with nested attributes as well."""
            obj = self
            if path != ".":
                for attribute in path.split(".")[1:]:
                    obj = getattr(obj, attribute)
            return obj

        # Look for hidden arguments
        for key, value in model_kwargs.iteritems():
            if key.startswith("__amp_rpc"):
                model_kwargs.pop(key)
                model_kwargs[key.lstrip("__amp_rpc_")] = get_nested_attr(value)

        # Call the model method with the matching name
        model = get_nested_attr(self.__amp_rpc_model__)
        result = getattr(model, method.__name__)(**model_kwargs)

        # Return an AMP response to be delivered to the remote caller
        if result is None:
            return {}
        else:
            return {"result": result}

    return command.responder(call_model_method)
