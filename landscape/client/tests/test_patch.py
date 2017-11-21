import sqlite3

from landscape.lib.persist import Persist
from landscape.client.patch import UpgradeManager, SQLiteUpgradeManager
from landscape.client.tests.helpers import LandscapeTest


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
        self.assertEqual(self.persist._hardmap, {})
        self.manager.apply(self.persist)
        self.assertEqual(self.persist._hardmap, {"system-version": 0})

    def test_one_patch(self):
        """Test that patches are called and passed a L{Persist} object."""
        calls = []
        self.manager.register_upgrader(1, calls.append)
        self.manager.apply(self.persist)
        self.assertEqual(calls, [self.persist])

    def test_two_patches(self):
        """Test that patches are run in order."""
        calls = []
        self.manager.register_upgrader(2, lambda x: calls.append(2))
        self.manager.register_upgrader(1, lambda x: calls.append(1))

        self.manager.apply(self.persist)
        self.assertEqual(calls, [1, 2])

    def test_record_version(self):
        """When a patch is run it should update the C{system-version}."""
        self.assertEqual(self.persist.get("system-version"), None)
        self.manager.register_upgrader(1, lambda x: None)
        self.manager.apply(self.persist)
        self.assertEqual(self.persist.get("system-version"), 1)

    def test_only_apply_unapplied_versions(self):
        """Upgraders should only be run if they haven't been run before."""
        calls = []
        self.manager.register_upgrader(1, lambda x: calls.append(1))
        self.manager.apply(self.persist)
        self.manager.apply(self.persist)
        self.assertEqual(calls, [1])

    def test_initialize(self):
        """Marking no upgraders as applied should leave the version at 0."""
        self.manager.initialize(self.persist)
        self.assertEqual(self.persist.get("system-version"), 0)

    def test_initialize_with_upgraders(self):
        """
        After registering some upgraders, initialize should set the
        version for the new persist to the highest version number
        available, without running any of the upgraders.
        """
        self.manager.register_upgrader(1, lambda x: 1 / 0)
        self.manager.register_upgrader(5, lambda x: 1 / 0)
        self.manager.register_upgrader(3, lambda x: 1 / 0)
        self.manager.initialize(self.persist)

        self.assertEqual(self.persist.get("system-version"), 5)

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
        self.db_filename = self.makeFile()
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
        self.assertEqual(self.manager.get_database_versions(self.cursor),
                         set())

    def test_one_patch(self):
        """Test that patches are called and passed a sqlite db object."""
        calls = []
        self.manager.initialize(self.cursor)
        self.manager.register_upgrader(1, calls.append)
        self.manager.apply(self.cursor)
        self.assertEqual(calls, [self.cursor])
        self.cursor.execute(self.version_query)
        self.assertEqual(self.cursor.fetchone(), (1,))

    def test_two_patches(self):
        """Test that patches are run in order."""
        calls = []
        self.manager.initialize(self.cursor)
        self.manager.register_upgrader(2, lambda x: calls.append(2))
        self.manager.register_upgrader(1, lambda x: calls.append(1))

        self.manager.apply(self.cursor)
        self.assertEqual(calls, [1, 2])
        self.cursor.execute(self.version_query)
        self.assertEqual(self.cursor.fetchone(), (2,))

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
        self.assertEqual((patch1, patch2, patch3), ([], [1], []))
        self.manager.apply(self.cursor)
        self.assertEqual((patch1, patch2, patch3), ([1], [1], [1]))

    def test_initialize_with_upgraders(self):
        """
        After registering some upgraders, initialize should set the
        version of the newly created database to the highest version
        available.
        """
        self.manager.register_upgrader(1, lambda x: 1 / 0)
        self.manager.register_upgrader(5, lambda x: 1 / 0)
        self.manager.register_upgrader(3, lambda x: 1 / 0)
        self.manager.initialize(self.cursor)
        self.assertEqual(self.manager.get_database_versions(self.cursor),
                         set([1, 3, 5]))

    def test_decorated_upgraders_run(self):
        """
        Upgraders that use the L{upgrader} decorator should
        automatically register themselves with a given
        L{UpgradeManager} and be run when the manager applies patches.
        """
        upgrade_manager = SQLiteUpgradeManager()
        upgrade_manager.initialize(self.cursor)
        calls = []

        @upgrade_manager.upgrader(1)
        def upgrade(db):
            calls.append(db)

        upgrade_manager.apply(self.cursor)
        self.assertEqual(calls, [self.cursor])
