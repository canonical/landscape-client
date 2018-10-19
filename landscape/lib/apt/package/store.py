"""Provide access to the persistent data used by L{PackageTaskHandler}s."""
import time

try:
    import sqlite3
except ImportError:
    from pysqlite2 import dbapi2 as sqlite3

from twisted.python.compat import iteritems, long

from landscape.lib import bpickle
from landscape.lib.store import with_cursor


class UnknownHashIDRequest(Exception):
    """Raised for unknown hash id requests."""


class InvalidHashIdDb(Exception):
    """Raised when trying to add an invalid hash=>id lookaside database."""


class HashIdStore(object):
    """C{HashIdStore} stores package hash=>id mappings in a file.

    The file is a SQLite database that contains a single table called "hash".
    The table schema is defined in L{ensure_hash_id_schema}.

    @param filename: The file where the mappings are persisted to.
    """
    _db = None

    def __init__(self, filename):
        self._filename = filename

    def _ensure_schema(self):
        ensure_hash_id_schema(self._db)

    @with_cursor
    def set_hash_ids(self, cursor, hash_ids):
        """Set the ids of a set of hashes.

        @param hash_ids: a C{dict} of hash=>id mappings.
        """
        for hash, id in iteritems(hash_ids):
            cursor.execute("REPLACE INTO hash VALUES (?, ?)",
                           (id, sqlite3.Binary(hash)))

    @with_cursor
    def get_hash_id(self, cursor, hash):
        """Return the id associated to C{hash}, or C{None} if not available.

        @param hash: a C{bytes} representing a hash.
        """
        cursor.execute("SELECT id FROM hash WHERE hash=?",
                       (sqlite3.Binary(hash),))
        value = cursor.fetchone()
        if value:
            return value[0]
        return None

    @with_cursor
    def get_hash_ids(self, cursor):
        """Return a C{dict} holding all the available hash=>id mappings."""
        cursor.execute("SELECT hash, id FROM hash")
        return {bytes(row[0]): row[1] for row in cursor.fetchall()}

    @with_cursor
    def get_id_hash(self, cursor, id):
        """Return the hash associated to C{id}, or C{None} if not available."""
        assert isinstance(id, (int, long))
        cursor.execute("SELECT hash FROM hash WHERE id=?", (id,))
        value = cursor.fetchone()
        if value:
            return bytes(value[0])
        return None

    @with_cursor
    def clear_hash_ids(self, cursor):
        """Delete all hash=>id mappings."""
        cursor.execute("DELETE FROM hash")

    @with_cursor
    def check_sanity(self, cursor):
        """Check database integrity.

        @raise: L{InvalidHashIdDb} if the filenme passed to the constructor is
            not a SQLite database or does not have a table called "hash" with
            a compatible schema.
        """
        try:
            cursor.execute("SELECT id FROM hash WHERE hash=?", ("",))
        except sqlite3.DatabaseError:
            raise InvalidHashIdDb(self._filename)


class PackageStore(HashIdStore):
    """Persist data about system packages and L{PackageTaskHandler}'s tasks.

    This class extends L{HashIdStore} by adding tables to the SQLite database
    backend for storing information about the status of the system packages and
    about the tasks to be performed by L{PackageTaskHandler}s.

    The additional tables and schemas are defined in L{ensure_package_schema}.

    @param filename: The file where data is persisted to.
    """

    def __init__(self, filename):
        super(PackageStore, self).__init__(filename)
        self._hash_id_stores = []

    def _ensure_schema(self):
        super(PackageStore, self)._ensure_schema()
        ensure_package_schema(self._db)

    def add_hash_id_db(self, filename):
        """
        Attach an additional "lookaside" hash=>id database.

        This method can be called more than once to attach several
        hash=>id databases, which will be queried *before* the main
        database, in the same the order they were added.

        If C{filename} is not a SQLite database or does not have a
        table called "hash" with a compatible schema, L{InvalidHashIdDb}
        is raised.

        @param filename: a secondary SQLite databases to look for pre-canned
                         hash=>id mappings.
        """
        hash_id_store = HashIdStore(filename)

        try:
            hash_id_store.check_sanity()
        except InvalidHashIdDb as e:
            # propagate the error
            raise e

        self._hash_id_stores.append(hash_id_store)

    def has_hash_id_db(self):
        """Return C{True} if one or more lookaside databases are attached."""
        return len(self._hash_id_stores) > 0

    def get_hash_id(self, hash):
        """Return the id associated to C{hash}, or C{None} if not available.

        This method composes the L{HashIdStore.get_hash_id} methods of all
        the attached lookaside databases, falling back to the main one, as
        described in L{add_hash_id_db}.
        """
        assert isinstance(hash, bytes)

        # Check if we can find the hash=>id mapping in the lookaside stores
        for store in self._hash_id_stores:
            id = store.get_hash_id(hash)
            if id:
                return id

        # Fall back to the locally-populated db
        return HashIdStore.get_hash_id(self, hash)

    def get_id_hash(self, id):
        """Return the hash associated to C{id}, or C{None} if not available.

        This method composes the L{HashIdStore.get_id_hash} methods of all
        the attached lookaside databases, falling back to the main one in
        case the hash associated to C{id} is not found in any of them.
        """
        for store in self._hash_id_stores:
            hash = store.get_id_hash(id)
            if hash is not None:
                return hash
        return HashIdStore.get_id_hash(self, id)

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
    def add_autoremovable(self, cursor, ids):
        for id in ids:
            cursor.execute("REPLACE INTO autoremovable VALUES (?)", (id,))

    @with_cursor
    def remove_autoremovable(self, cursor, ids):
        id_list = ",".join(str(int(id)) for id in ids)
        cursor.execute("DELETE FROM autoremovable WHERE id IN (%s)" % id_list)

    @with_cursor
    def clear_autoremovable(self, cursor):
        cursor.execute("DELETE FROM autoremovable")

    @with_cursor
    def get_autoremovable(self, cursor):
        cursor.execute("SELECT id FROM autoremovable")
        return [row[0] for row in cursor.fetchall()]

    @with_cursor
    def add_security(self, cursor, ids):
        for id in ids:
            cursor.execute("REPLACE INTO security VALUES (?)", (id,))

    @with_cursor
    def remove_security(self, cursor, ids):
        id_list = ",".join(str(int(id)) for id in ids)
        cursor.execute("DELETE FROM security WHERE id IN (%s)" % id_list)

    @with_cursor
    def clear_security(self, cursor):
        cursor.execute("DELETE FROM security")

    @with_cursor
    def get_security(self, cursor):
        cursor.execute("SELECT id FROM security")
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
    def get_locked(self, cursor):
        """Get the package ids of all locked packages."""
        cursor.execute("SELECT id FROM locked")
        return [row[0] for row in cursor.fetchall()]

    @with_cursor
    def add_locked(self, cursor, ids):
        """Add the given package ids to the list of locked packages."""
        for id in ids:
            cursor.execute("REPLACE INTO locked VALUES (?)", (id,))

    @with_cursor
    def remove_locked(self, cursor, ids):
        id_list = ",".join(str(int(id)) for id in ids)
        cursor.execute("DELETE FROM locked WHERE id IN (%s)" % id_list)

    @with_cursor
    def clear_locked(self, cursor):
        """Remove all the package ids in the locked table."""
        cursor.execute("DELETE FROM locked")

    @with_cursor
    def add_hash_id_request(self, cursor, hashes):
        hashes = list(hashes)
        cursor.execute("INSERT INTO hash_id_request (hashes, timestamp)"
                       " VALUES (?,?)",
                       (sqlite3.Binary(bpickle.dumps(hashes)), time.time()))
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
        return [HashIDRequest(self._db, row[0]) for row in cursor.fetchall()]

    @with_cursor
    def clear_hash_id_requests(self, cursor):
        cursor.execute("DELETE FROM hash_id_request")

    @with_cursor
    def add_task(self, cursor, queue, data):
        data = bpickle.dumps(data)
        cursor.execute(
            "INSERT INTO task (queue, timestamp, data) VALUES (?,?,?)",
            (queue, time.time(), sqlite3.Binary(data)))
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


class FakePackageStore(PackageStore):
    """
    A L{PackageStore} with an additional message table to store sent messages.
    """

    def _ensure_schema(self):
        super(FakePackageStore, self)._ensure_schema()
        ensure_fake_package_schema(self._db)

    @with_cursor
    def save_message(self, cursor, message):
        cursor.execute("INSERT INTO message (data) VALUES (?)",
                       (sqlite3.Binary(bpickle.dumps(message)),))

    @with_cursor
    def get_message_ids(self, cursor):
        return [row[0] for row in
                cursor.execute("SELECT id FROM message").fetchall()]

    @with_cursor
    def save_message_ids(self, cursor, message_ids):
        cursor.executemany(
            "INSERT INTO message (id) VALUES (?)",
            [(message_id,) for message_id in message_ids])

    @with_cursor
    def get_messages_by_ids(self, cursor, message_ids):
        params = ", ".join(["?"] * len(message_ids))
        result = cursor.execute(
                "SELECT id, data FROM message WHERE id IN (%s) "
                "ORDER BY id" % params, tuple(message_ids)).fetchall()
        return [(row[0], bytes(row[1])) for row in result]


class HashIDRequest(object):

    def __init__(self, db, id):
        self._db = db
        self.id = id

    @property
    @with_cursor
    def hashes(self, cursor):
        cursor.execute("SELECT hashes FROM hash_id_request WHERE id=?",
                       (self.id,))
        return bpickle.loads(bytes(cursor.fetchone()[0]))

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
        self.data = bpickle.loads(bytes(row[2]))

    @with_cursor
    def remove(self, cursor):
        cursor.execute("DELETE FROM task WHERE id=?", (self.id,))


def ensure_hash_id_schema(db):
    """Create all tables needed by a L{HashIdStore}.

    @param db: A connection to a SQLite database.
    """
    cursor = db.cursor()
    try:
        cursor.execute("CREATE TABLE hash"
                       " (id INTEGER PRIMARY KEY, hash BLOB UNIQUE)")
    except (sqlite3.OperationalError, sqlite3.DatabaseError):
        cursor.close()
        db.rollback()
    else:
        cursor.close()
        db.commit()


def ensure_package_schema(db):
    """Create all tables needed by a L{PackageStore}.

    @param db: A connection to a SQLite database.
    """
    # FIXME This needs a "patch" table with a "version" column which will
    #       help with upgrades.  It should also be used to decide when to
    #       create the schema from the ground up, rather than that using
    #       try block.
    cursor = db.cursor()
    try:
        cursor.execute("CREATE TABLE security"
                       " (id INTEGER PRIMARY KEY)")
        cursor.execute("CREATE TABLE autoremovable"
                       " (id INTEGER PRIMARY KEY)")
        cursor.execute("CREATE TABLE locked"
                       " (id INTEGER PRIMARY KEY)")
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


def ensure_fake_package_schema(db):
    cursor = db.cursor()
    try:
        cursor.execute("CREATE TABLE message"
                       " (id INTEGER PRIMARY KEY, data BLOB)")
    except (sqlite3.OperationalError, sqlite3.DatabaseError):
        cursor.close()
        db.rollback()
    else:
        cursor.close()
        db.commit()
