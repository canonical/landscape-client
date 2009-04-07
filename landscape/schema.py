"""A schema system. Yes. Another one!"""


class InvalidError(Exception):
    """Raised when invalid input is received."""
    pass


class Constant(object):
    """Something that must be equal to a constant value."""
    def __init__(self, value):
        self.value = value

    def coerce(self, value):
        if value != self.value:
            raise InvalidError("%r != %r" % (value, self.value))
        return value


class Any(object):
    """Something which must apply to any of a number of different schemas."""
    def __init__(self, *schemas):
        """
        @param schemas: Any number of other schema objects.
        """
        self.schemas = schemas

    def coerce(self, value):
        """
        The result of the first schema which doesn't raise
        L{InvalidError} from its C{coerce} method will be returned.
        """
        for schema in self.schemas:
            try:
                return schema.coerce(value)
            except InvalidError:
                pass
        raise InvalidError("%r did not match any schema in %s"
                           % (value, self.schemas))

class Bool(object):
    """Something that must be a C{bool}."""
    def coerce(self, value):
        if not isinstance(value, bool):
            raise InvalidError("%r is not a bool" % (value,))
        return value


class Int(object):
    """Something that must be an C{int} or C{long}."""
    def coerce(self, value):
        if not isinstance(value, (int, long)):
            raise InvalidError("%r isn't an int or long" % (value,))
        return value


class Float(object):
    """Something that must be an C{int}, C{long}, or C{float}."""
    def coerce(self, value):
        if not isinstance(value, (int, long, float)):
            raise InvalidError("%r isn't a float" % (value,))
        return value


class String(object):
    """Something that must be a C{str}."""
    def coerce(self, value):
        if not isinstance(value, str):
            raise InvalidError("%r isn't a str" % (value,))
        return value


class Unicode(object):
    """Something that must be a C{unicode}."""
    def coerce(self, value):
        if not isinstance(value, unicode):
            raise InvalidError("%r isn't a unicode" % (value,))
        return value


class UnicodeOrString(object):
    """Something that must be a C{unicode} or {str}.

    If the value is a C{str}, it will automatically be decoded.
    """

    def __init__(self, encoding):
        """
        @param encoding: The encoding to automatically decode C{str}s with.
        """
        self.encoding = encoding

    def coerce(self, value):
        if isinstance(value, str):
            try:
                value = value.decode(self.encoding)
            except UnicodeDecodeError, e:
                raise InvalidError("%r can't be decoded: %s" % (value, str(e)))
        if not isinstance(value, unicode):
            raise InvalidError("%r isn't a unicode" % (value,))
        return value


class List(object):
    """Something which must be a C{list}."""
    def __init__(self, schema):
        """
        @param schema: The schema that all values of the list must match.
        """
        self.schema = schema

    def coerce(self, value):
        if not isinstance(value, list):
            raise InvalidError("%r is not a list" % (value,))
        new_list = list(value)
        for i, subvalue in enumerate(value):
            try:
                new_list[i] = self.schema.coerce(subvalue)
            except InvalidError, e:
                raise InvalidError(
                    "%r could not coerce with %s: %s"
                    % (subvalue, self.schema, e))
        return new_list


class Tuple(object):
    """Something which must be a fixed-length tuple."""
    def __init__(self, *schema):
        """
        @param schema: A sequence of schemas, which will be applied to
            each value in the tuple respectively.
        """
        self.schema = schema

    def coerce(self, value):
        if not isinstance(value, tuple):
            raise InvalidError("%r is not a tuple" % (value,))
        if len(value) != len(self.schema):
            raise InvalidError("Need %s items, got %s in %r"
                               % (len(self.schema), len(value), value))
        new_value = []
        for schema, value in zip(self.schema, value):
            new_value.append(schema.coerce(value))
        return tuple(new_value)


class KeyDict(object):
    """Something which must be a C{dict} with defined keys.

    The keys must be constant and the values must match a per-key schema.
    """
    def __init__(self, schema, optional=None):
        """
        @param schema: A dict mapping keys to schemas that the values
            of those keys must match.
        """
        if optional is None:
            optional = []
        self.optional = set(optional)
        self.schema = schema

    def coerce(self, value):
        new_dict = {}
        if not isinstance(value, dict):
            raise InvalidError("%r is not a dict." % (value,))
        for k, v in value.iteritems():
            if k not in self.schema:
                raise InvalidError("%r is not a valid key as per %r"
                                   % (k, self.schema))
            try:
                new_dict[k] = self.schema[k].coerce(v)
            except InvalidError, e:
                raise InvalidError(
                    "Value of %r key of dict %r could not coerce with %s: %s"
                    % (k, value, self.schema[k], e))
        new_keys = set(new_dict.keys())
        required_keys = set(self.schema.keys()) - self.optional
        missing = required_keys - new_keys
        if missing:
            raise InvalidError("Missing keys %s" % (missing,))
        return new_dict


class Dict(object):
    """Something which must be a C{dict} with arbitrary keys."""

    def __init__(self, key_schema, value_schema):
        """
        @param key_schema: The schema that keys must match.
        @param value_schema: The schema that values must match.
        """
        self.key_schema = key_schema
        self.value_schema = value_schema

    def coerce(self, value):
        if not isinstance(value, dict):
            raise InvalidError("%r is not a dict." % (value,))
        new_dict = {}
        for k, v in value.items():
            new_dict[self.key_schema.coerce(k)] = self.value_schema.coerce(v)
        return new_dict


class Message(KeyDict):
    """
    Like L{KeyDict}, but with three predefined keys: C{type}, C{api},
    and C{timestamp}. Of these, C{api} and C{timestamp} are optional.


    @param type: The type of the message. The C{type} key will need to
        match this as a constant.

    @param schema: A dict of additional schema in a format L{KeyDict}
        will accept.
    @param optional: An optional list of keys that should be optional.
    """
    def __init__(self, type, schema, optional=None):
        self.type = type
        schema["timestamp"] = Float()
        schema["api"] = Any(String(), Constant(None))
        schema["type"] = Constant(type)
        if optional is not None:
            optional.extend(["timestamp", "api"])
        else:
            optional = ["timestamp", "api"]
        super(Message, self).__init__(schema, optional=optional)
