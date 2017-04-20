import unittest

from landscape.lib import bpickle


class BPickleTest(unittest.TestCase):

    def test_int(self):
        self.assertEqual(bpickle.loads(bpickle.dumps(1)), 1)

    def test_float(self):
        self.assertAlmostEquals(bpickle.loads(bpickle.dumps(2.3)), 2.3)

    def test_float_scientific_notation(self):
        number = 0.00005
        self.assertTrue("e" in repr(number))
        self.assertAlmostEquals(bpickle.loads(bpickle.dumps(number)), number)

    def test_bytes(self):
        self.assertEqual(bpickle.loads(bpickle.dumps(b'foo')), b'foo')

    def test_string(self):
        self.assertEqual(bpickle.loads(bpickle.dumps('foo')), 'foo')

    def test_list(self):
        self.assertEqual(bpickle.loads(bpickle.dumps([1, 2, 'hello', 3.0])),
                         [1, 2, 'hello', 3.0])

    def test_tuple(self):
        data = bpickle.dumps((1, [], 2, 'hello', 3.0))
        self.assertEqual(bpickle.loads(data),
                         (1, [], 2, 'hello', 3.0))

    def test_none(self):
        self.assertEqual(bpickle.loads(bpickle.dumps(None)), None)

    def test_unicode(self):
        self.assertEqual(bpickle.loads(bpickle.dumps(u'\xc0')), u'\xc0')

    def test_bool(self):
        self.assertEqual(bpickle.loads(bpickle.dumps(True)), True)

    def test_dict(self):
        dumped_tostr = bpickle.dumps({True: "hello"})
        self.assertEqual(bpickle.loads(dumped_tostr),
                         {True: "hello"})
        dumped_tobool = bpickle.dumps({True: False})
        self.assertEqual(bpickle.loads(dumped_tobool),
                         {True: False})

    def test_dict_bytes_keys(self):
        """Check loading dict bytes keys without reinterpreting."""
        # Happens in amp and broker. Since those messages are meant to be
        # forwarded to the server without changing schema, keys shouldn't be
        # decoded in this case.
        initial_data = {b"hello": True}
        data = bpickle.dumps(initial_data)
        result = bpickle.loads(data, as_is=True)
        self.assertEqual(initial_data, result)

    def test_long(self):
        long = 99999999999999999999999999999
        self.assertEqual(bpickle.loads(bpickle.dumps(long)), long)
