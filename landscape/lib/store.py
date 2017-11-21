"""Functions used by all sqlite-backed stores."""

try:
    import sqlite3
except ImportError:
    from pysqlite2 import dbapi2 as sqlite3


def with_cursor(method):
    """Decorator that encloses the method in a database transaction.

    Even though SQLite is supposed to be useful in autocommit mode, we've
    found cases where the database continued to be locked for writing
    until the cursor was closed.  With this in mind, instead of using
    the autocommit mode, we explicitly terminate transactions and enforce
    cursor closing with this decorator.
    """

    def inner(self, *args, **kwargs):
        if not self._db:
            # Create the database connection only when we start to actually
            # use it. This is essentially just a workaroud of a sqlite bug
            # happening when 2 concurrent processes try to create the tables
            # around the same time, the one which fails having an incorrect
            # cache and not seeing the tables
            self._db = sqlite3.connect(self._filename)
            self._ensure_schema()
        try:
            cursor = self._db.cursor()
            try:
                result = method(self, cursor, *args, **kwargs)
            finally:
                cursor.close()
            self._db.commit()
        except BaseException:
            self._db.rollback()
            raise
        return result
    return inner
