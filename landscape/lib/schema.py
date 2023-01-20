"""A schema system. Yes. Another one!"""
from twisted.python.compat import iteritems
from twisted.python.compat import long
from twisted.python.compat import unicode


class InvalidError(Exception):
    """Raised when invalid input is received."""

    pass


class Constant:
    """Something that must be equal to a constant value."""

    def __init__(self, value):
        self.value = value

    def coerce(self, value):
        if isinstance(self.value, str) and isinstance(value, bytes):
            try:
                value = value.decode()
            except UnicodeDecodeError:
                pass

        if value != self.value:
            raise InvalidError(f"{value!r} != {self.value!r}")
        return value


class Any:
    """Something which must apply to any of a number of different schemas.

    @param schemas: Other schema objects.
    """

    def __init__(self, *schemas):
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
        raise InvalidError(
            f"{value!r} did not match any schema in {self.schemas}",
        )


class Bool:
    """Something that must be a C{bool}."""

    def coerce(self, value):
        if not isinstance(value, bool):
            raise InvalidError(f"{value!r} is not a bool")
        return value


class Int:
    """Something that must be an C{int} or C{long}."""

    def coerce(self, value):
        if not isinstance(value, (int, long)):
            raise InvalidError(f"{value!r} isn't an int or long")
        return value


class Float:
    """Something that must be an C{int}, C{long}, or C{float}."""

    def coerce(self, value):
        if not isinstance(value, (int, long, float)):
            raise InvalidError(f"{value!r} isn't a float")
        return value


class Bytes:
    """A binary string.

    If the value is a Python3 str (unicode), it will be automatically
    encoded.
    """

    def coerce(self, value):
        if isinstance(value, bytes):
            return value

        if isinstance(value, str):
            return value.encode()

        raise InvalidError(f"{value!r} isn't a bytestring")


class Unicode:
    """Something that must be a C{unicode}.

    If the value is a C{str}, it will automatically be decoded.

    @param encoding: The encoding to automatically decode C{str}s with.
    """

    def __init__(self, encoding="utf-8"):
        self.encoding = encoding

    def coerce(self, value):
        if isinstance(value, bytes):
            try:
                value = value.decode(self.encoding)
            except UnicodeDecodeError as e:
                raise InvalidError(
                    "{!r} can't be decoded: {}".format(value, str(e)),
                )
        if not isinstance(value, unicode):
            raise InvalidError(f"{value!r} isn't a unicode")
        return value


class List:
    """Something which must be a C{list}.

    @param schema: The schema that all values of the list must match.
    """

    def __init__(self, schema):
        self.schema = schema

    def coerce(self, value):
        if not isinstance(value, list):
            raise InvalidError(f"{value!r} is not a list")
        new_list = list(value)
        for i, subvalue in enumerate(value):
            try:
                new_list[i] = self.schema.coerce(subvalue)
            except InvalidError as e:
                raise InvalidError(
                    f"{subvalue!r} could not coerce with {self.schema}: {e}",
                )
        return new_list


class Tuple:
    """Something which must be a fixed-length tuple.

    @param schema: A sequence of schemas, which will be applied to
        each value in the tuple respectively.
    """

    def __init__(self, *schema):
        self.schema = schema

    def coerce(self, value):
        if not isinstance(value, tuple):
            raise InvalidError(f"{value!r} is not a tuple")
        if len(value) != len(self.schema):
            raise InvalidError(
                f"Need {len(self.schema)} items, "
                f"got {len(value)} in {value!r}",
            )
        new_value = []
        for schema, value in zip(self.schema, value):
            new_value.append(schema.coerce(value))
        return tuple(new_value)


class KeyDict:
    """Something which must be a C{dict} with defined keys.

    The keys must be constant and the values must match a per-key schema.
    If strict, extra keys cause an exception during coercion.

    @param schema: A dict mapping keys to schemas that the values of those
        keys must match.
    """

    def __init__(self, schema, optional=None, strict=True):
        if optional is None:
            optional = []
        self.optional = set(optional)
        self.schema = schema
        self._strict = strict

    def coerce(self, value):
        new_dict = {}
        if not isinstance(value, dict):
            raise InvalidError(f"{value!r} is not a dict.")

        for k, v in iteritems(value):
            unknown_key = k not in self.schema

            if unknown_key and self._strict:
                raise InvalidError(
                    f"{k!r} is not a valid key as per {self.schema!r}",
                )
            elif unknown_key:
                # We are in non-strict mode, so we ignore unknown keys.
                continue

            try:
                new_dict[k] = self.schema[k].coerce(v)
            except InvalidError as e:
                raise InvalidError(
                    f"Value of {k!r} key of dict {value!r} could not coerce "
                    f"with {self.schema[k]}: {e}",
                )
        new_keys = set(new_dict.keys())
        required_keys = set(self.schema.keys()) - self.optional
        missing = required_keys - new_keys
        if missing:
            raise InvalidError(f"Missing keys {missing}")
        return new_dict


class Dict:
    """Something which must be a C{dict} with arbitrary keys.

    @param key_schema: The schema that keys must match.
    @param value_schema: The schema that values must match.
    """

    def __init__(self, key_schema, value_schema):
        self.key_schema = key_schema
        self.value_schema = value_schema

    def coerce(self, value):
        if not isinstance(value, dict):
            raise InvalidError(f"{value!r} is not a dict.")
        new_dict = {}
        for k, v in value.items():
            new_dict[self.key_schema.coerce(k)] = self.value_schema.coerce(v)
        return new_dict
