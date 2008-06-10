import unittest

from dbus.types import Double

from landscape.lib import bpickle
from landscape.lib.bpickle_dbus import install, uninstall, dumps_utf8string


original = dict(bpickle.dumps_table)


class DBusBPickleExtensionsTest(unittest.TestCase):

    def tearDown(self):
        # Mutate the original object back to the original version
        # because rebinding it will cause bizarre failures.
        bpickle.dumps_table.clear()
        bpickle.dumps_table.update(original)

    def test_install(self):
        """
        Installing bpickle extensions for DBus types should add to the
        existing table.  Existing bpickle mappings shouldn't be
        changed.
        """
        install()
        self.assertNotEquals(original, bpickle.dumps_table)
        pre = set(original.iteritems())
        post = set(bpickle.dumps_table.iteritems())
        self.assertTrue(pre.issubset(post))

    def test_uninstall(self):
        """
        Uninstalling bpickle extensions for DBus types should remove
        whatever was added during installation.  Extensions installed
        by external components should not be affected by this
        operation.
        """
        install()
        self.assertFalse(object in bpickle.dumps_table)
        bpickle.dumps_table[object] = lambda obj: None

        uninstall()
        pre = set(original.iteritems())
        post = set(bpickle.dumps_table.iteritems())
        self.assertTrue(pre.issubset(post))
        self.assertTrue(object in bpickle.dumps_table)
        self.assertTrue(len(original)+1, len(bpickle.dumps_table))

    def test_dumps_utf8string(self):
        """
        Dumping a L{dbus.types.UTF8String} should produce the same
        bpickle output as would be produced for a C{unicode} value.
        """
        try:
            from dbus.types import UTF8String

            value = UTF8String("")
            self.assertEquals(dumps_utf8string(value), "u0:")
            value = UTF8String("Charlie!")
            self.assertEquals(dumps_utf8string(value), "u8:Charlie!")
        except ImportError:
            pass

    def test_dumps_double(self):
        """
        Dumping and restoring a L{dbus.types.Double} should result in the
        same value.
        """
        install()
        try:
            value = Double(480.0, variant_level=1)
        except TypeError:
            value = Double(480.0)
        self.assertAlmostEquals(bpickle.loads(bpickle.dumps(value)), 480.0)
