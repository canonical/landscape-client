import mock
import sqlite3
import threading
import time
import unittest

from landscape.lib import testing
from landscape.lib.apt.package.store import (
        HashIdStore, PackageStore, UnknownHashIDRequest, InvalidHashIdDb)


class BaseTestCase(testing.FSTestCase, unittest.TestCase):
    pass


class HashIdStoreTest(BaseTestCase):

    def setUp(self):
        super(HashIdStoreTest, self).setUp()

        self.filename = self.makeFile()
        self.store1 = HashIdStore(self.filename)
        self.store2 = HashIdStore(self.filename)

    def test_set_and_get_hash_id(self):
        self.store1.set_hash_ids({b"ha\x00sh1": 123, b"ha\x00sh2": 456})
        self.assertEqual(self.store1.get_hash_id(b"ha\x00sh1"), 123)
        self.assertEqual(self.store1.get_hash_id(b"ha\x00sh2"), 456)

    def test_get_hash_ids(self):
        hash_ids = {b"hash1": 123, b"hash2": 456}
        self.store1.set_hash_ids(hash_ids)
        self.assertEqual(self.store1.get_hash_ids(), hash_ids)

    def test_wb_lazy_connection(self):
        """
        The connection to the sqlite database is created only when some query
        gets actually requsted.
        """
        self.assertEqual(self.store1._db, None)
        self.store1.get_hash_ids()
        self.assertTrue(isinstance(self.store1._db, sqlite3.Connection))

    def test_wb_transactional_commits(self):
        """
        If the operation run by the store succeeds, C{commit} is called once on
        the connection.
        """
        db = sqlite3.connect(self.store1._filename)
        commits = []

        class FakeDb(object):
            def __getattr__(self, name):
                if name == "commit":
                    return self.commit
                return getattr(db, name)

            def commit(self):
                commits.append(None)

        self.store1._db = FakeDb()
        self.store1.set_hash_ids({})
        self.assertEqual([None], commits)

    def test_wb_transactional_rolls_back(self):
        """
        If the operation run by the store fails, C{rollback} is called once on
        the connection.
        """
        db = sqlite3.connect(self.store1._filename)
        rollbacks = []

        class FakeDb(object):
            def __getattr__(self, name):
                if name == "rollback":
                    return self.rollback
                return getattr(db, name)

            def rollback(self):
                rollbacks.append(None)

        self.store1._db = FakeDb()
        self.assertRaises(Exception, self.store1.set_hash_ids, None)
        self.assertEqual([None], rollbacks)

    def test_get_id_hash(self):
        self.store1.set_hash_ids({b"hash1": 123, b"hash2": 456})
        self.assertEqual(self.store2.get_id_hash(123), b"hash1")
        self.assertEqual(self.store2.get_id_hash(456), b"hash2")

    def test_clear_hash_ids(self):
        self.store1.set_hash_ids({b"ha\x00sh1": 123, b"ha\x00sh2": 456})
        self.store1.clear_hash_ids()
        self.assertEqual(self.store2.get_hash_id(b"ha\x00sh1"), None)
        self.assertEqual(self.store2.get_hash_id(b"ha\x00sh2"), None)

    def test_get_unexistent_hash(self):
        self.assertEqual(self.store1.get_hash_id(b"hash1"), None)

    def test_get_unexistent_id(self):
        self.assertEqual(self.store1.get_id_hash(123), None)

    def test_overwrite_id_hash(self):
        self.store1.set_hash_ids({b"hash1": 123})
        self.store2.set_hash_ids({b"hash2": 123})
        self.assertEqual(self.store1.get_hash_id(b"hash1"), None)
        self.assertEqual(self.store1.get_hash_id(b"hash2"), 123)

    def test_overwrite_hash_id(self):
        self.store1.set_hash_ids({b"hash1": 123})
        self.store2.set_hash_ids({b"hash1": 456})
        self.assertEqual(self.store1.get_id_hash(123), None)
        self.assertEqual(self.store1.get_id_hash(456), b"hash1")

    def test_check_sanity(self):

        store_filename = self.makeFile()
        db = sqlite3.connect(store_filename)
        cursor = db.cursor()
        cursor.execute("CREATE TABLE hash"
                       " (junk INTEGER PRIMARY KEY, hash BLOB UNIQUE)")
        cursor.close()
        db.commit()

        store = HashIdStore(store_filename)
        self.assertRaises(InvalidHashIdDb, store.check_sanity)


class PackageStoreTest(BaseTestCase):

    def setUp(self):
        super(PackageStoreTest, self).setUp()

        self.filename = self.makeFile()
        self.store1 = PackageStore(self.filename)
        self.store2 = PackageStore(self.filename)

    def test_has_hash_id_db(self):

        self.assertFalse(self.store1.has_hash_id_db())

        hash_id_db_filename = self.makeFile()
        HashIdStore(hash_id_db_filename)
        self.store1.add_hash_id_db(hash_id_db_filename)

        self.assertTrue(self.store1.has_hash_id_db())

    def test_add_hash_id_db_with_non_sqlite_file(self):

        def junk_db_factory():
            filename = self.makeFile()
            open(filename, "w").write("junk")
            return filename

        def raiseme():
            store_filename = junk_db_factory()
            try:
                self.store1.add_hash_id_db(store_filename)
            except InvalidHashIdDb as e:
                self.assertEqual(str(e), store_filename)
            else:
                self.fail()

        raiseme()
        self.assertFalse(self.store1.has_hash_id_db())

    def test_add_hash_id_db_with_wrong_schema(self):

        def non_compliant_db_factory():
            filename = self.makeFile()
            db = sqlite3.connect(filename)
            cursor = db.cursor()
            cursor.execute("CREATE TABLE hash"
                           " (junk INTEGER PRIMARY KEY, hash BLOB UNIQUE)")
            cursor.close()
            db.commit()
            return filename

        self.assertRaises(InvalidHashIdDb, self.store1.add_hash_id_db,
                          non_compliant_db_factory())
        self.assertFalse(self.store1.has_hash_id_db())

    def hash_id_db_factory(self, hash_ids):
        filename = self.makeFile()
        store = HashIdStore(filename)
        store.set_hash_ids(hash_ids)
        return filename

    def test_get_hash_id_using_hash_id_dbs(self):
        # Without hash=>id dbs
        self.assertEqual(self.store1.get_hash_id(b"hash1"), None)
        self.assertEqual(self.store1.get_hash_id(b"hash2"), None)

        # This hash=>id will be overriden
        self.store1.set_hash_ids({b"hash1": 1})

        # Add a couple of hash=>id dbs
        self.store1.add_hash_id_db(self.hash_id_db_factory({b"hash1": 2,
                                                            b"hash2": 3}))
        self.store1.add_hash_id_db(self.hash_id_db_factory({b"hash2": 4,
                                                            b"ha\x00sh1": 5}))

        # Check look-up priorities and binary hashes
        self.assertEqual(self.store1.get_hash_id(b"hash1"), 2)
        self.assertEqual(self.store1.get_hash_id(b"hash2"), 3)
        self.assertEqual(self.store1.get_hash_id(b"ha\x00sh1"), 5)

    def test_get_id_hash_using_hash_id_db(self):
        """
        When lookaside hash->id dbs are used, L{get_id_hash} has
        to query them first, falling back to the regular db in case
        the desired mapping is not found.
        """
        self.store1.add_hash_id_db(self.hash_id_db_factory({b"hash1": 123}))
        self.store1.add_hash_id_db(self.hash_id_db_factory({b"hash1": 999,
                                                            b"hash2": 456}))
        self.store1.set_hash_ids({b"hash3": 789})
        self.assertEqual(self.store1.get_id_hash(123), b"hash1")
        self.assertEqual(self.store1.get_id_hash(456), b"hash2")
        self.assertEqual(self.store1.get_id_hash(789), b"hash3")

    def test_add_and_get_available_packages(self):
        self.store1.add_available([1, 2])
        self.assertEqual(self.store2.get_available(), [1, 2])

    def test_add_available_conflicting(self):
        """Adding the same available pacakge id twice is fine."""
        self.store1.add_available([1])
        self.store1.add_available([1])
        self.assertEqual(self.store2.get_available(), [1])

    def test_remove_available(self):
        self.store1.add_available([1, 2, 3, 4])
        self.store1.remove_available([2, 3])
        self.assertEqual(self.store2.get_available(), [1, 4])

    def test_clear_available(self):
        self.store1.add_available([1, 2, 3, 4])
        self.store1.clear_available()
        self.assertEqual(self.store2.get_available(), [])

    def test_add_and_get_available_upgrades_packages(self):
        self.store1.add_available_upgrades([1, 2])
        self.assertEqual(self.store2.get_available_upgrades(), [1, 2])

    def test_add_available_upgrades_conflicting(self):
        """Adding the same available_upgrades pacakge id twice is fine."""
        self.store1.add_available_upgrades([1])
        self.store1.add_available_upgrades([1])
        self.assertEqual(self.store2.get_available_upgrades(), [1])

    def test_add_available_upgrades_timing(self):
        """Adding 20k ids must take less than 5 seconds."""
        started = time.time()
        self.store1.add_available_upgrades(range(20000))
        self.assertTrue(time.time() - started < 5,
                        "Adding 20k available upgrades ids took "
                        "more than 5 seconds.")

    def test_remove_available_upgrades(self):
        self.store1.add_available_upgrades([1, 2, 3, 4])
        self.store1.remove_available_upgrades([2, 3])
        self.assertEqual(self.store2.get_available_upgrades(), [1, 4])

    def test_remove_available_upgrades_timing(self):
        self.store1.add_available_upgrades(range(20000))
        started = time.time()
        self.store1.remove_available_upgrades(range(20000))
        self.assertTrue(time.time() - started < 5,
                        "Removing 20k available upgrades ids took "
                        "more than 5 seconds.")

    def test_clear_available_upgrades(self):
        self.store1.add_available_upgrades([1, 2, 3, 4])
        self.store1.clear_available_upgrades()
        self.assertEqual(self.store2.get_available_upgrades(), [])

    def test_add_and_get_autoremovable(self):
        self.store1.add_autoremovable([1, 2])
        value = self.store1.get_autoremovable()
        self.assertEqual([1, 2], value)

    def test_clear_autoremovable(self):
        self.store1.add_autoremovable([1, 2])
        self.store1.clear_autoremovable()
        value = self.store1.get_autoremovable()
        self.assertEqual([], value)

    def test_remove_autoremovable(self):
        self.store1.add_autoremovable([1, 2, 3, 4])
        self.store1.remove_autoremovable([2, 4, 5])
        value = self.store1.get_autoremovable()
        self.assertEqual([1, 3], value)

    def test_add_and_get_installed_packages(self):
        self.store1.add_installed([1, 2])
        self.assertEqual(self.store2.get_installed(), [1, 2])

    def test_add_installed_conflicting(self):
        """Adding the same installed pacakge id twice is fine."""
        self.store1.add_installed([1])
        self.store1.add_installed([1])
        self.assertEqual(self.store2.get_installed(), [1])

    def test_add_installed_timing(self):
        """Adding 20k ids must take less than 5 seconds."""
        started = time.time()
        self.store1.add_installed(range(20000))
        self.assertTrue(time.time() - started < 5,
                        "Adding 20k installed ids took more than 5 seconds.")

    def test_remove_installed(self):
        self.store1.add_installed([1, 2, 3, 4])
        self.store1.remove_installed([2, 3])
        self.assertEqual(self.store2.get_installed(), [1, 4])

    def test_remove_installed_timing(self):
        self.store1.add_installed(range(20000))
        started = time.time()
        self.store1.remove_installed(range(20000))
        self.assertTrue(time.time() - started < 5,
                        "Removing 20k installed ids took more than 5 seconds.")

    def test_clear_installed(self):
        self.store1.add_installed([1, 2, 3, 4])
        self.store1.clear_installed()
        self.assertEqual(self.store2.get_installed(), [])

    def test_ensure_package_schema_with_new_tables(self):
        """
        The L{ensure_package_schema} function behaves correctly when new
        tables are added.
        """
        filename = self.makeFile()
        database = sqlite3.connect(filename)
        cursor = database.cursor()
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
        cursor.close()
        database.commit()
        database.close()

        store = PackageStore(filename)
        store.get_locked()

        database = sqlite3.connect(filename)
        cursor = database.cursor()
        cursor.execute("pragma table_info(locked)")
        result = cursor.fetchall()
        self.assertTrue(len(result) > 0)
        cursor.execute("pragma table_info(autoremovable)")
        result = cursor.fetchall()
        self.assertTrue(len(result) > 0)

    def test_add_and_get_locked(self):
        """
        L{PackageStore.add_locked} adds the given ids to the table of locked
        packages and commits the changes.
        """
        self.store1.add_locked([1])
        self.assertEqual(self.store2.get_locked(), [1])

    def test_add_locked_conflicting(self):
        """Adding the same locked pacakge id twice is fine."""
        self.store1.add_locked([1])
        self.store1.add_locked([1])
        self.assertEqual(self.store2.get_locked(), [1])

    def test_remove_locked(self):
        """
        L{PackageStore.removed_locked} remove the given ids from the table
        of locked packages and commits the changes.
        """
        self.store1.add_locked([1, 2, 3, 4])
        self.store1.remove_locked([2, 3])
        self.assertEqual(self.store2.get_locked(), [1, 4])

    def test_remove_locked_non_existing(self):
        """
        Removing non-existing locked packages is fine.
        """
        self.store1.remove_locked([1])
        self.assertEqual(self.store2.get_locked(), [])

    def test_clear_locked(self):
        """
        L{PackageStore.clear_locked} clears the table of locked packages by
        removing all its package ids.
        """
        self.store1.add_locked([1, 2, 3, 4])
        self.store1.clear_locked()
        self.assertEqual(self.store2.get_locked(), [])

    def test_add_hash_id_request(self):
        hashes = ("ha\x00sh1", "ha\x00sh2")
        request1 = self.store1.add_hash_id_request(hashes)
        request2 = self.store2.get_hash_id_request(request1.id)
        self.assertEqual(request1.id, request2.id)
        self.assertEqual(request1.hashes, list(hashes))
        self.assertEqual(request2.hashes, list(hashes))

    def test_iter_hash_id_requests(self):
        hashes1 = ["ha\x00sh1", "ha\x00sh2"]
        hashes2 = ["ha\x00sh3", "ha\x00sh4"]
        self.store1.add_hash_id_request(hashes1)
        self.store1.add_hash_id_request(hashes2)
        hashes = [hash for request in self.store2.iter_hash_id_requests()
                  for hash in request.hashes]
        self.assertEqual(hashes, hashes1 + hashes2)

    def test_get_initial_hash_id_request_timestamp(self):
        with mock.patch("time.time", return_value=123):
            request1 = self.store1.add_hash_id_request(["hash1"])
            request2 = self.store2.get_hash_id_request(request1.id)
        self.assertEqual(123, request2.timestamp)

    def test_update_hash_id_request_timestamp(self):
        request1 = self.store1.add_hash_id_request(["hash1"])
        request2 = self.store2.get_hash_id_request(request1.id)

        request1.timestamp = 456

        self.assertEqual(request2.timestamp, 456)

    def test_default_hash_id_request_message_id(self):
        request = self.store1.add_hash_id_request(["hash1"])
        self.assertEqual(request.message_id, None)

    def test_update_hash_id_request_message_id(self):
        request1 = self.store1.add_hash_id_request(["hash1"])
        request2 = self.store2.get_hash_id_request(request1.id)

        request1.message_id = 456

        self.assertEqual(request2.message_id, 456)

    def test_get_hash_id_request_with_unknown_request_id(self):
        self.assertRaises(UnknownHashIDRequest,
                          self.store1.get_hash_id_request, 123)

    def test_remove_hash_id_request(self):
        request = self.store1.add_hash_id_request(["hash1"])
        request.remove()
        self.assertRaises(UnknownHashIDRequest,
                          self.store1.get_hash_id_request, request.id)

    def test_add_task(self):
        data = {"answer": 42}
        task = self.store1.add_task("reporter", data)
        self.assertEqual(type(task.id), int)
        self.assertEqual(task.queue, "reporter")
        self.assertEqual(task.data, data)

    def test_get_next_task(self):
        task1 = self.store1.add_task("reporter", [1])
        task2 = self.store1.add_task("reporter", [2])
        task3 = self.store1.add_task("changer", [3])

        task = self.store2.get_next_task("reporter")
        self.assertEqual(task.id, task1.id)
        self.assertEqual(task.data, [1])

        task = self.store2.get_next_task("changer")
        self.assertEqual(task.id, task3.id)
        self.assertEqual(task.data, [3])

        task = self.store2.get_next_task("reporter")
        self.assertEqual(task.id, task1.id)
        self.assertEqual(task.data, [1])

        task.remove()

        task = self.store2.get_next_task("reporter")
        self.assertEqual(task.id, task2.id)
        self.assertEqual(task.data, [2])

        task.remove()

        task = self.store2.get_next_task("reporter")
        self.assertEqual(task, None)

    def test_get_task_timestamp(self):
        with mock.patch("time.time", return_value=123):
            self.store1.add_task("reporter", [1])
        task = self.store2.get_next_task("reporter")
        self.assertEqual(123, task.timestamp)

    def test_next_tasks_ordered_by_timestamp(self):
        with mock.patch("time.time", return_value=222):
            self.store1.add_task("reporter", [1])

        with mock.patch("time.time", return_value=111):
            self.store1.add_task("reporter", [2])

        task = self.store2.get_next_task("reporter")
        self.assertEqual(111, task.timestamp)

        task.remove()

        task = self.store2.get_next_task("reporter")
        self.assertEqual(222, task.timestamp)

    def test_clear_hash_id_requests(self):
        request1 = self.store1.add_hash_id_request(["hash1"])
        request2 = self.store1.add_hash_id_request(["hash2"])
        self.store1.clear_hash_id_requests()
        self.assertRaises(UnknownHashIDRequest,
                          self.store1.get_hash_id_request, request1.id)
        self.assertRaises(UnknownHashIDRequest,
                          self.store1.get_hash_id_request, request2.id)

    def test_clear_tasks(self):
        data = {"answer": 42}
        task = self.store1.add_task("reporter", data)
        self.assertEqual(type(task.id), int)
        self.assertEqual(task.queue, "reporter")
        self.assertEqual(task.data, data)
        self.store1.clear_tasks()
        task = self.store2.get_next_task("reporter")
        self.assertEqual(task, None)

    def test_clear_tasks_except_1_task(self):
        data = {"answer": 42}
        task = self.store1.add_task("reporter", data)
        data = {"answer": 43}
        task2 = self.store1.add_task("reporter", data)
        self.store1.clear_tasks(except_tasks=(task2,))
        task = self.store2.get_next_task("reporter")
        self.assertEqual(task.id, task2.id)
        task.remove()
        task = self.store2.get_next_task("reporter")
        self.assertEqual(task, None)

    def test_clear_tasks_except_2_tasks(self):
        data = {"answer": 42}
        task = self.store1.add_task("reporter", data)
        data = {"answer": 43}
        task2 = self.store1.add_task("reporter", data)
        data = {"answer": 44}
        task3 = self.store1.add_task("reporter", data)
        self.store1.clear_tasks(except_tasks=(task2, task3))
        task = self.store2.get_next_task("reporter")
        self.assertEqual(task.id, task2.id)
        task.remove()
        task = self.store2.get_next_task("reporter")
        self.assertEqual(task.id, task3.id)
        task.remove()
        task = self.store2.get_next_task("reporter")
        self.assertEqual(task, None)

    def test_parallel_database_access(self):
        error = []

        def func1():
            func1.store1 = PackageStore(self.filename)
            func1.store1.add_task("reporter", "data")
            func1.store1.add_task("reporter", "data")
            func1.task = func1.store1.get_next_task("reporter")

        def func2():
            func2.store2 = PackageStore(self.filename)
            try:
                func2.store2.add_task("reporter", "data")
            except Exception as e:
                error.append(str(e))

        for func in [func1, func2]:
            thread = threading.Thread(target=func)
            thread.start()
            thread.join()

        self.assertEqual(error, [])
