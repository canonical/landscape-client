try:
    from pysqlite2 import dbapi2 as sqlite3
except:
    import sqlite3

from landscape.lib.persist import Persist
from landscape.patch import UpgradeManager, SQLiteUpgradeManager
from landscape.tests.helpers import LandscapeTest


class PatchTest(LandscapeTest):

    def setUp(self):
        LandscapeTest.setUp(self)
        self.persist = Persist()
        self.manager = UpgradeManager()

    def test_wb_nopatches(self):
        """
        Applying no patches should make no change to the database,
        apart from maybe specifying a default version.
        """
        self.assertEquals(self.persist._hardmap, {})
        self.manager.apply(self.persist)
        self.assertEquals(self.persist._hardmap, {"system-version": 0})

    def test_one_patch(self):
        """Test that patches are called and passed a L{Persist} object."""
        l = []
        self.manager.register_upgrader(1, l.append)
        self.manager.apply(self.persist)
        self.assertEquals(l, [self.persist])

    def test_two_patches(self):
        """Test that patches are run in order."""
        l = []
        self.manager.register_upgrader(2, lambda x: l.append(2))
        self.manager.register_upgrader(1, lambda x: l.append(1))

        self.manager.apply(self.persist)
        self.assertEquals(l, [1, 2])

    def test_record_version(self):
        """When a patch is run it should update the C{system-version}."""
        self.assertEquals(self.persist.get("system-version"), None)
        self.manager.register_upgrader(1, lambda x: None)
        self.manager.apply(self.persist)
        self.assertEquals(self.persist.get("system-version"), 1)

    def test_only_apply_unapplied_versions(self):
        """Upgraders should only be run if they haven't been run before."""
        l = []
        self.manager.register_upgrader(1, lambda x: l.append(1))
        self.manager.apply(self.persist)
        self.manager.apply(self.persist)
        self.assertEquals(l, [1])

    def test_initialize(self):
        """Marking no upgraders as applied should leave the version at 0."""
        self.manager.initialize(self.persist)
        self.assertEquals(self.persist.get("system-version"), 0)

    def test_initialize_with_upgraders(self):
        """
        After registering some upgraders, initialize should set the
        version for the new persist to the highest version number
        available, without running any of the upgraders.
        """
        self.manager.register_upgrader(1, lambda x: 1/0)
        self.manager.register_upgrader(5, lambda x: 1/0)
        self.manager.register_upgrader(3, lambda x: 1/0)
        self.manager.initialize(self.persist)

        self.assertEquals(self.persist.get("system-version"), 5)

    def test_decorated_upgraders_run(self):
        """
        Upgraders that use the L{upgrader} decorator should
        automatically register themselves with a given
        L{UpgradeManager} and be run when the manager applies patches.
        """
        upgrade_manager = UpgradeManager()
        @upgrade_manager.upgrader(1)
        def upgrade(persist):
            self.persist.set("upgrade-called", True)

        upgrade_manager.apply(self.persist)
        self.assertTrue(self.persist.get("upgrade-called"))


class SQLitePatchTest(LandscapeTest):

    def setUp(self):
        LandscapeTest.setUp(self)
        self.db_filename = self.make_path()
        self.db = sqlite3.connect(self.db_filename, isolation_level=None)
        self.cursor = self.db.cursor()
        self.manager = SQLiteUpgradeManager()
        self.version_query = "SELECT MAX(version) from patch"

    def test_no_patches(self):
        """
        Applying no patches should make no change to the database,
        apart from maybe specifying a default version.
        """
        self.manager.initialize(self.cursor)
        self.manager.apply(self.cursor)
        self.assertEquals(self.manager.get_database_versions(self.cursor),
                          set())

    def test_one_patch(self):
        """Test that patches are called and passed a sqlite db object."""
        l = []
        self.manager.initialize(self.cursor)
        self.manager.register_upgrader(1, l.append)
        self.manager.apply(self.cursor)
        self.assertEquals(l, [self.cursor])
        self.cursor.execute(self.version_query)
        self.assertEquals(self.cursor.fetchone(), (1,))

    def test_two_patches(self):
        """Test that patches are run in order."""
        l = []
        self.manager.initialize(self.cursor)
        self.manager.register_upgrader(2, lambda x: l.append(2))
        self.manager.register_upgrader(1, lambda x: l.append(1))

        self.manager.apply(self.cursor)
        self.assertEquals(l, [1, 2])
        self.cursor.execute(self.version_query)
        self.assertEquals(self.cursor.fetchone(), (2,))

    def test_only_apply_unapplied_versions(self):
        """Upgraders should only be run if they haven't been run before."""
        patch1 = []
        patch2 = []
        patch3 = []
        self.manager.initialize(self.cursor)
        self.manager.register_upgrader(1, lambda x: patch1.append(1))
        self.manager.register_upgrader(2, lambda x: patch2.append(1))
        self.manager.register_upgrader(3, lambda x: patch3.append(1))
        self.manager.apply_one(2, self.cursor)
        self.assertEquals((patch1, patch2, patch3), ([], [1], []))
        self.manager.apply(self.cursor)
        self.assertEquals((patch1, patch2, patch3), ([1], [1], [1]))

    def test_initialize_with_upgraders(self):
        """
        After registering some upgraders, initialize should set the
        version of the newly created database to the highest version
        available.
        """
        self.manager.register_upgrader(1, lambda x: 1/0)
        self.manager.register_upgrader(5, lambda x: 1/0)
        self.manager.register_upgrader(3, lambda x: 1/0)
        self.manager.initialize(self.cursor)
        self.assertEquals(self.manager.get_database_versions(self.cursor),
                          set([1, 3, 5]))

    def test_decorated_upgraders_run(self):
        """
        Upgraders that use the L{upgrader} decorator should
        automatically register themselves with a given
        L{UpgradeManager} and be run when the manager applies patches.
        """
        upgrade_manager = SQLiteUpgradeManager()
        upgrade_manager.initialize(self.cursor)
        l = []
        @upgrade_manager.upgrader(1)
        def upgrade(db):
            l.append(db)

        upgrade_manager.apply(self.cursor)
        self.assertEquals(l, [self.cursor])
