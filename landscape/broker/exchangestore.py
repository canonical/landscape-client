"""Provide access to the persistent data used by the L{MessageExchange}."""
import time

try:
    import sqlite3
except ImportError:
    from pysqlite2 import dbapi2 as sqlite3

from landscape.lib.store import with_cursor


class MessageContext(object):
    """Stores a context for incoming messages that require a response.

    The context consists of

      - the "operation-id" value
      - the secure ID that was in effect when the message was received
      - the message type
      - the time when the message was received

    This data will be used to detect secure ID changes between the time at
    which the request message came in and the completion of the request.
    If the secure ID did change the result message is obolete and will not be
    sent to the server.

    @param db: the sqlite database handle.
    @param id: the database key value for this instance.
    """

    def __init__(self, db, operation_id, secure_id, message_type, timestamp):
        self._db = db
        self.operation_id = operation_id
        self.secure_id = secure_id
        self.message_type = message_type
        self.timestamp = timestamp

    @with_cursor
    def remove(self, cursor):
        cursor.execute(
            "DELETE FROM message_context WHERE operation_id=?",
            (self.operation_id,))


class ExchangeStore(object):
    """Message meta data required by the L{MessageExchange}.

    The implementation uses a SQLite database as backend, with a single table
    called "message_context", whose schema is defined in
    L{ensure_exchange_schema}.

    @param filename: The name of the file that contains the sqlite database.
    """
    _db = None

    def __init__(self, filename):
        self._filename = filename

    def _ensure_schema(self):
        ensure_exchange_schema(self._db)

    @with_cursor
    def add_message_context(
            self, cursor, operation_id, secure_id, message_type):
        """Add a L{MessageContext} with the given data."""
        params = (operation_id, secure_id, message_type, time.time())
        cursor.execute(
            "INSERT INTO message_context "
            "   (operation_id, secure_id, message_type, timestamp) "
            "   VALUES (?,?,?,?)", params)
        return MessageContext(self._db, *params)

    @with_cursor
    def get_message_context(self, cursor, operation_id):
        """The L{MessageContext} for the given C{operation_id} or C{None}."""
        cursor.execute(
            "SELECT operation_id, secure_id, message_type, timestamp "
            "FROM message_context WHERE operation_id=?", (operation_id,))
        row = cursor.fetchone()
        if row:
            return MessageContext(self._db, *row)
        else:
            return None

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
