"""Provide access to the persistent data used by the L{MessageExchange}."""
import time

try:
    import sqlite3
except ImportError:
    from pysqlite2 import dbapi2 as sqlite3

from landscape.lib.store import with_cursor


class MessageContext(object):
    """Stores the secure ID for incoming messages that require a response.

    This data will be used to detect secure ID changes between the time at
    which the request message came in and the completion of the request.
    If the secure ID did change the result message is obolete and will not be
    sent to the server.
    """
    def __init__(self, db, id):
        self._db = db
        self.id = id

        cursor = db.cursor()
        try:
            cursor.execute(
                "SELECT operation_id, secure_id, message_type, timestamp "
                "FROM message_context WHERE id=?", (id,))
            row = cursor.fetchone()
        finally:
            cursor.close()

        self.operation_id = row[0]
        self.secure_id = row[1]
        self.message_type = row[2]
        self.timestamp = row[3]

    @with_cursor
    def remove(self, cursor):
        cursor.execute("DELETE FROM message_context WHERE id=?", (self.id,))


class ExchangeStore(object):
    """Message meta data required by the L{MessageExchange}.

    The implementation uses a SQLite database as backend, with a single table
    called "message_context", whose schema is defined in
    L{ensure_exchange_schema}.
    """
    _db = None

    def __init__(self, filename):
        """
        @param filename: The file where the mappings are persisted to.
        """
        self._filename = filename

    def _ensure_schema(self):
        ensure_exchange_schema(self._db)

    @with_cursor
    def add_message_context(
        self, cursor, operation_id, secure_id, message_type):
        """Add a L{MessageContext} with the given data."""
        cursor.execute(
            "INSERT INTO message_context "
            "   (operation_id, secure_id, message_type, timestamp) "
            "   VALUES (?,?,?,?)",
            (operation_id, secure_id, message_type, time.time()))
        return MessageContext(self._db, cursor.lastrowid)

    @with_cursor
    def get_message_context(self, cursor, operation_id):
        """The L{MessageContext} for the given C{operation_id} or C{None}."""
        cursor.execute(
            "SELECT id FROM message_context WHERE operation_id=?",
            (operation_id,))
        result = cursor.fetchone()
        return MessageContext(self._db, result[0]) if result else None

    @with_cursor
    def all_operation_ids(self, cursor):
        """Return all operation IDs currently stored in C{message_context}."""
        cursor.execute("SELECT operation_id FROM message_context")
        result = cursor.fetchall()
        return [row[0] for row in result]


def ensure_exchange_schema(db):
    """Create all tables needed by a L{ExchangeStore}.

    @param db: A connection to a SQLite database.
    """
    cursor = db.cursor()
    try:
        cursor.execute(
            "CREATE TABLE message_context"
            " (id INTEGER PRIMARY KEY, timestamp TIMESTAMP, "
            "  secure_id TEXT NOT NULL, operation_id INTEGER NOT NULL, "
            "  message_type text NOT NULL)")
        cursor.execute(
            "CREATE UNIQUE INDEX msgctx_operationid_idx ON "
            "message_context(operation_id)")
    except (sqlite3.OperationalError, sqlite3.DatabaseError):
        cursor.close()
        db.rollback()
    else:
        cursor.close()
        db.commit()
