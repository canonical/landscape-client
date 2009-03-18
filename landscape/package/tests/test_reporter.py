import glob
import sys
import os

from twisted.internet.defer import Deferred

from landscape.lib.lock import lock_path
from landscape.lib.fetch import FetchError
from landscape.lib.command import CommandError

from landscape.package.store import PackageStore, UnknownHashIDRequest
from landscape.package.reporter import (
    PackageReporter, HASH_ID_REQUEST_TIMEOUT, main, find_reporter_command)
from landscape.package import reporter
from landscape.package.facade import SmartFacade

from landscape.deployment import Configuration
from landscape.broker.remote import RemoteBroker

from landscape.package.tests.helpers import (
    SmartFacadeHelper, HASH1, HASH2, HASH3)

from landscape.tests.helpers import (
    LandscapeIsolatedTest, RemoteBrokerHelper)
from landscape.tests.mocker import ANY


class PackageReporterTest(LandscapeIsolatedTest):

    helpers = [SmartFacadeHelper, RemoteBrokerHelper]

    def setUp(self):
        super(PackageReporterTest, self).setUp()

        self.store = PackageStore(self.makeFile())
        self.config = Configuration()
        self.reporter = PackageReporter(self.store, self.facade, self.remote, self.config)

    def set_pkg2_upgrades_pkg1(self):
        previous = self.Facade.channels_reloaded
        def callback(self):
            from smart.backends.deb.base import DebUpgrades
            previous(self)
            pkg2 = self.get_packages_by_name("name2")[0]
            pkg2.upgrades += (DebUpgrades("name1", "=", "version1-release1"),)
            self.reload_cache() # Relink relations.
        self.Facade.channels_reloaded = callback

    def set_pkg1_installed(self):
        previous = self.Facade.channels_reloaded
        def callback(self):
            previous(self)
            self.get_packages_by_name("name1")[0].installed = True
        self.Facade.channels_reloaded = callback

    def test_set_package_ids_with_all_known(self):
        request1 = self.store.add_hash_id_request(["hash1", "hash2"])
        request2 = self.store.add_hash_id_request(["hash3", "hash4"])
        request3 = self.store.add_hash_id_request(["hash5", "hash6"])

        self.store.add_task("reporter",
                            {"type": "package-ids", "ids": [123, 456],
                             "request-id": request2.id})

        def got_result(result):
            self.assertEquals(self.store.get_hash_id("hash1"), None)
            self.assertEquals(self.store.get_hash_id("hash2"), None)
            self.assertEquals(self.store.get_hash_id("hash3"), 123)
            self.assertEquals(self.store.get_hash_id("hash4"), 456)
            self.assertEquals(self.store.get_hash_id("hash5"), None)
            self.assertEquals(self.store.get_hash_id("hash6"), None)

        deferred = self.reporter.handle_tasks()
        return deferred.addCallback(got_result)

    def test_set_package_ids_with_unknown_request_id(self):

        self.store.add_task("reporter",
                            {"type": "package-ids", "ids": [123, 456],
                             "request-id": 123})

        # Nothing bad should happen.
        return self.reporter.handle_tasks()

    def test_set_package_ids_with_unknown_hashes(self):
        message_store = self.broker_service.message_store

        message_store.set_accepted_types(["add-packages"])

        request1 = self.store.add_hash_id_request(["foo", HASH1, "bar"])

        self.store.add_task("reporter",
                            {"type": "package-ids",
                             "ids": [123, None, 456],
                             "request-id": request1.id})

        def got_result(result):
            message = message_store.get_pending_messages()[0]

            # The server will answer the "add-packages" message with a
            # "package-ids" message, so we must keep track of the hashes
            # for packages sent.
            request2 = self.store.get_hash_id_request(message["request-id"])
            self.assertEquals(request2.hashes, [HASH1])

            # Keeping track of the message id for the message with the
            # package data allows us to tell if we should consider our
            # request as lost for some reason, and thus re-request it.
            message_id = request2.message_id
            self.assertEquals(type(message_id), int)

            self.assertTrue(message_store.is_pending(message_id))

            self.assertMessages(message_store.get_pending_messages(),
                [{"packages": [{"description": u"Description1",
                                "installed-size": 28672,
                                "name": u"name1",
                                "relations":
                                    [(131074, u"providesname1"),
                                     (196610, u"name1 = version1-release1"),
                                     (262148,
                                      u"prerequirename1 = prerequireversion1"),
                                     (262148, u"requirename1 = requireversion1"),
                                     (393224, u"name1 < version1-release1"),
                                     (458768,
                                      u"conflictsname1 = conflictsversion1")],
                                "section": u"Group1",
                                "size": 1038,
                                "summary": u"Summary1",
                                "type": 65537,
                                "version": u"version1-release1"}],
                                "request-id": request2.id,
                  "type": "add-packages"}])

        deferred = self.reporter.handle_tasks()
        return deferred.addCallback(got_result)

    def test_set_package_ids_with_unknown_hashes_and_size_none(self):
        message_store = self.broker_service.message_store

        message_store.set_accepted_types(["add-packages"])

        request1 = self.store.add_hash_id_request(["foo", HASH1, "bar"])

        self.store.add_task("reporter",
                            {"type": "package-ids",
                             "ids": [123, None, 456],
                             "request-id": request1.id})

        def got_result(result):
            message = message_store.get_pending_messages()[0]
            request2 = self.store.get_hash_id_request(message["request-id"])
            self.assertMessages(message_store.get_pending_messages(),
                [{"packages": [{"description": u"Description1",
                                "installed-size": None,
                                "name": u"name1",
                                "relations": [],
                                "section": u"Group1",
                                "size": None,
                                "summary": u"Summary1",
                                "type": 65537,
                                "version": u"version1-release1"}],
                                "request-id": request2.id,
                  "type": "add-packages"}])


        class FakePackage(object):
            type = 65537
            name = u"name1"
            version = u"version1-release1"
            section = u"Group1"
            summary = u"Summary1"
            description = u"Description1"
            size = None
            installed_size = None
            relations = []

        mock_facade = self.mocker.patch(SmartFacade)
        mock_facade.get_package_skeleton(ANY)
        self.mocker.result(FakePackage())
        self.mocker.replay()
        deferred = self.reporter.handle_tasks()
        return deferred.addCallback(got_result)

    def test_set_package_ids_with_unknown_hashes_and_failed_send_msg(self):
        message_store = self.broker_service.message_store
        message_store.set_accepted_types(["add-packages"])

        class Boom(Exception): pass
        deferred = Deferred()
        deferred.errback(Boom())

        remote_mock = self.mocker.patch(RemoteBroker)
        remote_mock.send_message(ANY, True)
        self.mocker.result(deferred)
        self.mocker.replay()

        request_id = self.store.add_hash_id_request(["foo", HASH1, "bar"]).id

        self.store.add_task("reporter", {"type": "package-ids",
                                         "ids": [123, None, 456],
                                         "request-id": request_id})

        def got_result(result):
            self.assertMessages(message_store.get_pending_messages(), [])
            self.assertEquals([request.id for request in
                               self.store.iter_hash_id_requests()],
                              [request_id])

        result = self.reporter.handle_tasks()
        self.assertFailure(result, Boom)
        return result.addCallback(got_result)

    def test_set_package_ids_removes_request_id_when_done(self):
        request = self.store.add_hash_id_request(["hash1"])
        self.store.add_task("reporter", {"type": "package-ids", "ids": [123],
                                         "request-id": request.id})

        def got_result(result):
            self.assertRaises(UnknownHashIDRequest,
                              self.store.get_hash_id_request, request.id)

        deferred = self.reporter.handle_tasks()
        return deferred.addCallback(got_result)

    def test_fetch_hash_id_db(self):

        # Assume package_hash_id_url is set
        self.config.data_path = self.makeDir()
        self.config.package_hash_id_url = "http://fake.url/path/"
        os.makedirs(os.path.join(self.config.data_path, "package/hash-id"))
        hash_id_db_filename = os.path.join(self.config.data_path,
                                          "package/hash-id",
                                          "uuid_codename_arch")

        # Fake uuid, codename and arch
        message_store = self.broker_service.message_store
        message_store.set_server_uuid("uuid")
        command_mock = self.mocker.replace("landscape.lib.command.run_command")
        command_mock("lsb_release -cs")
        self.mocker.result("codename")
        command_mock("dpkg --print-architecture")
        self.mocker.result("arch")

        # Let's say fetch_async is successful
        hash_id_db_url = self.config.package_hash_id_url + "uuid_codename_arch"
        fetch_async_mock = self.mocker.replace("landscape.lib.fetch.fetch_async")
        fetch_async_mock(hash_id_db_url)
        fetch_async_result = Deferred()
        fetch_async_result.callback("hash-ids")
        self.mocker.result(fetch_async_result)

        # The download should be properly logged
        logging_mock = self.mocker.replace("logging.info")
        logging_mock("Downloaded hash=>id database from %s" % hash_id_db_url)
        self.mocker.result(None)

        # We don't have our hash=>id database yet
        self.assertFalse(os.path.exists(hash_id_db_filename))

        # Now go!
        self.mocker.replay()
        result = self.reporter.fetch_hash_id_db()

        # Check the database
        def callback(ignored):
            self.assertTrue(os.path.exists(hash_id_db_filename))
            self.assertEquals(open(hash_id_db_filename).read(), "hash-ids")
        result.addCallback(callback)

        return result

    def test_fetch_hash_id_db_does_not_download_twice(self):

        # Let's say that the hash=>id database is already there
        self.config.data_path = self.makeDir()
        os.makedirs(os.path.join(self.config.data_path, "package/hash-id"))
        hash_id_db_filename = os.path.join(self.config.data_path,
                                          "package/hash-id",
                                          "uuid_codename_arch")
        open(hash_id_db_filename, "w").write("test")

        # Fake uuid, codename and arch
        message_store = self.broker_service.message_store
        message_store.set_server_uuid("uuid")
        command_mock = self.mocker.replace("landscape.lib.command.run_command")
        command_mock("lsb_release -cs")
        self.mocker.result("codename")
        command_mock("dpkg --print-architecture")
        self.mocker.result("arch")

        # Go!
        self.mocker.replay()
        result = self.reporter.fetch_hash_id_db()

        # Same database still there
        def callback(ignored):
            self.assertEquals(open(hash_id_db_filename).read(), "test")
        result.addCallback(callback)

        return result

    def test_fetch_hash_id_db_undetermined_codename(self):

        # Fake uuid
        message_store = self.broker_service.message_store
        message_store.set_server_uuid("uuid")

        # Undetermined codename
        command_mock = self.mocker.replace("landscape.lib.command.run_command")
        command_mock("lsb_release -cs")
        command_error = CommandError("lsb_release -cs", 1, "error")
        self.mocker.throw(command_error)

        # The failure should be properly logged
        logging_mock = self.mocker.replace("logging.warning")
        logging_mock("Couldn't determine which hash=>id database to use: %s" %
                     str(command_error))
        self.mocker.result(None)

        # Go!
        self.mocker.replay()
        result = self.reporter.fetch_hash_id_db()

        return result

    def test_fetch_hash_id_db_undetermined_arch(self):

        # Fake uuid and codename
        message_store = self.broker_service.message_store
        message_store.set_server_uuid("uuid")
        command_mock = self.mocker.replace("landscape.lib.command.run_command")
        command_mock("lsb_release -cs")
        self.mocker.result("codename")

        # Undetermined arch
        command_mock("dpkg --print-architecture")
        command_error = CommandError("dpkg --print-architecture", 1, "error")
        self.mocker.throw(command_error)

        # The failure should be properly logged
        logging_mock = self.mocker.replace("logging.warning")
        logging_mock("Couldn't determine which hash=>id database to use: %s" %
                     str(command_error))
        self.mocker.result(None)

        # Go!
        self.mocker.replay()
        result = self.reporter.fetch_hash_id_db()

        return result

    def test_fetch_hash_id_db_with_default_url(self):

        # Let's say package_hash_id_url is not set but url is
        self.config.data_path = self.makeDir()
        self.config.package_hash_id_url = None
        self.config.url = "http://fake.url/path/message-system/"
        os.makedirs(os.path.join(self.config.data_path, "package/hash-id"))
        hash_id_db_filename = os.path.join(self.config.data_path,
                                          "package/hash-id",
                                          "uuid_codename_arch")

        # Fake uuid, codename and arch
        message_store = self.broker_service.message_store
        message_store.set_server_uuid("uuid")
        command_mock = self.mocker.replace("landscape.lib.command.run_command")
        command_mock("lsb_release -cs")
        self.mocker.result("codename")
        command_mock("dpkg --print-architecture")
        self.mocker.result("arch")

        # Check fetch_async is called with the default url
        hash_id_db_url = "http://fake.url/path/hash-id-databases/" \
                         "uuid_codename_arch"
        fetch_async_mock = self.mocker.replace("landscape.lib.fetch.fetch_async")
        fetch_async_mock(hash_id_db_url)
        fetch_async_result = Deferred()
        fetch_async_result.callback("hash-ids")
        self.mocker.result(fetch_async_result)

        # Now go!
        self.mocker.replay()
        result = self.reporter.fetch_hash_id_db()

        # Check the database
        def callback(ignored):
            self.assertTrue(os.path.exists(hash_id_db_filename))
            self.assertEquals(open(hash_id_db_filename).read(), "hash-ids")
        result.addCallback(callback)
        return result

    def test_fetch_hash_id_db_with_undetermined_url(self):

        # We have no way to guess the url
        self.config.data_path = self.makeDir()
        self.config.package_hash_id_url = None
        self.config.url = None

        # Fake uuid, codename and arch
        message_store = self.broker_service.message_store
        message_store.set_server_uuid("uuid")
        command_mock = self.mocker.replace("landscape.lib.command.run_command")
        command_mock("lsb_release -cs")
        self.mocker.result("codename")
        command_mock("dpkg --print-architecture")
        self.mocker.result("arch")

        # The failure should be properly logged
        logging_mock = self.mocker.replace("logging.warning")
        logging_mock("Can't determine the hash=>id database url")
        self.mocker.result(None)

        # Now go!
        self.mocker.replay()
        result = self.reporter.fetch_hash_id_db()

        return result

    def test_fetch_hash_id_db_with_download_error(self):

        # Assume package_hash_id_url is set
        self.config.data_path = self.makeDir()
        self.config.package_hash_id_url = "http://fake.url/path/"

        # Fake uuid, codename and arch
        message_store = self.broker_service.message_store
        message_store.set_server_uuid("uuid")
        command_mock = self.mocker.replace("landscape.lib.command.run_command")
        command_mock("lsb_release -cs")
        self.mocker.result("codename")
        command_mock("dpkg --print-architecture")
        self.mocker.result("arch")

        # Let's say fetch_async fails
        hash_id_db_url = self.config.package_hash_id_url + "uuid_codename_arch"
        fetch_async_mock = self.mocker.replace("landscape.lib.fetch.fetch_async")
        fetch_async_mock(hash_id_db_url)
        fetch_async_result = Deferred()
        fetch_async_result.errback(FetchError("fetch error"))
        self.mocker.result(fetch_async_result)

        # The failure should be properly logged
        logging_mock = self.mocker.replace("logging.warning")
        logging_mock("Couldn't download hash=>id database: fetch error")
        self.mocker.result(None)

        # Now go!
        self.mocker.replay()
        result = self.reporter.fetch_hash_id_db()

        # We shouldn't have any hash=>id database
        def callback(ignored):
            hash_id_db_filename = os.path.join(self.config.data_path,
                                               "package/hash-id",
                                               "uuid_codename_arch")
            self.assertEquals(os.path.exists(hash_id_db_filename), False)
        result.addCallback(callback)

        return result

    def test_fetch_hash_id_db_with_undetermined_url(self):

        # We don't know where to fetch the hash=>id database from
        self.config.url = None
        self.config.package_hash_id_url = None

        # Fake uuid, codename and arch
        remote_mock = self.mocker.patch(RemoteBroker)
        remote_mock.get_server_uuid()
        uuid_result = Deferred()
        uuid_result.callback("uuid")
        self.mocker.result(uuid_result)

        command_mock = self.mocker.replace("landscape.lib.command.run_command")
        command_mock("lsb_release -cs")
        self.mocker.result("codename")
        command_mock("dpkg --print-architecture")
        self.mocker.result("arch")
 
        # The failure should be properly logged
        logging_mock = self.mocker.replace("logging.warning")
        logging_mock("Can't determine the hash=>id database url")
        self.mocker.result(None)

        # Let's go
        self.mocker.replay()

        result = self.reporter.fetch_hash_id_db()
 
        # We shouldn't have any hash=>id database
        def callback(ignored):
            hash_id_db_filename = os.path.join(self.config.data_path,
                                               "package/hash-id",
                                               "uuid_codename_arch")
            self.assertEquals(os.path.exists(hash_id_db_filename), False)
        result.addCallback(callback)

        return result

    def test_remove_expired_hash_id_request(self):
        request = self.store.add_hash_id_request(["hash1"])
        request.message_id = 9999

        request.timestamp -= HASH_ID_REQUEST_TIMEOUT

        def got_result(result):
            self.assertRaises(UnknownHashIDRequest,
                              self.store.get_hash_id_request, request.id)

        result = self.reporter.remove_expired_hash_id_requests()
        return result.addCallback(got_result)

    def test_remove_expired_hash_id_request_wont_remove_before_timeout(self):
        request1 = self.store.add_hash_id_request(["hash1"])
        request1.message_id = 9999
        request1.timestamp -= HASH_ID_REQUEST_TIMEOUT / 2

        initial_timestamp = request1.timestamp

        def got_result(result):
            request2 = self.store.get_hash_id_request(request1.id)
            self.assertTrue(request2)

            # Shouldn't update timestamp when already delivered.
            self.assertEquals(request2.timestamp, initial_timestamp)

        result = self.reporter.remove_expired_hash_id_requests()
        return result.addCallback(got_result)

    def test_remove_expired_hash_id_request_updates_timestamps(self):
        request = self.store.add_hash_id_request(["hash1"])
        message_store = self.broker_service.message_store
        message_id = message_store.add({"type": "add-packages",
                                        "packages": [],
                                        "request-id": request.id})
        request.message_id = message_id
        initial_timestamp = request.timestamp

        def got_result(result):
            self.assertTrue(request.timestamp > initial_timestamp)

        result = self.reporter.remove_expired_hash_id_requests()
        return result.addCallback(got_result)

    def test_remove_expired_hash_id_request_removes_when_no_message_id(self):
        request = self.store.add_hash_id_request(["hash1"])

        def got_result(result):
            self.assertRaises(UnknownHashIDRequest,
                              self.store.get_hash_id_request, request.id)

        result = self.reporter.remove_expired_hash_id_requests()
        return result.addCallback(got_result)

    def test_request_unknown_hashes(self):
        self.store.set_hash_ids({HASH2: 123})

        message_store = self.broker_service.message_store
        message_store.set_accepted_types(["unknown-package-hashes"])

        def got_result(result):
            self.assertMessages(message_store.get_pending_messages(),
                                [{"hashes": EqualsHashes(HASH1, HASH3),
                                  "request-id": 1,
                                  "type": "unknown-package-hashes"}])

            message = message_store.get_pending_messages()[0]

            request = self.store.get_hash_id_request(1)
            self.assertEquals(request.hashes, message["hashes"])

            self.assertTrue(message_store.is_pending(request.message_id))

        result = self.reporter.request_unknown_hashes()
        return result.addCallback(got_result)

    def test_request_unknown_hashes_limits_number_of_packages(self):
        message_store = self.broker_service.message_store
        message_store.set_accepted_types(["unknown-package-hashes"])

        self.addCleanup(setattr, reporter, "MAX_UNKNOWN_HASHES_PER_REQUEST",
                        reporter.MAX_UNKNOWN_HASHES_PER_REQUEST)

        reporter.MAX_UNKNOWN_HASHES_PER_REQUEST = 2

        def got_result1(result):
            # The first message sent should send any 2 of the 3 hashes.
            self.assertEquals(len(message_store.get_pending_messages()), 1)
            message = message_store.get_pending_messages()[-1]
            self.assertEquals(len(message["hashes"]), 2)

            result2 = self.reporter.request_unknown_hashes()
            result2.addCallback(got_result2, message["hashes"])

            return result2

        def got_result2(result, hashes):
            # The second message sent should send the missing hash.
            self.assertEquals(len(message_store.get_pending_messages()), 2)
            message = message_store.get_pending_messages()[-1]
            self.assertEquals(len(message["hashes"]), 1)
            self.assertNotIn(message["hashes"][0], hashes)

        result1 = self.reporter.request_unknown_hashes()
        result1.addCallback(got_result1)

        return result1

    def test_request_unknown_hashes_with_previously_requested(self):
        """
        In this test we'll pretend that a couple of hashes were
        previously requested, and there's one new hash to be requested.
        """
        message_store = self.broker_service.message_store
        message_store.set_accepted_types(["unknown-package-hashes"])

        self.store.add_hash_id_request([HASH1, HASH3])

        def got_result(result):
            self.assertMessages(message_store.get_pending_messages(),
                                [{"hashes": [HASH2],
                                  "request-id": 2,
                                  "type": "unknown-package-hashes"}])

            message = message_store.get_pending_messages()[0]

            request = self.store.get_hash_id_request(2)
            self.assertEquals(request.hashes, message["hashes"])

            self.assertTrue(message_store.is_pending(request.message_id))

        result = self.reporter.request_unknown_hashes()
        return result.addCallback(got_result)

    def test_request_unknown_hashes_with_all_previously_requested(self):
        message_store = self.broker_service.message_store
        message_store.set_accepted_types(["unknown-package-hashes"])

        self.store.add_hash_id_request([HASH1, HASH2, HASH3])

        def got_result(result):
            self.assertMessages(message_store.get_pending_messages(), [])

        result = self.reporter.request_unknown_hashes()
        return result.addCallback(got_result)

    def test_request_unknown_hashes_with_failing_send_message(self):
        """
        When broker.send_message() fails, the hash_id_request shouldn't
        even be stored, because we have no message_id.
        """
        message_store = self.broker_service.message_store
        message_store.set_accepted_types(["unknown-package-hashes"])

        class Boom(Exception): pass
        deferred = Deferred()
        deferred.errback(Boom())

        remote_mock = self.mocker.patch(RemoteBroker)
        remote_mock.send_message(ANY, True)
        self.mocker.result(deferred)
        self.mocker.replay()

        def got_result(result):
            self.assertMessages(message_store.get_pending_messages(), [])
            self.assertEquals(list(self.store.iter_hash_id_requests()), [])

        result = self.reporter.request_unknown_hashes()

        self.assertFailure(result, Boom)

        return result.addCallback(got_result)

    def test_detect_changes_with_available(self):
        message_store = self.broker_service.message_store
        message_store.set_accepted_types(["packages"])

        self.store.set_hash_ids({HASH1: 1, HASH2: 2, HASH3: 3})

        def got_result(result):
            self.assertMessages(message_store.get_pending_messages(),
                                [{"type": "packages", "available": [(1, 3)]}])

            self.assertEquals(sorted(self.store.get_available()), [1, 2, 3])

        result = self.reporter.detect_changes()
        return result.addCallback(got_result)

    def test_detect_changes_with_available_and_unknown_hash(self):
        message_store = self.broker_service.message_store
        message_store.set_accepted_types(["packages"])

        self.store.set_hash_ids({HASH1: 1, HASH3: 3})

        def got_result(result):
            self.assertMessages(message_store.get_pending_messages(),
                                [{"type": "packages", "available": [1, 3]}])

            self.assertEquals(sorted(self.store.get_available()), [1, 3])

        result = self.reporter.detect_changes()
        return result.addCallback(got_result)

    def test_detect_changes_with_available_and_previously_known(self):
        message_store = self.broker_service.message_store
        message_store.set_accepted_types(["packages"])

        self.store.set_hash_ids({HASH1: 1, HASH2: 2, HASH3: 3})
        self.store.add_available([1, 3])

        def got_result(result):
            self.assertMessages(message_store.get_pending_messages(),
                                [{"type": "packages", "available": [2]}])

            self.assertEquals(sorted(self.store.get_available()), [1, 2, 3])

        result = self.reporter.detect_changes()
        return result.addCallback(got_result)

    def test_detect_changes_with_not_available(self):
        message_store = self.broker_service.message_store
        message_store.set_accepted_types(["packages"])

        for filename in glob.glob(self.repository_dir + "/*"):
            os.unlink(filename)

        self.store.set_hash_ids({HASH1: 1, HASH2: 2, HASH3: 3})
        self.store.add_available([1, 2, 3])

        def got_result(result):
            self.assertMessages(message_store.get_pending_messages(),
                                [{"type": "packages",
                                  "not-available": [(1, 3)]}])

            self.assertEquals(sorted(self.store.get_available()), [])

        result = self.reporter.detect_changes()
        return result.addCallback(got_result)

    def test_detect_changes_with_installed(self):
        message_store = self.broker_service.message_store
        message_store.set_accepted_types(["packages"])

        self.store.set_hash_ids({HASH1: 1, HASH2: 2, HASH3: 3})
        self.store.add_available([1, 2, 3])

        self.set_pkg1_installed()

        def got_result(result):
            self.assertMessages(message_store.get_pending_messages(),
                                [{"type": "packages", "installed": [1]}])

            self.assertEquals(sorted(self.store.get_installed()), [1])

        result = self.reporter.detect_changes()
        return result.addCallback(got_result)

    def test_detect_changes_with_installed_already_known(self):
        message_store = self.broker_service.message_store
        message_store.set_accepted_types(["packages"])

        self.store.set_hash_ids({HASH1: 1, HASH2: 2, HASH3: 3})
        self.store.add_available([1, 2, 3])
        self.store.add_installed([1])

        self.set_pkg1_installed()

        def got_result(result):
            self.assertMessages(message_store.get_pending_messages(), [])

        result = self.reporter.detect_changes()
        return result.addCallback(got_result)

    def test_detect_changes_with_not_installed(self):
        message_store = self.broker_service.message_store
        message_store.set_accepted_types(["packages"])

        self.store.set_hash_ids({HASH1: 1, HASH2: 2, HASH3: 3})
        self.store.add_available([1, 2, 3])
        self.store.add_installed([1])

        def got_result(result):
            self.assertMessages(message_store.get_pending_messages(),
                                [{"type": "packages", "not-installed": [1]}])

            self.assertEquals(sorted(self.store.get_installed()), [])

        result = self.reporter.detect_changes()
        return result.addCallback(got_result)

    def test_detect_changes_with_upgrade_but_not_installed(self):
        message_store = self.broker_service.message_store
        message_store.set_accepted_types(["packages"])

        self.store.set_hash_ids({HASH1: 1, HASH2: 2, HASH3: 3})
        self.store.add_available([1, 2, 3])

        self.set_pkg2_upgrades_pkg1()

        def got_result(result):
            self.assertMessages(message_store.get_pending_messages(), [])

        result = self.reporter.detect_changes()
        return result.addCallback(got_result)

    def test_detect_changes_with_upgrade(self):
        message_store = self.broker_service.message_store
        message_store.set_accepted_types(["packages"])

        self.store.set_hash_ids({HASH1: 1, HASH2: 2, HASH3: 3})
        self.store.add_available([1, 2, 3])
        self.store.add_installed([1])

        self.set_pkg2_upgrades_pkg1()
        self.set_pkg1_installed()

        def got_result(result):
            self.assertMessages(message_store.get_pending_messages(),
                                [{"type": "packages",
                                  "available-upgrades": [2]}])

            self.assertEquals(sorted(self.store.get_available_upgrades()), [2])

        result = self.reporter.detect_changes()
        return result.addCallback(got_result)

    def test_detect_changes_with_not_upgrade(self):
        message_store = self.broker_service.message_store
        message_store.set_accepted_types(["packages"])

        self.store.set_hash_ids({HASH1: 1, HASH2: 2, HASH3: 3})
        self.store.add_available([1, 2, 3])
        self.store.add_available_upgrades([2])

        def got_result(result):
            self.assertMessages(message_store.get_pending_messages(),
                                [{"type": "packages",
                                  "not-available-upgrades": [2]}])

            self.assertEquals(sorted(self.store.get_available_upgrades()), [])

        result = self.reporter.detect_changes()
        return result.addCallback(got_result)

    def test_run(self):
        reporter_mock = self.mocker.patch(self.reporter)

        self.mocker.order()

        results = [Deferred() for i in range(6)]

        reporter_mock.fetch_hash_id_db()
        self.mocker.result(results[0])

        reporter_mock.use_hash_id_db()
        self.mocker.result(results[1])

        reporter_mock.handle_tasks()
        self.mocker.result(results[2])

        reporter_mock.remove_expired_hash_id_requests()
        self.mocker.result(results[3])

        reporter_mock.request_unknown_hashes()
        self.mocker.result(results[4])

        reporter_mock.detect_changes()
        self.mocker.result(results[5])

        self.mocker.replay()

        self.reporter.run()

        # It must raise an error because deferreds weren't yet fired.
        self.assertRaises(AssertionError, self.mocker.verify)

        # Call them in reversed order. It must not make a difference because
        # Twisted is ensuring that things run in the proper order.
        for deferred in reversed(results):
            deferred.callback(None)

    def test_main(self):
        data_path = self.makeDir()

        run_task_handler = self.mocker.replace("landscape.package.taskhandler"
                                               ".run_task_handler",
                                               passthrough=False)
        run_task_handler(PackageReporter, ["ARGS"])
        self.mocker.result("RESULT")
        self.mocker.replay()

        self.assertEquals(main(["ARGS"]), "RESULT")

    def test_find_reporter_command(self):
        dirname = self.makeDir()
        filename = self.makeFile("", dirname=dirname,
                                 basename="landscape-package-reporter")

        saved_argv = sys.argv
        try:
            sys.argv = [os.path.join(dirname, "landscape-monitor")]

            command = find_reporter_command()

            self.assertEquals(command, filename)
        finally:
            sys.argv = saved_argv

    def test_resynchronize(self):
        """
        When a resynchronize task arrives, the reporter should clear
        out all the data in the package store, except the hash ids.
        This is done in the reporter so that we know it happens when
        no other reporter is possibly running at the same time.
        """
        self.store.set_hash_ids({HASH1: 3, HASH2: 4})
        self.store.add_available([1])
        self.store.add_available_upgrades([2])
        self.store.add_installed([2])
        request1 = self.store.add_hash_id_request(["hash3"])
        request2 = self.store.add_hash_id_request(["hash4"])

        # Let's make sure the data is there.
        self.assertEquals(self.store.get_available_upgrades(), [2])
        self.assertEquals(self.store.get_available(), [1])
        self.assertEquals(self.store.get_installed(), [2])
        self.assertEquals(self.store.get_hash_id_request(request1.id).id, request1.id)

        self.store.add_task("reporter", {"type": "resynchronize"})
        
        deferred = self.reporter.run()

        def check_result(result):
            # The hashes should not go away.
            hash1 = self.store.get_hash_id(HASH1)
            hash2 = self.store.get_hash_id(HASH2)
            self.assertEquals([hash1, hash2], [3, 4])

            # But the other data should.
            self.assertEquals(self.store.get_available_upgrades(), [])
            # After running the resychronize task, detect_changes is called,
            # and the existing known hashes are made available.
            self.assertEquals(self.store.get_available(), [3, 4])
            self.assertEquals(self.store.get_installed(), [])

            # A New hash id request should also be detected for HASH3,
            # but there should be no other hash id requests.
            request = self.store.get_hash_id_request(request1.id)
            self.assertEquals(request.id, request1.id)
            self.assertEquals(request.hashes, [HASH3])
            self.assertRaises(UnknownHashIDRequest,
                              self.store.get_hash_id_request, request2.id)
        deferred.addCallback(check_result)
        return deferred


class EqualsHashes(object):

    def __init__(self, *hashes):
        self._hashes = sorted(hashes)

    def __eq__(self, other):
        return self._hashes == sorted(other)
