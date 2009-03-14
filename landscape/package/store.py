import time
import os

try:
    import sqlite3
except ImportError:
    from pysqlite2 import dbapi2 as sqlite3

from landscape.lib import bpickle


class UnknownHashIDRequest(Exception):
    """Raised for unknown hash id requests."""


def with_cursor(method):
    """Decorator that encloses the method in a database transaction.

    Even though SQLite is supposed to be useful in autocommit mode, we've
    found cases where the database continued to be locked for writing
    until the cursor was closed.  With this in mind, instead of using
    the autocommit mode, we explicitly terminate transactions and enforce
    cursor closing with this decorator.
    """
    def inner(self, *args, **kwargs):
        try:
            cursor = self._db.cursor()
            try:
                result = method(self, cursor, *args, **kwargs)
            finally:
                cursor.close()
            self._db.commit()
        except:
            self._db.rollback()
            raise
        return result
    return inner


class PackageStore(object):

    def __init__(self, filename):
        self._db = sqlite3.connect(filename)
        ensure_schema(self._db)

        self._lookaside_dbs = []

    def add_lookaside_db(self, filename):
        """
        @param filenames: a secondary SQLite databases to look for pre-canned
            hash=>id mappings.

            This method can be called more than once to attach several
            lookaside databases, which will be queried *before* the main
            database, in the same the order they were added.

            The lookaside database must have a table called "hash" with a
            compatbile schema (see the ensure_schema() function).
        """
        # XXX possibly add some validation code here, to check that filename
        # is actually a SQLite database with the appropriate schema
        self._lookaside_dbs.append(sqlite3.connect(filename))

    @with_cursor
    def set_hash_ids(self, cursor, hash_ids):
        for hash, id in hash_ids.iteritems():
            cursor.execute("REPLACE INTO hash VALUES (?, ?)",
                           (id, buffer(hash)))

    def get_hash_id(self, hash):
        assert isinstance(hash, basestring)

        # Check if we can find the hash=>id mapping in the lookaside dbs
        for db in self._lookaside_dbs:
            id = self._get_hash_id_from_lookaside_db(db, hash)
            if id:
                return id

        # Fall back to the locally-populated db
        return self._get_hash_id_from_main_db(hash)

    @with_cursor
    def _get_hash_id_from_main_db(self, cursor, hash):
        cursor.execute("SELECT id FROM hash WHERE hash=?", (buffer(hash),))
        value = cursor.fetchone()
        if value:
            return value[0]
        return None

    def _get_hash_id_from_lookaside_db(self, db, hash):
        cursor = db.cursor()
        try:
            cursor.execute("SELECT id FROM hash WHERE hash=?", (buffer(hash),))
        finally:
            value = cursor.fetchone()
        cursor.close()
        if value:
            return value[0]
        return None

    @with_cursor
    def get_id_hash(self, cursor, id):
        assert isinstance(id, (int, long))
        cursor.execute("SELECT hash FROM hash WHERE id=?", (id,))
        value = cursor.fetchone()
        if value:
            return str(value[0])
        return None

    @with_cursor
    def clear_hash_ids(self, cursor):
        cursor.execute("DELETE FROM hash")

    @with_cursor
    def add_available(self, cursor, ids):
        for id in ids:
            cursor.execute("REPLACE INTO available VALUES (?)", (id,))

    @with_cursor
    def remove_available(self, cursor, ids):
        id_list = ",".join(str(int(id)) for id in ids)
        cursor.execute("DELETE FROM available WHERE id IN (%s)" % id_list)

    @with_cursor
    def clear_available(self, cursor):
        cursor.execute("DELETE FROM available")

    @with_cursor
    def get_available(self, cursor):
        cursor.execute("SELECT id FROM available")
        return [row[0] for row in cursor.fetchall()]

    @with_cursor
    def add_available_upgrades(self, cursor, ids):
        for id in ids:
            cursor.execute("REPLACE INTO available_upgrade VALUES (?)", (id,))

    @with_cursor
    def remove_available_upgrades(self, cursor, ids):
        id_list = ",".join(str(int(id)) for id in ids)
        cursor.execute("DELETE FROM available_upgrade WHERE id IN (%s)"
                       % id_list)

    @with_cursor
    def clear_available_upgrades(self, cursor):
        cursor.execute("DELETE FROM available_upgrade")

    @with_cursor
    def get_available_upgrades(self, cursor):
        cursor.execute("SELECT id FROM available_upgrade")
        return [row[0] for row in cursor.fetchall()]

    @with_cursor
    def add_installed(self, cursor, ids):
        for id in ids:
            cursor.execute("REPLACE INTO installed VALUES (?)", (id,))

    @with_cursor
    def remove_installed(self, cursor, ids):
        id_list = ",".join(str(int(id)) for id in ids)
        cursor.execute("DELETE FROM installed WHERE id IN (%s)" % id_list)

    @with_cursor
    def clear_installed(self, cursor):
        cursor.execute("DELETE FROM installed")

    @with_cursor
    def get_installed(self, cursor):
        cursor.execute("SELECT id FROM installed")
        return [row[0] for row in cursor.fetchall()]

    @with_cursor
    def add_hash_id_request(self, cursor, hashes):
        hashes = list(hashes)
        cursor.execute("INSERT INTO hash_id_request (hashes, timestamp)"
                       " VALUES (?,?)",
                       (buffer(bpickle.dumps(hashes)), time.time()))
        return HashIDRequest(self._db, cursor.lastrowid)

    @with_cursor
    def get_hash_id_request(self, cursor, request_id):
        cursor.execute("SELECT 1 FROM hash_id_request WHERE id=?",
                       (request_id,))
        if not cursor.fetchone():
            raise UnknownHashIDRequest(request_id)
        return HashIDRequest(self._db, request_id)

    @with_cursor
    def iter_hash_id_requests(self, cursor):
        cursor.execute("SELECT id FROM hash_id_request")
        for row in cursor.fetchall():
            yield HashIDRequest(self._db, row[0])

    @with_cursor
    def clear_hash_id_requests(self, cursor):
        cursor.execute("DELETE FROM hash_id_request")

    @with_cursor
    def add_task(self, cursor, queue, data):
        data = bpickle.dumps(data)
        cursor.execute("INSERT INTO task (queue, timestamp, data) "
                       "VALUES (?,?,?)", (queue, time.time(), buffer(data)))
        return PackageTask(self._db, cursor.lastrowid)

    @with_cursor
    def get_next_task(self, cursor, queue):
        cursor.execute("SELECT id FROM task WHERE queue=? ORDER BY timestamp",
                       (queue,))
        row = cursor.fetchone()
        if row:
            return PackageTask(self._db, row[0])
        return None

    @with_cursor
    def clear_tasks(self, cursor, except_tasks=()):
        cursor.execute("DELETE FROM task WHERE id NOT IN (%s)" %
                       ",".join([str(task.id) for task in except_tasks]))


class HashIDRequest(object):

    def __init__(self, db, id):
        self._db = db
        self.id = id

    @property
    @with_cursor
    def hashes(self, cursor):
        cursor.execute("SELECT hashes FROM hash_id_request WHERE id=?",
                       (self.id,))
        return bpickle.loads(str(cursor.fetchone()[0]))

    @with_cursor
    def _get_timestamp(self, cursor):
        cursor.execute("SELECT timestamp FROM hash_id_request WHERE id=?",
                       (self.id,))
        return cursor.fetchone()[0]

    @with_cursor
    def _set_timestamp(self, cursor, value):
        cursor.execute("UPDATE hash_id_request SET timestamp=? WHERE id=?",
                       (value, self.id))

    timestamp = property(_get_timestamp, _set_timestamp)

    @with_cursor
    def _get_message_id(self, cursor):
        cursor.execute("SELECT message_id FROM hash_id_request WHERE id=?",
                       (self.id,))
        return cursor.fetchone()[0]

    @with_cursor
    def _set_message_id(self, cursor, value):
        cursor.execute("UPDATE hash_id_request SET message_id=? WHERE id=?",
                       (value, self.id))

    message_id = property(_get_message_id, _set_message_id)

    @with_cursor
    def remove(self, cursor):
        cursor.execute("DELETE FROM hash_id_request WHERE id=?", (self.id,))


class PackageTask(object):

    def __init__(self, db, id):
        self._db = db
        self.id = id

        cursor = db.cursor()
        try:
            cursor.execute("SELECT queue, timestamp, data FROM task "
                           "WHERE id=?", (id,))
            row = cursor.fetchone()
        finally:
            cursor.close()

        self.queue = row[0]
        self.timestamp = row[1]
        self.data = bpickle.loads(str(row[2]))

    @with_cursor
    def remove(self, cursor):
        cursor.execute("DELETE FROM task WHERE id=?", (self.id,))


def ensure_schema(db):
    # FIXME This needs a "patch" table with a "version" column which will
    #       help with upgrades.  It should also be used to decide when to
    #       create the schema from the ground up, rather than that using
    #       try block.
    cursor = db.cursor()
    try:
        cursor.execute("CREATE TABLE hash"
                       " (id INTEGER PRIMARY KEY, hash BLOB UNIQUE)")
        cursor.execute("CREATE TABLE available"
                       " (id INTEGER PRIMARY KEY)")
        cursor.execute("CREATE TABLE available_upgrade"
                       " (id INTEGER PRIMARY KEY)")
        cursor.execute("CREATE TABLE installed"
                       " (id INTEGER PRIMARY KEY)")
        cursor.execute("CREATE TABLE hash_id_request"
                       " (id INTEGER PRIMARY KEY, timestamp TIMESTAMP,"
                       " message_id INTEGER, hashes BLOB)")
        cursor.execute("CREATE TABLE task"
                       " (id INTEGER PRIMARY KEY, queue TEXT,"
                       " timestamp TIMESTAMP, data BLOB)")
    except sqlite3.OperationalError:
        cursor.close()
        db.rollback()
    else:
        cursor.close()
        db.commit()
