import threading
import time
import os

from landscape.tests.helpers import LandscapeTest

from landscape.package.store import PackageStore, UnknownHashIDRequest


class PackageStoreTest(LandscapeTest):

    def setUp(self):
        super(PackageStoreTest, self).setUp()

        self.filename = self.makeFile()
        self.store1 = PackageStore(self.filename)
        self.store2 = PackageStore(self.filename)

    def test_wb_transactional_commits(self):
        mock_db = self.mocker.replace(self.store1._db)
        mock_db.commit()
        self.mocker.replay()
        self.store1.set_hash_ids({})

    def test_wb_transactional_rolls_back(self):
        mock_db = self.mocker.replace(self.store1._db)
        mock_db.rollback()
        self.mocker.replay()
        self.assertRaises(Exception, self.store1.set_hash_ids, None)

    def test_set_and_get_hash_id(self):
        self.store1.set_hash_ids({"ha\x00sh1": 123, "ha\x00sh2": 456})
        self.assertEquals(self.store2.get_hash_id("ha\x00sh1"), 123)
        self.assertEquals(self.store2.get_hash_id("ha\x00sh2"), 456)

    def test_get_id_hash(self):
        self.store1.set_hash_ids({"hash1": 123, "hash2": 456})
        self.assertEquals(self.store2.get_id_hash(123), "hash1")
        self.assertEquals(self.store2.get_id_hash(456), "hash2")

    def test_get_hash_id_using_hash_id_dbs(self):

        # Without hash_id dbs
        self.assertEquals(self.store1.get_hash_id("hash1"), None)
        self.assertEquals(self.store1.get_hash_id("hash2"), None)

        def hash_id_db_factory(hash_ids):
            filename = self.makeFile()
            store = PackageStore(filename)
            store.set_hash_ids(hash_ids)
            return filename

        self.store1.add_hash_id_db(hash_id_db_factory({"hash1": 123}))
        self.store1.add_hash_id_db(hash_id_db_factory({"hash2": 456}))

        # With hash_id dbs
        self.assertEquals(self.store1.get_hash_id("hash1"), 123)
        self.assertEquals(self.store1.get_hash_id("hash2"), 456)

    def test_clear_hash_ids(self):
        self.store1.set_hash_ids({"ha\x00sh1": 123, "ha\x00sh2": 456})
        self.store1.clear_hash_ids()
        self.assertEquals(self.store2.get_hash_id("ha\x00sh1"), None)
        self.assertEquals(self.store2.get_hash_id("ha\x00sh2"), None)

    def test_get_unexistent_hash(self):
        self.assertEquals(self.store1.get_hash_id("hash1"), None)

    def test_get_unexistent_id(self):
        self.assertEquals(self.store1.get_id_hash(123), None)

    def test_overwrite_id_hash(self):
        self.store1.set_hash_ids({"hash1": 123})
        self.store2.set_hash_ids({"hash2": 123})
        self.assertEquals(self.store1.get_hash_id("hash1"), None)
        self.assertEquals(self.store1.get_hash_id("hash2"), 123)

    def test_overwrite_hash_id(self):
        self.store1.set_hash_ids({"hash1": 123})
        self.store2.set_hash_ids({"hash1": 456})
        self.assertEquals(self.store1.get_id_hash(123), None)
        self.assertEquals(self.store1.get_id_hash(456), "hash1")

    def test_set_hash_ids_timing(self):
        """Setting 20k hashes must take less than 5 seconds."""
        hashes = dict((str(i), i) for i in range(20000))
        started = time.time()
        self.store1.set_hash_ids(hashes)
        self.assertTrue(time.time()-started < 5,
                        "Setting 20k hashes took more than 5 seconds.")

    def test_add_and_get_available_packages(self):
        self.store1.add_available([1, 2])
        self.assertEquals(self.store2.get_available(), [1, 2])

    def test_add_available_conflicting(self):
        """Adding the same available pacakge id twice is fine."""
        self.store1.add_available([1])
        self.store1.add_available([1])
        self.assertEquals(self.store2.get_available(), [1])

    def test_add_available_timing(self):
        """Adding 20k ids must take less than 5 seconds."""
        started = time.time()
        self.store1.add_available(range(20000))
        self.assertTrue(time.time()-started < 5,
                        "Adding 20k available ids took more than 5 seconds.")

    def test_remove_available(self):
        self.store1.add_available([1, 2, 3, 4])
        self.store1.remove_available([2, 3])
        self.assertEquals(self.store2.get_available(), [1, 4])

    def test_remove_available_timing(self):
        self.store1.add_available(range(20000))
        started = time.time()
        self.store1.remove_available(range(20000))
        self.assertTrue(time.time()-started < 5,
                        "Removing 20k available ids took more than 5 seconds.")

    def test_clear_available(self):
        self.store1.add_available([1, 2, 3, 4])
        self.store1.clear_available()
        self.assertEquals(self.store2.get_available(), [])

    def test_add_and_get_available_upgrades_packages(self):
        self.store1.add_available_upgrades([1, 2])
        self.assertEquals(self.store2.get_available_upgrades(), [1, 2])

    def test_add_available_upgrades_conflicting(self):
        """Adding the same available_upgrades pacakge id twice is fine."""
        self.store1.add_available_upgrades([1])
        self.store1.add_available_upgrades([1])
        self.assertEquals(self.store2.get_available_upgrades(), [1])

    def test_add_available_upgrades_timing(self):
        """Adding 20k ids must take less than 5 seconds."""
        started = time.time()
        self.store1.add_available_upgrades(range(20000))
        self.assertTrue(time.time()-started < 5,
                        "Adding 20k available upgrades ids took "
                        "more than 5 seconds.")

    def test_remove_available_upgrades(self):
        self.store1.add_available_upgrades([1, 2, 3, 4])
        self.store1.remove_available_upgrades([2, 3])
        self.assertEquals(self.store2.get_available_upgrades(), [1, 4])

    def test_remove_available_upgrades_timing(self):
        self.store1.add_available_upgrades(range(20000))
        started = time.time()
        self.store1.remove_available_upgrades(range(20000))
        self.assertTrue(time.time()-started < 5,
                        "Removing 20k available upgrades ids took "
                        "more than 5 seconds.")

    def test_clear_available_upgrades(self):
        self.store1.add_available_upgrades([1, 2, 3, 4])
        self.store1.clear_available_upgrades()
        self.assertEquals(self.store2.get_available_upgrades(), [])

    def test_add_and_get_installed_packages(self):
        self.store1.add_installed([1, 2])
        self.assertEquals(self.store2.get_installed(), [1, 2])

    def test_add_installed_conflicting(self):
        """Adding the same installed pacakge id twice is fine."""
        self.store1.add_installed([1])
        self.store1.add_installed([1])
        self.assertEquals(self.store2.get_installed(), [1])

    def test_add_installed_timing(self):
        """Adding 20k ids must take less than 5 seconds."""
        started = time.time()
        self.store1.add_installed(range(20000))
        self.assertTrue(time.time()-started < 5,
                        "Adding 20k installed ids took more than 5 seconds.")

    def test_remove_installed(self):
        self.store1.add_installed([1, 2, 3, 4])
        self.store1.remove_installed([2, 3])
        self.assertEquals(self.store2.get_installed(), [1, 4])

    def test_remove_installed_timing(self):
        self.store1.add_installed(range(20000))
        started = time.time()
        self.store1.remove_installed(range(20000))
        self.assertTrue(time.time()-started < 5,
                        "Removing 20k installed ids took more than 5 seconds.")

    def test_clear_installed(self):
        self.store1.add_installed([1, 2, 3, 4])
        self.store1.clear_installed()
        self.assertEquals(self.store2.get_installed(), [])

    def test_add_hash_id_request(self):
        hashes = ("ha\x00sh1", "ha\x00sh2")
        request1 = self.store1.add_hash_id_request(hashes)
        request2 = self.store2.get_hash_id_request(request1.id)
        self.assertEquals(request1.id, request2.id)
        self.assertEquals(request1.hashes, list(hashes))
        self.assertEquals(request2.hashes, list(hashes))

    def test_iter_hash_id_requests(self):
        hashes1 = ["ha\x00sh1", "ha\x00sh2"]
        hashes2 = ["ha\x00sh3", "ha\x00sh4"]
        request1 = self.store1.add_hash_id_request(hashes1)
        request2 = self.store1.add_hash_id_request(hashes2)
        hashes = [hash for request in self.store2.iter_hash_id_requests()
                       for hash in request.hashes]
        self.assertEquals(hashes, hashes1 + hashes2)

    def test_get_initial_hash_id_request_timestamp(self):
        time_mock = self.mocker.replace("time.time")
        time_mock()
        self.mocker.result(123)
        self.mocker.replay()

        try:
            request1 = self.store1.add_hash_id_request(["hash1"])
            request2 = self.store2.get_hash_id_request(request1.id)

            self.assertEquals(request2.timestamp, 123)

            # We handle mocker explicitly so that our hacked time()
            # won't break Twisted's internals.
            self.mocker.verify()
        finally:
            self.mocker.reset()

    def test_update_hash_id_request_timestamp(self):
        request1 = self.store1.add_hash_id_request(["hash1"])
        request2 = self.store2.get_hash_id_request(request1.id)

        request1.timestamp = 456

        self.assertEquals(request2.timestamp, 456)

    def test_default_hash_id_request_message_id(self):
        request = self.store1.add_hash_id_request(["hash1"])
        self.assertEquals(request.message_id, None)

    def test_update_hash_id_request_message_id(self):
        request1 = self.store1.add_hash_id_request(["hash1"])
        request2 = self.store2.get_hash_id_request(request1.id)

        request1.message_id = 456

        self.assertEquals(request2.message_id, 456)

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
        self.assertEquals(type(task.id), int)
        self.assertEquals(task.queue, "reporter")
        self.assertEquals(task.data, data)

    def test_get_next_task(self):
        task1 = self.store1.add_task("reporter", [1])
        task2 = self.store1.add_task("reporter", [2])
        task3 = self.store1.add_task("changer", [3])

        task = self.store2.get_next_task("reporter")
        self.assertEquals(task.id, task1.id)
        self.assertEquals(task.data, [1])

        task = self.store2.get_next_task("changer")
        self.assertEquals(task.id, task3.id)
        self.assertEquals(task.data, [3])

        task = self.store2.get_next_task("reporter")
        self.assertEquals(task.id, task1.id)
        self.assertEquals(task.data, [1])

        task.remove()

        task = self.store2.get_next_task("reporter")
        self.assertEquals(task.id, task2.id)
        self.assertEquals(task.data, [2])

        task.remove()

        task = self.store2.get_next_task("reporter")
        self.assertEquals(task, None)

    def test_get_task_timestamp(self):
        time_mock = self.mocker.replace("time.time")
        time_mock()
        self.mocker.result(123)
        self.mocker.replay()

        try:
            self.store1.add_task("reporter", [1])
            task = self.store2.get_next_task("reporter")

            self.assertEquals(task.timestamp, 123)

            # We handle mocker explicitly so that our hacked time()
            # won't break Twisted's internals.
            self.mocker.verify()
        finally:
            self.mocker.reset()

    def test_next_tasks_ordered_by_timestamp(self):
        time_mock = self.mocker.replace("time.time")
        time_mock()
        self.mocker.result(222)
        time_mock()
        self.mocker.result(111)
        self.mocker.replay()

        try:
            task1 = self.store1.add_task("reporter", [1])
            task2 = self.store1.add_task("reporter", [2])

            task = self.store2.get_next_task("reporter")
            self.assertEquals(task.timestamp, 111)

            task.remove()

            task = self.store2.get_next_task("reporter")
            self.assertEquals(task.timestamp, 222)

            # We handle mocker explicitly so that our hacked time()
            # won't break Twisted's internals.
            self.mocker.verify()
        finally:
            self.mocker.reset()

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
        self.assertEquals(type(task.id), int)
        self.assertEquals(task.queue, "reporter")
        self.assertEquals(task.data, data)
        self.store1.clear_tasks()
        task = self.store2.get_next_task("reporter")
        self.assertEquals(task, None)

    def test_clear_tasks_except_1_task(self):
        data = {"answer": 42}
        task = self.store1.add_task("reporter", data)
        data = {"answer": 43}
        task2 = self.store1.add_task("reporter", data)
        self.store1.clear_tasks(except_tasks=(task2,))
        task = self.store2.get_next_task("reporter")
        self.assertEquals(task.id, task2.id)
        task.remove()
        task = self.store2.get_next_task("reporter")
        self.assertEquals(task, None)

    def test_clear_tasks_except_2_tasks(self):
        data = {"answer": 42}
        task = self.store1.add_task("reporter", data)
        data = {"answer": 43}
        task2 = self.store1.add_task("reporter", data)
        data = {"answer": 44}
        task3 = self.store1.add_task("reporter", data)
        self.store1.clear_tasks(except_tasks=(task2, task3))
        task = self.store2.get_next_task("reporter")
        self.assertEquals(task.id, task2.id)
        task.remove()
        task = self.store2.get_next_task("reporter")
        self.assertEquals(task.id, task3.id)
        task.remove()
        task = self.store2.get_next_task("reporter")
        self.assertEquals(task, None)

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
            except Exception, e:
                error.append(str(e))

        for func in [func1, func2]:
            thread = threading.Thread(target=func)
            thread.start()
            thread.join()

        self.assertEquals(error, [])

