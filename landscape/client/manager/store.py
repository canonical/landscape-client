try:
    import sqlite3
except ImportError:
    from pysqlite2 import dbapi2 as sqlite3

from landscape.lib.apt.package.store import with_cursor


class ManagerStore(object):

    def __init__(self, filename):
        self._db = sqlite3.connect(filename)
        ensure_schema(self._db)

    @with_cursor
    def get_graph(self, cursor, graph_id):
        cursor.execute(
            "SELECT graph_id, filename, user FROM graph WHERE graph_id=?",
            (graph_id,))
        return cursor.fetchone()

    @with_cursor
    def get_graphs(self, cursor):
        cursor.execute("SELECT graph_id, filename, user FROM graph")
        return cursor.fetchall()

    @with_cursor
    def add_graph(self, cursor, graph_id, filename, user):
        cursor.execute(
            "SELECT graph_id FROM graph WHERE graph_id=?",
            (graph_id,))
        if cursor.fetchone():
            cursor.execute(
                "UPDATE graph SET filename=?, user=? WHERE graph_id=?",
                (filename, user, graph_id))
        else:
            cursor.execute(
                "INSERT INTO graph (graph_id, filename, user) "
                "VALUES (?, ?, ?)",
                (graph_id, filename, user))

    @with_cursor
    def remove_graph(self, cursor, graph_id):
        cursor.execute("DELETE FROM graph WHERE graph_id=?", (graph_id,))

    @with_cursor
    def set_graph_accumulate(self, cursor, graph_id, timestamp, value):
        cursor.execute(
            "SELECT graph_id, graph_timestamp, graph_value FROM "
            "graph_accumulate WHERE graph_id=?", (graph_id,))
        graph_accumulate = cursor.fetchone()
        if graph_accumulate:
            cursor.execute(
                "UPDATE graph_accumulate SET graph_timestamp = ?, "
                "graph_value = ? WHERE graph_id=?",
                (timestamp, value, graph_id))
        else:
            cursor.execute(
                "INSERT INTO graph_accumulate (graph_id, graph_timestamp, "
                "graph_value) VALUES (?, ?, ?)", (graph_id, timestamp, value))

    @with_cursor
    def get_graph_accumulate(self, cursor, graph_id):
        cursor.execute(
            "SELECT graph_id, graph_timestamp, graph_value FROM "
            "graph_accumulate WHERE graph_id=?", (graph_id,))
        return cursor.fetchone()


def ensure_schema(db):
    cursor = db.cursor()
    try:
        cursor.execute("CREATE TABLE graph"
                       " (graph_id INTEGER PRIMARY KEY,"
                       " filename TEXT NOT NULL, user TEXT)")
        cursor.execute("CREATE TABLE graph_accumulate"
                       " (graph_id INTEGER PRIMARY KEY,"
                       " graph_timestamp INTEGER, graph_value FLOAT)")
    except sqlite3.OperationalError:
        cursor.close()
        db.rollback()
    else:
        cursor.close()
        db.commit()
