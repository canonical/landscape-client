import time

try:
    import sqlite3
except ImportError:
    from pysqlite2 import dbapi2 as sqlite3

from landscape.client.tests.helpers import LandscapeTest

from landscape.client.broker.exchangestore import ExchangeStore


class ExchangeStoreTest(LandscapeTest):
    """Unit tests for the C{ExchangeStore}."""

    def setUp(self):
        super(ExchangeStoreTest, self).setUp()

        self.filename = self.makeFile()
        self.store1 = ExchangeStore(self.filename)
        self.store2 = ExchangeStore(self.filename)

    def test_add_message_context(self):
        """Adding a message context works correctly."""
        now = time.time()
        self.store1.add_message_context(123, 'abc', 'change-packages')

        db = sqlite3.connect(self.store2._filename)
        cursor = db.cursor()
        cursor.execute(
            "SELECT operation_id, secure_id, message_type, timestamp "
            "FROM message_context WHERE operation_id=?", (123,))
        results = cursor.fetchall()
        self.assertEqual(1, len(results))
        [row] = results
        self.assertEqual(123, row[0])
        self.assertEqual('abc', row[1])
        self.assertEqual('change-packages', row[2])
        self.assertTrue(row[3] > now)

    def test_add_message_context_with_duplicate_operation_id(self):
        """Only one message context with a given operation-id is permitted."""
        self.store1.add_message_context(123, "abc", "change-packages")
        self.assertRaises(
            (sqlite3.IntegrityError, sqlite3.OperationalError),
            self.store1.add_message_context, 123, "def", "change-packages")

    def test_get_message_context(self):
        """
        Accessing a C{MessageContext} with an existing C{operation-id} works.
        """
        now = time.time()
        self.store1.add_message_context(234, 'bcd', 'change-packages')
        context = self.store2.get_message_context(234)
        self.assertEqual(234, context.operation_id)
        self.assertEqual('bcd', context.secure_id)
        self.assertEqual('change-packages', context.message_type)
        self.assertTrue(context.timestamp > now)

    def test_get_message_context_with_nonexistent_operation_id(self):
        """Attempts to access a C{MessageContext} with a non-existent
        C{operation-id} result in C{None}."""
        self.assertIs(None, self.store1.get_message_context(999))

    def test_message_context_remove(self):
        """C{MessageContext}s are deleted correctly."""
        context = self.store1.add_message_context(
            345, 'opq', 'change-packages')
        context.remove()
        self.assertIs(None, self.store1.get_message_context(345))

    def test_all_operation_ids_for_empty_database(self):
        """
        Calling C{all_operation_ids} on an empty database returns an empty
        list.
        """
        self.assertEqual([], self.store1.all_operation_ids())

    def test_all_operation_ids(self):
        """C{all_operation_ids} works correctly."""
        self.store1.add_message_context(456, 'cde', 'change-packages')
        self.assertEqual([456], self.store2.all_operation_ids())
        self.store2.add_message_context(567, 'def', 'change-packages')
        self.assertEqual([456, 567], self.store1.all_operation_ids())
