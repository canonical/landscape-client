import os
from os.path import join
import gdbm

from landscape.lib.persist import Persist
from landscape.tests.helpers import LandscapeTest

from landscape.patch import UpgradeManager
from landscape.upgraders import legacy
from landscape.package.store import PackageStore


class TestUpgraders(LandscapeTest):

    def test_v8_upgrade_user_data(self):
        persist = Persist()
        old_user_data = {"users": {
            1001: {"home-phone": None, "username": "testing", "uid": 1001,
                     "enabled": True, "location": None, "primary-gid": 1001,
                     "work-phone":None, "name": u"Testing"},
               4: {"home-phone": None, "username":"sync", "uid": 4,
                     "enabled": True, "location": None, "primary-gid": 65534,
                     "work-phone": None, "name": u"sync"}
             }
        }
        persist.set("users", old_user_data)
        legacy.index_users_on_names_added(persist)
        expected_user_data = {
            "testing": {"home-phone": None, "username": "testing", "uid": 1001,
                        "enabled": True, "location": None, "primary-gid": 1001,
                        "work-phone":None, "name": u"Testing"},
            "sync":    {"home-phone": None, "username":"sync", "uid": 4,
                        "enabled": True, "location": None,
                        "primary-gid": 65534, "work-phone": None,
                         "name": u"sync"}
        }
        self.assertEquals(persist.get("users")["users"],
                          expected_user_data)

    def test_v8_upgrade_group_data(self):
        """
        The newer group format uses usernames instead of user ids in the list
        of members of a group.  So we need to translate between them.

        If a user is found in the list of members, that we can't find by id,
        then we drop it from the persistent data.
        """
        persist = Persist()
        # The "scanner" group contains an unknown userid "9", we expect it to
        # be dropped.
        old_user_data = {
            "users": {
                1001: {"home-phone": None, "username": "testing",
                         "uid": 1001, "enabled": True, "location": None,
                         "primary-gid": 1001, "work-phone":None,
                         "name": u"Testing"},
                   4: {"home-phone": None, "username":"sync", "uid": 4,
                         "enabled": True, "location": None,
                         "primary-gid": 65534,
                         "work-phone": None, "name": u"sync"}},
            "groups": {
                5: {"gid": 5, "name": "tty", "members": []},
              104: {"gid": 104,"name": "scanner",
                    "members": [1001, 4, 9]}}
        }
        persist.set("users", old_user_data)
        legacy.index_users_on_names_added(persist)
        expected_group_data = {
            "tty":   {"gid": 5, "name": "tty", "members": []},
            "scanner": {"gid": 104,"name": "scanner",
                        "members": ["sync", "testing"]},
        }
        self.assertEquals(persist.get("users")["groups"],
                          expected_group_data)

    def test_v7_move_registration_data(self):
        """
        Move the registration-related data to the "registration" namespace.
        """
        persist = Persist()
        persist.set("message-store.secure_id", "SECURE")
        persist.set("http-ping.insecure-id", "INSECURE")
        legacy.move_registration_data(persist)
        self.assertFalse(persist.has("message-store.secure_id"))
        self.assertFalse(persist.has("http-ping.insecure-id"))
        self.assertEquals(persist.get("registration.secure-id"), "SECURE")
        self.assertEquals(persist.get("registration.insecure-id"), "INSECURE")

    def test_v6_rename_message_queue(self):
        """
        Rename "message-queue" to "message-store".
        """
        persist = Persist()
        persist.set("message-store", "DATA")
        legacy.rename_message_queue(persist)
        self.assertFalse(persist.has("message-queue"))
        self.assertEquals(persist.get("message-store"), "DATA")

        # Shouldn't break or overwrite if nothing to do.
        legacy.rename_message_queue(persist)
        self.assertFalse(persist.has("message-queue"))
        self.assertEquals(persist.get("message-store"), "DATA")

    def test_v5_update_user_data(self):
        """
        The v5 upgrader removes 'users' and 'groups' data from the
        persist database.
        """
        persist = Persist()
        users = persist.root_at("users")
        users.set("users", ["user data!"])
        users.set("groups", ["user data!"])
        legacy.user_change_detection_added(persist)
        self.assertFalse(users.has("users"))
        self.assertFalse(users.has("groups"))

    def test_v4_delete_user_data(self):
        """
        The v4 upgrader simply removes old-format user data.
        """
        persist = Persist()
        users = persist.root_at("users")
        users.set("data", {"fooble": "blatto"})
        legacy.group_support_added(persist)
        self.assertFalse(users.has("data"))

    def test_v3_delete_urgent_exchange(self):
        persist = Persist()
        message_exchange = persist.root_at("message-exchange")
        message_exchange.set("urgent-exchange", True)
        legacy.delete_urgent_exchange(persist)
        self.assertFalse(message_exchange.has("urgent-exchange"))

    def test_v2_delete_old_resource_data(self):
        """
        The upgrader needs to remove old resource data.
        """
        persist = Persist()
        persist.set("load-average", 1)
        persist.set("memory-info", 1)
        persist.set("mount-info", 1)
        persist.set("processor-info", 1)
        persist.set("temperature", 1)
        persist.set("trip-points", 1)

        legacy.delete_old_resource_data(persist)

        self.assertEquals(persist.get("load-average"), None)
        self.assertEquals(persist.get("memory-info"), None)
        self.assertEquals(persist.get("mount-info"), None)
        self.assertEquals(persist.get("processor-info"), None)
        self.assertEquals(persist.get("temperature"), None)
        self.assertEquals(persist.get("trip-points"), None)

    def test_v1_delete_user_data(self):
        persist = Persist()
        users = persist.root_at("users")
        users.set("data", {"fooble": "blatto"})
        legacy.delete_user_data(persist)
        self.assertFalse(users.has("data"))


class TestMigration(LandscapeTest):

    def setUp(self):
        super(TestMigration, self).setUp()
        self.data_dir = self.makeDir()
        self.persist_filename = "data.bpickle"
        self.broker_filename = "broker_data.bpickle"
        self.monitor_filename = "monitor_data.bpickle"
        self.sqlite_filename = "hashdb.sqlite"
        self.hashdb_filename = "hash.db"
        self.upgrade_manager = UpgradeManager()
        self.persist = Persist(filename=join(self.data_dir,
                                             self.persist_filename))

    def migrate(self):
        legacy.migrate_data_file(self.data_dir,
                                 self.persist_filename,
                                 self.broker_filename,
                                 self.monitor_filename,
                                 self.hashdb_filename,
                                 self.sqlite_filename,
                                 self.upgrade_manager)

    def test_migrate_legacy_data_migrates_monitor_data(self):
        """
        Make sure the migrater migrates monitor data from the old
        persist file into the monitor persist file.
        """
        self.persist.set("load-average", {"A" : 1})
        self.persist.set("memory-info", {"B" : 2})
        self.persist.set("mount-info", {"C" : 3})
        self.persist.set("processor-info", {"D" : 4})
        self.persist.set("temperature", {"E" : 5})
        self.persist.set("computer-uptime", {"F" : 6})
        self.persist.set("computer-info", {"G" : 7})
        self.persist.set("hardware-inventory", {"H" : 8})
        self.persist.set("users", {"I" : 9})
        self.persist.save()

        self.migrate()

        monitor_filename = join(self.data_dir, self.monitor_filename)
        self.assertTrue(os.path.exists(monitor_filename))
        monitor_persist = Persist(filename=monitor_filename)

        self.assertEquals(monitor_persist.get("load-average"), {"A" : 1})
        self.assertEquals(monitor_persist.get("memory-info"), {"B" : 2})
        self.assertEquals(monitor_persist.get("mount-info"), {"C" : 3})
        self.assertEquals(monitor_persist.get("processor-info"), {"D" : 4})
        self.assertEquals(monitor_persist.get("temperature"), {"E" : 5})
        self.assertEquals(monitor_persist.get("computer-uptime"), {"F" : 6})
        self.assertEquals(monitor_persist.get("computer-info"), {"G" : 7})
        self.assertEquals(monitor_persist.get("hardware-inventory"), {"H" : 8})
        self.assertEquals(monitor_persist.get("users"), {"I" : 9})

    def test_migrate_legacy_data_migrates_broker_data(self):
        """
        Make sure the migrater migrates broker data from the old
        persist file into the broker persist file.
        """
        persist = self.persist.root_at("message-store")
        persist.set("foo", 33)
        persist = self.persist.root_at("message-exchange")
        persist.set("bar", 66)
        persist = self.persist.root_at("registration")
        persist.set("baz", 99)
        self.persist.save()
        self.migrate()
        broker_filename = join(self.data_dir, self.broker_filename)
        self.assertTrue(os.path.exists(broker_filename))

        broker_persist = Persist(filename=broker_filename)
        self.assertEquals(broker_persist.get("message-store.foo"), 33)
        self.assertEquals(broker_persist.get("message-exchange.bar"), 66)
        self.assertEquals(broker_persist.get("registration.baz"), 99)

    def test_migrate_upgrades_existing_persist_first(self):
        """
        Make sure the migrater first applies all upgrades to the
        persist before migrating it.
        """
        l = []
        self.persist.save()
        self.upgrade_manager.register_upgrader(1, l.append)
        self.migrate()
        persist_filename = join(self.data_dir, self.persist_filename)
        self.assertTrue(os.path.exists(persist_filename))
        persist = Persist(filename=persist_filename)
        self.assertEquals(persist.get("system-version"), 1)
        self.assertEquals(l[0].get("system-version"), 1)

    def test_migrate_partially_upgraded_persist(self):
        """Unapplied patches are applied before migration occurs."""
        self.persist.set("system-version", 1)
        self.persist.save()

        first = []
        second = []
        self.upgrade_manager.register_upgrader(1, first.append)
        self.upgrade_manager.register_upgrader(2, second.append)
        self.migrate()

        persist_filename = join(self.data_dir, self.persist_filename)
        self.assertTrue(os.path.exists(persist_filename))
        persist = Persist(filename=persist_filename)
        self.assertEquals(first, [])
        self.assertEquals(second[0].get("system-version"), 2)

    def test_migrate_creates_new_persist_first(self):
        """
        Make sure the migrater creates a new persist and marks it as
        applied with the most recent version if there is no existing
        persist data file.
        """
        l = []
        self.upgrade_manager.register_upgrader(1, l.append)
        persist_filename = join(self.data_dir, self.persist_filename)
        self.assertFalse(os.path.exists(persist_filename))

        self.migrate()

        self.assertTrue(os.path.exists(persist_filename))
        persist = Persist(filename=persist_filename)
        self.assertEquals(persist.get("system-version"), 1)

        # the upgrader is never called because the persist is created
        # fresh and just marked as the most recent version.
        self.assertEquals(l, [])

    def test_package_migrates_hash_db_to_sqlite(self):
        """
        Make sure migrater migrates legacy package hash data to the
        new sqlite-based package store.
        """
        hashdb = gdbm.open(join(self.data_dir, self.hashdb_filename), "cs")
        hashdb["HASH"] = "33"
        hashdb["33"] = "HASH"
        self.assertFalse(os.path.exists(join(self.data_dir,
                                             self.sqlite_filename)))

        self.migrate()

        store = PackageStore(join(self.data_dir, self.sqlite_filename))
        self.assertEquals(store.get_hash_id("HASH"), 33)
        self.assertEquals(store.get_id_hash(33), "HASH")

    def test_package_migrates_package_statistics_to_sqlite(self):
        """
        Make sure migrater migrates legacy installed, available and
        available upgrade package data in the persist file to the new
        sqlite-based package store.
        """
        hashdb = gdbm.open(join(self.data_dir, self.hashdb_filename), "cs")
        hashdb["HASH"] = "33"
        hashdb["33"] = "HASH"

        self.persist.set("package.installed", [33])
        self.persist.set("package.available", [34])
        self.persist.set("package.available_upgrades", [35])
        self.persist.save()
        self.assertFalse(os.path.exists(join(self.data_dir,
                                             self.sqlite_filename)))
        self.migrate()

        store = PackageStore(join(self.data_dir, self.sqlite_filename))
        self.assertEquals(store.get_installed(), [33])
        self.assertEquals(store.get_available(), [34])
        self.assertEquals(store.get_available_upgrades(), [35])
