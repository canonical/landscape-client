
from landscape.lib.schema import KeyDict, Float, Bytes, Constant, Any


class Message(KeyDict):
    """
    Like L{KeyDict}, but with three predefined keys: C{type}, C{api},
    and C{timestamp}. Of these, C{api} and C{timestamp} are optional.


    @param type: The type of the message. The C{type} key will need to
        match this as a constant.
    @param schema: A dict of additional schema in a format L{KeyDict}
        will accept.
    @param optional: An optional list of keys that should be optional.
    @param api: The server API version needed to send this message,
        if C{None} any version is fine.
    """
    def __init__(self, type, schema, optional=None, api=None):
        self.type = type
        self.api = api
        schema["timestamp"] = Float()
        schema["api"] = Any(Bytes(), Constant(None))
        schema["type"] = Constant(type)
        if optional is not None:
            optional.extend(["timestamp", "api"])
        else:
            optional = ["timestamp", "api"]
        super(Message, self).__init__(schema, optional=optional)

    def coerce(self, value):
        for k in list(value.keys()):
            if k not in self.schema:
                # We don't know about this field, just discard it. This
                # is useful when a client that introduced some new field
                # in a message talks to an older server, that don't understand
                # the new field yet.
                value.pop(k)
        return super(Message, self).coerce(value)
