import unittest

from landscape.lib.schema import Int
from landscape.message_schemas.message import Message


class MessageTest(unittest.TestCase):

    def test_coerce(self):
        """The L{Message} schema should be very similar to KeyDict."""
        schema = Message("foo", {"data": Int()})
        self.assertEqual(
            schema.coerce({"type": "foo", "data": 3}),
            {"type": "foo", "data": 3})

    def test_timestamp(self):
        """L{Message} schemas should accept C{timestamp} keys."""
        schema = Message("bar", {})
        self.assertEqual(
            schema.coerce({"type": "bar", "timestamp": 0.33}),
            {"type": "bar", "timestamp": 0.33})

    def test_api(self):
        """L{Message} schemas should accept C{api} keys."""
        schema = Message("baz", {})
        self.assertEqual(
            schema.coerce({"type": "baz", "api": b"whatever"}),
            {"type": "baz", "api": b"whatever"})

    def test_api_None(self):
        """L{Message} schemas should accept None for C{api}."""
        schema = Message("baz", {})
        self.assertEqual(
            schema.coerce({"type": "baz", "api": None}),
            {"type": "baz", "api": None})

    def test_optional(self):
        """The L{Message} schema should allow additional optional keys."""
        schema = Message("foo", {"data": Int()}, optional=["data"])
        self.assertEqual(schema.coerce({"type": "foo"}), {"type": "foo"})

    def test_type(self):
        """The C{type} should be introspectable on L{Message} objects."""
        schema = Message("foo", {})
        self.assertEqual(schema.type, "foo")

    def test_with_unknown_fields(self):
        """
        The L{Message} schema discards unknown fields when coercing values.
        """
        schema = Message("foo", {})
        self.assertEqual({"type": "foo"},
                         schema.coerce({"type": "foo", "crap": 123}))
