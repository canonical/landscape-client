import logging


class UpgraderConflict(Exception):
    """Two upgraders with the same version have been registered."""


class UpgradeManagerBase(object):
    """A simple upgrade system."""

    def __init__(self):
        self._upgraders = {}

    def register_upgrader(self, version, function):
        """
        @param version: The version number that this upgrader is
            upgrading the database to. This defines the order that
            upgraders are run.
        @param function: The function to call when applying
            upgraders. It must take a single object, the database that is
            being upgraded.
        """
        if version in self._upgraders:
            raise UpgraderConflict(
                "%s is already registered as %s; not adding %s" %
                (version, self._upgraders[version], function))
        self._upgraders[version] = function

    def get_version(self):
        """
        Get the 'current' version of any database that this
        UpgradeManager will be applied to.
        """
        keys = self._upgraders.keys()
        if keys:
            return max(keys)
        return 0

    def upgrader(self, version):
        """
        A decorator for specifying that a function is an upgrader for
        this upgrade manager.

        @param version: The version number that the function will be
            upgrading to.
        """
        def inner(function):
            self.register_upgrader(version, function)
            return function
        return inner


class UpgradeManager(UpgradeManagerBase):

    def apply(self, persist):
        """Bring the database up-to-date.

        @param persist: The database to upgrade. It will be passed to
            all upgrade functions.
        """
        if not persist.has("system-version"):
            persist.set("system-version", 0)
        for version, upgrader in sorted(self._upgraders.items()):
            if version > persist.get("system-version"):
                persist.set("system-version", version)
                upgrader(persist)
                logging.info("Successfully applied patch %s" % version)

    def initialize(self, persist):
        """
        Mark the database as being up-to-date; use this when
        initializing a new database.
        """
        persist.set("system-version", self.get_version())


class SQLiteUpgradeManager(UpgradeManagerBase):
    """An upgrade manager backed by sqlite."""

    def get_database_versions(self, cursor):
        cursor.execute("SELECT version FROM patch")
        result = cursor.fetchall()
        return set([row[0] for row in result])

    def get_database_version(self, cursor):
        cursor.execute("SELECT MAX(version) FROM patch")
        version = cursor.fetchone()[0]
        if version:
            return version
        return 0

    def apply(self, cursor):
        """Bring the database up-to-date."""
        versions = self.get_database_versions(cursor)
        for version, upgrader in sorted(self._upgraders.items()):
            if version not in versions:
                self.apply_one(version, cursor)

    def apply_one(self, version, cursor):
        upgrader = self._upgraders[version]
        upgrader(cursor)
        cursor.execute("INSERT INTO patch VALUES (?)", (version,))

    def initialize(self, cursor):
        """
        Mark the database as being up-to-date; use this when
        initializing a new SQLite database.
        """
        cursor.execute("CREATE TABLE patch (version INTEGER)")
        for version, upgrader in sorted(self._upgraders.items()):
            cursor.execute("INSERT INTO patch VALUES (?)", (version,))
