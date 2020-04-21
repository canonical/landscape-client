import locale
import sys
import os
import time
import apt_pkg
import mock
import shutil
import subprocess

from twisted.internet.defer import Deferred, succeed, fail, inlineCallbacks
from twisted.internet import reactor


from landscape.lib import bpickle
from landscape.lib.apt.package.facade import AptFacade
from landscape.lib.apt.package.store import (
    PackageStore, UnknownHashIDRequest, FakePackageStore)
from landscape.lib.apt.package.testing import (
    AptFacadeHelper, SimpleRepositoryHelper,
    HASH1, HASH2, HASH3, PKGNAME1)
from landscape.lib.fs import create_text_file, touch_file
from landscape.lib.fetch import FetchError
from landscape.lib.lsb_release import parse_lsb_release, LSB_RELEASE_FILENAME
from landscape.lib.testing import EnvironSaverHelper, FakeReactor
from landscape.client.package.reporter import (
    PackageReporter, HASH_ID_REQUEST_TIMEOUT, main, find_reporter_command,
    PackageReporterConfiguration, FakeGlobalReporter, FakeReporter)
from landscape.client.package import reporter
from landscape.client.tests.helpers import LandscapeTest, BrokerServiceHelper


SAMPLE_LSB_RELEASE = "DISTRIB_CODENAME=codename\n"


class PackageReporterConfigurationTest(LandscapeTest):

    def test_force_apt_update_option(self):
        """
        The L{PackageReporterConfiguration} supports a '--force-apt-update'
        command line option.
        """
        config = PackageReporterConfiguration()
        config.default_config_filenames = (self.makeFile(""), )
        self.assertFalse(config.force_apt_update)
        config.load(["--force-apt-update"])
        self.assertTrue(config.force_apt_update)


class PackageReporterAptTest(LandscapeTest):

    helpers = [AptFacadeHelper, SimpleRepositoryHelper, BrokerServiceHelper]

    Facade = AptFacade

    def setUp(self):
        super(PackageReporterAptTest, self).setUp()
        self.store = PackageStore(self.makeFile())
        self.config = PackageReporterConfiguration()
        self.reactor = FakeReactor()
        self.reporter = PackageReporter(
            self.store, self.facade, self.remote, self.config, self.reactor)
        self.reporter.get_session_id()
        # Assume update-notifier-common stamp file is not present by
        # default.
        self.reporter.update_notifier_stamp = "/Not/Existing"
        self.config.data_path = self.makeDir()
        os.mkdir(self.config.package_directory)
        self.check_stamp_file = self.config.detect_package_changes_stamp

    def _clear_repository(self):
        """Remove all packages from self.repository."""
        create_text_file(self.repository_dir + "/Packages", "")

    def set_pkg1_upgradable(self):
        """Make it so that package "name1" is considered to be upgradable.

        Return the hash of the package that upgrades "name1".
        """
        self._add_package_to_deb_dir(
            self.repository_dir, "name1", version="version2")
        self.facade.reload_channels()
        name1_upgrade = sorted(self.facade.get_packages_by_name("name1"))[1]
        return self.facade.get_package_hash(name1_upgrade)

    def set_pkg1_installed(self):
        """Make it so that package "name1" is considered installed."""
        self._install_deb_file(os.path.join(self.repository_dir, PKGNAME1))

    def set_pkg1_autoremovable(self):
        """Make it so package "name1" is considered auto removable."""
        self.set_pkg1_installed()
        self.facade.reload_channels()
        name1 = sorted(self.facade.get_packages_by_name("name1"))[0]
        # Since no other package depends on this, all that's needed
        # to have it autoremovable is to mark it as installed+auto.
        name1.package.mark_auto(True)

    def _make_fake_apt_update(self, out="output", err="error", code=0):
        """Create a fake apt-update executable"""
        self.reporter.apt_update_filename = self.makeFile(
            "#!/bin/sh\n"
            "echo -n '%s'\n"
            "echo -n '%s' >&2\n"
            "exit %d" % (out, err, code))
        os.chmod(self.reporter.apt_update_filename, 0o755)

    def test_set_package_ids_with_all_known(self):
        self.store.add_hash_id_request([b"hash1", b"hash2"])
        request2 = self.store.add_hash_id_request([b"hash3", b"hash4"])
        self.store.add_hash_id_request([b"hash5", b"hash6"])

        self.store.add_task("reporter",
                            {"type": "package-ids", "ids": [123, 456],
                             "request-id": request2.id})

        def got_result(result):
            self.assertEqual(self.store.get_hash_id(b"hash1"), None)
            self.assertEqual(self.store.get_hash_id(b"hash2"), None)
            self.assertEqual(self.store.get_hash_id(b"hash3"), 123)
            self.assertEqual(self.store.get_hash_id(b"hash4"), 456)
            self.assertEqual(self.store.get_hash_id(b"hash5"), None)
            self.assertEqual(self.store.get_hash_id(b"hash6"), None)

        deferred = self.reporter.handle_tasks()
        return deferred.addCallback(got_result)

    def test_set_package_ids_with_unknown_request_id(self):

        self.store.add_task("reporter",
                            {"type": "package-ids", "ids": [123, 456],
                             "request-id": 123})

        # Nothing bad should happen.
        return self.reporter.handle_tasks()

    def test_set_package_ids_py27(self):
        """Check py27 upgraded messages are decoded."""
        self.store.add_task("reporter",
                            {"type": b"package-ids", "ids": [123, 456],
                             "request-id": 123})
        result = self.reporter.handle_tasks()
        self.assertIsInstance(result, Deferred)

    @mock.patch("logging.warning", return_value=None)
    def test_handle_task_unknown(self, mock_warn):
        """handle_task fails warns about unknown messages."""
        self.store.add_task("reporter", {"type": "spam"})
        result = self.reporter.handle_tasks()
        self.assertIsInstance(result, Deferred)
        expected = "Unknown task message type: {!r}".format(u"spam")  # py2/3
        mock_warn.assert_called_once_with(expected)

    def test_set_package_ids_with_unknown_hashes(self):
        message_store = self.broker_service.message_store

        message_store.set_accepted_types(["add-packages"])

        request1 = self.store.add_hash_id_request([b"foo", HASH1, b"bar"])

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
            self.assertEqual(request2.hashes, [HASH1])

            # Keeping track of the message id for the message with the
            # package data allows us to tell if we should consider our
            # request as lost for some reason, and thus re-request it.
            message_id = request2.message_id
            self.assertEqual(type(message_id), int)

            self.assertTrue(message_store.is_pending(message_id))

            self.assertMessages(
                message_store.get_pending_messages(),
                [{"packages": [{"description": u"Description1",
                                "installed-size": 28672,
                                "name": u"name1",
                                "relations":
                                    [(131074, u"providesname1"),
                                     (196610, u"name1 = version1-release1"),
                                     (262148,
                                      u"prerequirename1 = prerequireversion1"),
                                     (262148,
                                      u"requirename1 = requireversion1"),
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

        request1 = self.store.add_hash_id_request([b"foo", HASH1, b"bar"])

        self.store.add_task("reporter",
                            {"type": "package-ids",
                             "ids": [123, None, 456],
                             "request-id": request1.id})

        def got_result(result, mocked_get_package_skeleton):
            self.assertTrue(mocked_get_package_skeleton.called)
            message = message_store.get_pending_messages()[0]
            request2 = self.store.get_hash_id_request(message["request-id"])
            self.assertMessages(
                message_store.get_pending_messages(),
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

            def get_hash(self):
                return HASH1  # Need to match the hash of the initial request

        with mock.patch.object(self.Facade, "get_package_skeleton",
                               return_value=FakePackage()) as mocked:
            deferred = self.reporter.handle_tasks()
            return deferred.addCallback(got_result, mocked)

    def test_set_package_ids_with_unknown_hashes_and_failed_send_msg(self):
        message_store = self.broker_service.message_store
        message_store.set_accepted_types(["add-packages"])

        class Boom(Exception):
            pass

        deferred = Deferred()
        deferred.errback(Boom())

        request_id = self.store.add_hash_id_request([b"foo", HASH1, b"bar"]).id

        self.store.add_task("reporter", {"type": "package-ids",
                                         "ids": [123, None, 456],
                                         "request-id": request_id})

        def got_result(result, send_mock):
            send_mock.assert_called_once_with(mock.ANY, mock.ANY, True)
            self.assertMessages(message_store.get_pending_messages(), [])
            self.assertEqual(
                [request.id for request in self.store.iter_hash_id_requests()],
                [request_id])

        with mock.patch.object(
                self.reporter._broker, "send_message") as send_mock:
            send_mock.return_value = deferred
            result = self.reporter.handle_tasks()
            self.assertFailure(result, Boom)
            return result.addCallback(got_result, send_mock)

    def test_set_package_ids_removes_request_id_when_done(self):
        request = self.store.add_hash_id_request([b"hash1"])
        self.store.add_task("reporter", {"type": "package-ids", "ids": [123],
                                         "request-id": request.id})

        def got_result(result):
            self.assertRaises(UnknownHashIDRequest,
                              self.store.get_hash_id_request, request.id)

        deferred = self.reporter.handle_tasks()
        return deferred.addCallback(got_result)

    @mock.patch("landscape.client.package.reporter.fetch_async",
                return_value=succeed(b"hash-ids"))
    @mock.patch("logging.info", return_value=None)
    def test_fetch_hash_id_db(self, logging_mock, mock_fetch_async):

        # Assume package_hash_id_url is set
        self.config.data_path = self.makeDir()
        self.config.package_hash_id_url = "http://fake.url/path/"
        os.makedirs(os.path.join(self.config.data_path, "package", "hash-id"))
        hash_id_db_filename = os.path.join(self.config.data_path, "package",
                                           "hash-id", "uuid_codename_arch")

        # Fake uuid, codename and arch
        message_store = self.broker_service.message_store
        message_store.set_server_uuid("uuid")
        self.reporter.lsb_release_filename = self.makeFile(SAMPLE_LSB_RELEASE)
        self.facade.set_arch("arch")

        # Let's say fetch_async is successful
        hash_id_db_url = self.config.package_hash_id_url + "uuid_codename_arch"

        # We don't have our hash=>id database yet
        self.assertFalse(os.path.exists(hash_id_db_filename))

        result = self.reporter.fetch_hash_id_db()

        # Check the database
        def callback(ignored):
            self.assertTrue(os.path.exists(hash_id_db_filename))
            self.assertEqual(open(hash_id_db_filename).read(), "hash-ids")
        result.addCallback(callback)

        logging_mock.assert_called_once_with(
            "Downloaded hash=>id database from %s" % hash_id_db_url)
        mock_fetch_async.assert_called_once_with(
            hash_id_db_url, cainfo=None, proxy=None)
        return result

    @mock.patch("landscape.client.package.reporter.fetch_async",
                return_value=succeed(b"hash-ids"))
    @mock.patch("logging.info", return_value=None)
    def test_fetch_hash_id_db_with_proxy(self, logging_mock, mock_fetch_async):
        """fetching hash-id-db uses proxy settings"""
        # Assume package_hash_id_url is set
        self.config.data_path = self.makeDir()
        self.config.package_hash_id_url = "https://fake.url/path/"
        os.makedirs(os.path.join(self.config.data_path, "package", "hash-id"))

        # Fake uuid, codename and arch
        message_store = self.broker_service.message_store
        message_store.set_server_uuid("uuid")
        self.reporter.lsb_release_filename = self.makeFile(SAMPLE_LSB_RELEASE)
        self.facade.set_arch("arch")

        # Let's say fetch_async is successful
        hash_id_db_url = self.config.package_hash_id_url + "uuid_codename_arch"

        # set proxy settings
        self.config.https_proxy = "http://helloproxy:8000"

        result = self.reporter.fetch_hash_id_db()
        mock_fetch_async.assert_called_once_with(
            hash_id_db_url, cainfo=None, proxy="http://helloproxy:8000")
        return result

    @mock.patch("landscape.client.package.reporter.fetch_async")
    def test_fetch_hash_id_db_does_not_download_twice(self, mock_fetch_async):

        # Let's say that the hash=>id database is already there
        self.config.package_hash_id_url = "http://fake.url/path/"
        self.config.data_path = self.makeDir()
        os.makedirs(os.path.join(self.config.data_path, "package", "hash-id"))
        hash_id_db_filename = os.path.join(self.config.data_path, "package",
                                           "hash-id", "uuid_codename_arch")
        open(hash_id_db_filename, "w").write("test")

        # Fake uuid, codename and arch
        message_store = self.broker_service.message_store
        message_store.set_server_uuid("uuid")
        self.reporter.lsb_release_filename = self.makeFile(SAMPLE_LSB_RELEASE)
        self.facade.set_arch("arch")

        result = self.reporter.fetch_hash_id_db()

        def callback(ignored):
            # Check that fetch_async hasn't been called
            mock_fetch_async.assert_not_called()

            # The hash=>id database is still there
            self.assertEqual(open(hash_id_db_filename).read(), "test")

        result.addCallback(callback)

        return result

    @mock.patch("logging.warning", return_value=None)
    def test_fetch_hash_id_db_undetermined_server_uuid(self, logging_mock):
        """
        If the server-uuid can't be determined for some reason, no download
        should be attempted and the failure should be properly logged.
        """
        message_store = self.broker_service.message_store
        message_store.set_server_uuid(None)

        result = self.reporter.fetch_hash_id_db()
        logging_mock.assert_called_once_with(
            "Couldn't determine which hash=>id database to use: "
            "server UUID not available")
        return result

    @mock.patch("logging.warning", return_value=None)
    def test_fetch_hash_id_db_undetermined_codename(self, logging_mock):

        # Fake uuid
        message_store = self.broker_service.message_store
        message_store.set_server_uuid("uuid")

        # Undetermined codename
        self.reporter.lsb_release_filename = self.makeFile("Foo=bar")

        result = self.reporter.fetch_hash_id_db()

        logging_mock.assert_called_once_with(
            "Couldn't determine which hash=>id database to use: "
            "missing code-name key in %s" % self.reporter.lsb_release_filename)
        return result

    @mock.patch("logging.warning", return_value=None)
    def test_fetch_hash_id_db_undetermined_arch(self, logging_mock):

        # Fake uuid and codename
        message_store = self.broker_service.message_store
        message_store.set_server_uuid("uuid")
        self.reporter.lsb_release_filename = self.makeFile(SAMPLE_LSB_RELEASE)

        # Undetermined arch
        self.facade.set_arch("")

        result = self.reporter.fetch_hash_id_db()
        logging_mock.assert_called_once_with(
            "Couldn't determine which hash=>id database to use: "
            "unknown dpkg architecture")
        return result

    @mock.patch("landscape.client.package.reporter.fetch_async",
                return_value=succeed(b"hash-ids"))
    def test_fetch_hash_id_db_with_default_url(self, mock_fetch_async):
        # Let's say package_hash_id_url is not set but url is
        self.config.data_path = self.makeDir()
        self.config.package_hash_id_url = None
        self.config.url = "http://fake.url/path/message-system/"
        os.makedirs(os.path.join(self.config.data_path, "package", "hash-id"))
        hash_id_db_filename = os.path.join(self.config.data_path, "package",
                                           "hash-id", "uuid_codename_arch")

        # Fake uuid, codename and arch
        message_store = self.broker_service.message_store
        message_store.set_server_uuid("uuid")
        self.reporter.lsb_release_filename = self.makeFile(SAMPLE_LSB_RELEASE)
        self.facade.set_arch("arch")

        # Check fetch_async is called with the default url
        hash_id_db_url = "http://fake.url/path/hash-id-databases/" \
                         "uuid_codename_arch"
        result = self.reporter.fetch_hash_id_db()

        # Check the database
        def callback(ignored):
            self.assertTrue(os.path.exists(hash_id_db_filename))
            self.assertEqual(open(hash_id_db_filename).read(), "hash-ids")
        result.addCallback(callback)
        mock_fetch_async.assert_called_once_with(
            hash_id_db_url, cainfo=None, proxy=None)
        return result

    @mock.patch("landscape.client.package.reporter.fetch_async",
                return_value=fail(FetchError("fetch error")))
    @mock.patch("logging.warning", return_value=None)
    def test_fetch_hash_id_db_with_download_error(
            self, logging_mock, mock_fetch_async):

        # Assume package_hash_id_url is set
        self.config.data_path = self.makeDir()
        self.config.package_hash_id_url = "http://fake.url/path/"

        # Fake uuid, codename and arch
        message_store = self.broker_service.message_store
        message_store.set_server_uuid("uuid")
        self.reporter.lsb_release_filename = self.makeFile(SAMPLE_LSB_RELEASE)
        self.facade.set_arch("arch")

        # Let's say fetch_async fails
        hash_id_db_url = self.config.package_hash_id_url + "uuid_codename_arch"

        result = self.reporter.fetch_hash_id_db()

        # We shouldn't have any hash=>id database
        def callback(ignored):
            hash_id_db_filename = os.path.join(
                self.config.data_path, "package", "hash-id",
                "uuid_codename_arch")
            self.assertEqual(os.path.exists(hash_id_db_filename), False)
        result.addCallback(callback)

        logging_mock.assert_called_once_with(
            "Couldn't download hash=>id database: fetch error")
        mock_fetch_async.assert_called_once_with(
            hash_id_db_url, cainfo=None, proxy=None)
        return result

    @mock.patch("logging.warning", return_value=None)
    def test_fetch_hash_id_db_with_undetermined_url(self, logging_mock):

        # We don't know where to fetch the hash=>id database from
        self.config.url = None
        self.config.package_hash_id_url = None

        # Fake uuid, codename and arch
        message_store = self.broker_service.message_store
        message_store.set_server_uuid("uuid")
        self.reporter.lsb_release_filename = self.makeFile(SAMPLE_LSB_RELEASE)
        self.facade.set_arch("arch")

        result = self.reporter.fetch_hash_id_db()

        # We shouldn't have any hash=>id database
        def callback(ignored):
            hash_id_db_filename = os.path.join(
                self.config.data_path, "package", "hash-id",
                "uuid_codename_arch")
            self.assertEqual(os.path.exists(hash_id_db_filename), False)
        result.addCallback(callback)

        logging_mock.assert_called_once_with(
            "Can't determine the hash=>id database url")
        return result

    @mock.patch("landscape.client.package.reporter.fetch_async",
                return_value=succeed(b"hash-ids"))
    def test_fetch_hash_id_db_with_custom_certificate(self, mock_fetch_async):
        """
        The L{PackageReporter.fetch_hash_id_db} method takes into account the
        possible custom SSL certificate specified in the client configuration.
        """

        self.config.url = "http://fake.url/path/message-system/"
        self.config.ssl_public_key = "/some/key"

        # Fake uuid, codename and arch
        message_store = self.broker_service.message_store
        message_store.set_server_uuid("uuid")
        self.reporter.lsb_release_filename = self.makeFile(SAMPLE_LSB_RELEASE)
        self.facade.set_arch("arch")

        # Check fetch_async is called with the default url
        hash_id_db_url = "http://fake.url/path/hash-id-databases/" \
                         "uuid_codename_arch"

        # Now go!
        result = self.reporter.fetch_hash_id_db()
        mock_fetch_async.assert_called_once_with(
            hash_id_db_url, cainfo=self.config.ssl_public_key, proxy=None)

        return result

    def test_wb_apt_sources_have_changed(self):
        """
        The L{PackageReporter._apt_sources_have_changed} method returns a bool
        indicating if the APT sources list file has changed recently.
        """
        self.reporter.sources_list_filename = "/I/Dont/Exist"
        self.reporter.sources_list_directory = "/I/Dont/Exist/At/All"
        self.assertFalse(self.reporter._apt_sources_have_changed())
        self.reporter.sources_list_filename = self.makeFile("foo")
        self.assertTrue(self.reporter._apt_sources_have_changed())
        os.utime(self.reporter.sources_list_filename, (-1, time.time() - 1799))
        self.assertTrue(self.reporter._apt_sources_have_changed())
        os.utime(self.reporter.sources_list_filename, (-1, time.time() - 1800))
        self.assertFalse(self.reporter._apt_sources_have_changed())

    def test_wb_apt_sources_have_changed_with_directory(self):
        """
        The L{PackageReporter._apt_sources_have_changed} checks also for
        possible additional sources files under /etc/apt/sources.d.
        """
        self.reporter.sources_list_filename = "/I/Dont/Exist/At/All"
        self.reporter.sources_list_directory = self.makeDir()
        self.makeFile(dirname=self.reporter.sources_list_directory,
                      content="deb http://foo ./")
        self.assertTrue(self.reporter._apt_sources_have_changed())

    def test_remove_expired_hash_id_request(self):
        request = self.store.add_hash_id_request([b"hash1"])
        request.message_id = 9999

        request.timestamp -= HASH_ID_REQUEST_TIMEOUT

        def got_result(result):
            self.assertRaises(UnknownHashIDRequest,
                              self.store.get_hash_id_request, request.id)

        result = self.reporter.remove_expired_hash_id_requests()
        return result.addCallback(got_result)

    def test_remove_expired_hash_id_request_wont_remove_before_timeout(self):
        request1 = self.store.add_hash_id_request([b"hash1"])
        request1.message_id = 9999
        request1.timestamp -= HASH_ID_REQUEST_TIMEOUT / 2

        initial_timestamp = request1.timestamp

        def got_result(result):
            request2 = self.store.get_hash_id_request(request1.id)
            self.assertTrue(request2)

            # Shouldn't update timestamp when already delivered.
            self.assertEqual(request2.timestamp, initial_timestamp)

        result = self.reporter.remove_expired_hash_id_requests()
        return result.addCallback(got_result)

    def test_remove_expired_hash_id_request_updates_timestamps(self):
        request = self.store.add_hash_id_request([b"hash1"])
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
        request = self.store.add_hash_id_request([b"hash1"])

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
            self.assertEqual(request.hashes, message["hashes"])

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
            self.assertEqual(len(message_store.get_pending_messages()), 1)
            message = message_store.get_pending_messages()[-1]
            self.assertEqual(len(message["hashes"]), 2)

            result2 = self.reporter.request_unknown_hashes()
            result2.addCallback(got_result2, message["hashes"])

            return result2

        def got_result2(result, hashes):
            # The second message sent should send the missing hash.
            self.assertEqual(len(message_store.get_pending_messages()), 2)
            message = message_store.get_pending_messages()[-1]
            self.assertEqual(len(message["hashes"]), 1)
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
            self.assertEqual(request.hashes, message["hashes"])

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

        class Boom(Exception):
            pass

        deferred = Deferred()
        deferred.errback(Boom())

        def got_result(result, send_mock):
            send_mock.assert_called_once_with(mock.ANY, mock.ANY, True)
            self.assertMessages(message_store.get_pending_messages(), [])
            self.assertEqual(list(self.store.iter_hash_id_requests()), [])

        with mock.patch.object(
                self.reporter._broker, "send_message") as send_mock:
            send_mock.return_value = deferred
            result = self.reporter.request_unknown_hashes()
            self.assertFailure(result, Boom)
            return result.addCallback(got_result, send_mock)

    def test_detect_packages_creates_stamp_file(self):
        """
        When the detect_packages method computes package changes, it creates
        a stamp file after sending the message.
        """
        message_store = self.broker_service.message_store
        message_store.set_accepted_types(["packages"])

        self.store.set_hash_ids({HASH1: 1, HASH2: 2, HASH3: 3})

        self.assertFalse(os.path.exists(self.check_stamp_file))

        def got_result(result):
            self.assertMessages(message_store.get_pending_messages(),
                                [{"type": "packages", "available": [(1, 3)]}])
            self.assertTrue(os.path.exists(self.check_stamp_file))

        result = self.reporter.detect_packages_changes()
        return result.addCallback(got_result)

    def test_detect_packages_changes_with_available(self):
        message_store = self.broker_service.message_store
        message_store.set_accepted_types(["packages"])

        self.store.set_hash_ids({HASH1: 1, HASH2: 2, HASH3: 3})

        def got_result(result):
            self.assertMessages(message_store.get_pending_messages(),
                                [{"type": "packages", "available": [(1, 3)]}])

            self.assertEqual(sorted(self.store.get_available()), [1, 2, 3])

        result = self.reporter.detect_packages_changes()
        return result.addCallback(got_result)

    def test_detect_packages_changes_with_available_and_unknown_hash(self):
        message_store = self.broker_service.message_store
        message_store.set_accepted_types(["packages"])

        self.store.set_hash_ids({HASH1: 1, HASH3: 3})

        def got_result(result):
            self.assertMessages(message_store.get_pending_messages(),
                                [{"type": "packages", "available": [1, 3]}])

            self.assertEqual(sorted(self.store.get_available()), [1, 3])

        result = self.reporter.detect_packages_changes()
        return result.addCallback(got_result)

    def test_detect_packages_changes_with_available_and_previously_known(self):
        message_store = self.broker_service.message_store
        message_store.set_accepted_types(["packages"])

        self.store.set_hash_ids({HASH1: 1, HASH2: 2, HASH3: 3})
        self.store.add_available([1, 3])

        def got_result(result):
            self.assertMessages(message_store.get_pending_messages(),
                                [{"type": "packages", "available": [2]}])

            self.assertEqual(sorted(self.store.get_available()), [1, 2, 3])

        result = self.reporter.detect_packages_changes()
        return result.addCallback(got_result)

    def test_detect_packages_changes_with_not_available(self):
        message_store = self.broker_service.message_store
        message_store.set_accepted_types(["packages"])

        self._clear_repository()

        self.store.set_hash_ids({HASH1: 1, HASH2: 2, HASH3: 3})
        self.store.add_available([1, 2, 3])

        def got_result(result):
            self.assertMessages(message_store.get_pending_messages(),
                                [{"type": "packages",
                                  "not-available": [(1, 3)]}])

            self.assertEqual(self.store.get_available(), [])

        result = self.reporter.detect_packages_changes()
        return result.addCallback(got_result)

    def test_detect_packages_changes_with_installed(self):
        message_store = self.broker_service.message_store
        message_store.set_accepted_types(["packages"])

        self.store.set_hash_ids({HASH1: 1, HASH2: 2, HASH3: 3})
        self.store.add_available([1, 2, 3])

        self.set_pkg1_installed()

        def got_result(result):
            self.assertMessages(message_store.get_pending_messages(),
                                [{"type": "packages", "installed": [1]}])

            self.assertEqual(self.store.get_installed(), [1])

        result = self.reporter.detect_packages_changes()
        return result.addCallback(got_result)

    def test_detect_packages_changes_with_installed_already_known(self):
        message_store = self.broker_service.message_store
        message_store.set_accepted_types(["packages"])

        self.store.set_hash_ids({HASH1: 1, HASH2: 2, HASH3: 3})
        self.store.add_available([1, 2, 3])
        self.store.add_installed([1])

        self.set_pkg1_installed()

        def got_result(result):
            self.assertFalse(result)
            self.assertMessages(message_store.get_pending_messages(), [])

        result = self.reporter.detect_packages_changes()
        return result.addCallback(got_result)

    def test_detect_packages_changes_with_not_installed(self):
        message_store = self.broker_service.message_store
        message_store.set_accepted_types(["packages"])

        self.store.set_hash_ids({HASH1: 1, HASH2: 2, HASH3: 3})
        self.store.add_available([1, 2, 3])
        self.store.add_installed([1])

        def got_result(result):
            self.assertTrue(result)
            self.assertMessages(message_store.get_pending_messages(),
                                [{"type": "packages", "not-installed": [1]}])

            self.assertEqual(self.store.get_installed(), [])

        result = self.reporter.detect_packages_changes()
        return result.addCallback(got_result)

    def test_detect_packages_changes_with_upgrade_but_not_installed(self):
        message_store = self.broker_service.message_store
        message_store.set_accepted_types(["packages"])

        upgrade_hash = self.set_pkg1_upgradable()
        self.store.set_hash_ids({HASH1: 1, upgrade_hash: 2, HASH3: 3})
        self.store.add_available([1, 2, 3])

        def got_result(result):
            self.assertMessages(message_store.get_pending_messages(), [])

        result = self.reporter.detect_packages_changes()
        return result.addCallback(got_result)

    def test_detect_packages_changes_with_upgrade(self):
        message_store = self.broker_service.message_store
        message_store.set_accepted_types(["packages"])

        upgrade_hash = self.set_pkg1_upgradable()
        self.set_pkg1_installed()
        self.facade.reload_channels()

        self.store.set_hash_ids(
            {HASH1: 1, upgrade_hash: 2, HASH3: 3})
        self.store.add_available([1, 2, 3])
        self.store.add_installed([1])

        def got_result(result):
            self.assertMessages(message_store.get_pending_messages(),
                                [{"type": "packages",
                                  "available-upgrades": [2]}])

            self.assertEqual(self.store.get_available_upgrades(), [2])

        result = self.reporter.detect_packages_changes()
        return result.addCallback(got_result)

    def test_detect_packages_changes_with_not_upgrade(self):
        message_store = self.broker_service.message_store
        message_store.set_accepted_types(["packages"])

        self.store.set_hash_ids({HASH1: 1, HASH2: 2, HASH3: 3})
        self.store.add_available([1, 2, 3])
        self.store.add_available_upgrades([2])

        def got_result(result):
            self.assertMessages(message_store.get_pending_messages(),
                                [{"type": "packages",
                                  "not-available-upgrades": [2]}])

            self.assertEqual(self.store.get_available_upgrades(), [])

        result = self.reporter.detect_packages_changes()
        return result.addCallback(got_result)

    def test_detect_packages_changes_with_autoremovable(self):
        message_store = self.broker_service.message_store
        message_store.set_accepted_types(["packages"])

        self.store.set_hash_ids({HASH1: 1, HASH2: 2, HASH3: 3})
        self.store.add_available([1, 2, 3])
        self.store.add_installed([1])
        self.set_pkg1_autoremovable()

        result = self.successResultOf(self.reporter.detect_packages_changes())
        self.assertTrue(result)

        expected = [{"type": "packages", "autoremovable": [1]}]
        self.assertMessages(message_store.get_pending_messages(), expected)
        self.assertEqual([1], self.store.get_autoremovable())

    def test_detect_packages_changes_with_not_autoremovable(self):
        message_store = self.broker_service.message_store
        message_store.set_accepted_types(["packages"])

        self.store.set_hash_ids({HASH1: 1, HASH2: 2, HASH3: 3})
        self.store.add_available([1, 2, 3])
        # We don't care about checking other state changes in this test.
        # In reality the package would also be installed, available, etc.
        self.store.add_autoremovable([1, 2])

        result = self.successResultOf(self.reporter.detect_packages_changes())
        self.assertTrue(result)

        expected = [{"type": "packages", "not-autoremovable": [1, 2]}]
        self.assertMessages(message_store.get_pending_messages(), expected)
        self.assertEqual([], self.store.get_autoremovable())

    def test_detect_packages_changes_with_known_autoremovable(self):
        message_store = self.broker_service.message_store
        message_store.set_accepted_types(["packages"])

        self.store.set_hash_ids({HASH1: 1, HASH2: 2, HASH3: 3})
        self.store.add_available([1, 2, 3])
        self.store.add_installed([1])
        self.store.add_autoremovable([1])
        self.set_pkg1_autoremovable()

        result = self.successResultOf(self.reporter.detect_packages_changes())
        self.assertFalse(result)
        self.assertEqual([1], self.store.get_autoremovable())

    @inlineCallbacks
    def test_detect_packages_from_security_pocket(self):
        """Packages versions coming from security are reported as such."""
        message_store = self.broker_service.message_store
        message_store.set_accepted_types(["packages"])
        lsb = parse_lsb_release(LSB_RELEASE_FILENAME)
        release_path = os.path.join(self.repository_dir, "Release")
        with open(release_path, "w") as release:
            release.write("Suite: {}-security".format(lsb["code-name"]))

        self.store.set_hash_ids({HASH1: 1, HASH2: 2, HASH3: 3})

        yield self.reporter.detect_packages_changes()

        self.assertMessages(message_store.get_pending_messages(), [{
            "type": "packages",
            "available": [(1, 3)],
            "security": [(1, 3)],
        }])
        self.assertEqual(sorted(self.store.get_available()), [1, 2, 3])
        self.assertEqual(sorted(self.store.get_security()), [1, 2, 3])

    @inlineCallbacks
    def test_detect_packages_not_from_security_pocket(self):
        """Packages versions removed from security are reported as such."""
        message_store = self.broker_service.message_store
        message_store.set_accepted_types(["packages"])

        self.store.set_hash_ids({HASH1: 1, HASH2: 2, HASH3: 3})
        self.store.add_available([1, 2, 3])
        self.store.add_security([1, 2])

        yield self.reporter.detect_packages_changes()

        self.assertMessages(message_store.get_pending_messages(), [{
            "type": "packages",
            "not-security": [1, 2],
        }])
        self.assertEqual(sorted(self.store.get_available()), [1, 2, 3])
        self.assertEqual(self.store.get_security(), [])

    def test_detect_packages_changes_with_backports(self):
        """
        Package versions coming from backports aren't considered to be
        available.

        This is because we don't support pinning, and the backports
        archive is enabled by default since xenial.
        """
        message_store = self.broker_service.message_store
        message_store.set_accepted_types(["packages"])

        lsb = parse_lsb_release(LSB_RELEASE_FILENAME)
        release_path = os.path.join(self.repository_dir, "Release")
        with open(release_path, "w") as release:
            release.write("Suite: {}-backports".format(lsb["code-name"]))

        self.store.set_hash_ids({HASH1: 1, HASH2: 2, HASH3: 3})

        def got_result(result):
            self.assertMessages(message_store.get_pending_messages(), [])

            self.assertEqual(sorted(self.store.get_available()), [])

        result = self.reporter.detect_packages_changes()
        return result.addCallback(got_result)

    def test_detect_packages_changes_with_backports_others(self):
        """
        Packages coming from backport archives that aren't named like
        the official backports archive are considered to be available.
        """
        message_store = self.broker_service.message_store
        message_store.set_accepted_types(["packages"])

        release_path = os.path.join(self.repository_dir, "Release")
        with open(release_path, "w") as release:
            release.write("Suite: my-personal-backports")

        self.store.set_hash_ids({HASH1: 1, HASH2: 2, HASH3: 3})

        def got_result(result):
            self.assertMessages(message_store.get_pending_messages(),
                                [{"type": "packages", "available": [(1, 3)]}])

            self.assertEqual(sorted(self.store.get_available()), [1, 2, 3])

        result = self.reporter.detect_packages_changes()
        return result.addCallback(got_result)

    def test_detect_packages_changes_with_backports_both(self):
        """
        If a package is both in the official backports archive and in
        some other archive (e.g. a PPA), the package is considered to be
        available.

        The reason for this is that if you have enabled a PPA, you most
        likely want to get updates from it.
        """
        message_store = self.broker_service.message_store
        message_store.set_accepted_types(["packages"])

        temp_dir = self.makeDir()
        other_backport_dir = os.path.join(temp_dir, "my-personal-backports")
        shutil.copytree(self.repository_dir, other_backport_dir)
        os.remove(os.path.join(other_backport_dir, "Packages"))
        self.facade.add_channel_deb_dir(other_backport_dir)

        lsb = parse_lsb_release(LSB_RELEASE_FILENAME)
        official_release_path = os.path.join(self.repository_dir, "Release")
        with open(official_release_path, "w") as release:
            release.write("Suite: {}-backports".format(lsb["code-name"]))
        unofficial_release_path = os.path.join(other_backport_dir, "Release")
        with open(unofficial_release_path, "w") as release:
            release.write("Suite: my-personal-backports")

        self.store.set_hash_ids({HASH1: 1, HASH2: 2, HASH3: 3})

        def got_result(result):
            self.assertMessages(message_store.get_pending_messages(),
                                [{"type": "packages", "available": [(1, 3)]}])

            self.assertEqual(sorted(self.store.get_available()), [1, 2, 3])

        result = self.reporter.detect_packages_changes()
        return result.addCallback(got_result)

    @inlineCallbacks
    def test_detect_packages_after_tasks(self):
        """
        When the L{PackageReporter} got a task to handle, it forces itself to
        detect package changes, not checking the local state of package.
        """
        message_store = self.broker_service.message_store
        message_store.set_accepted_types(["packages"])

        self.store.set_hash_ids({HASH1: 1, HASH2: 2, HASH3: 3})

        touch_file(self.check_stamp_file)

        self.store.add_task("reporter",
                            {"type": "package-ids", "ids": [123, 456],
                             "request-id": 123})

        yield self.reporter.handle_tasks()

        yield self.reporter.detect_packages_changes()

        # We check that detect changes run by looking at messages
        self.assertMessages(message_store.get_pending_messages(),
                            [{"type": "packages", "available": [(1, 3)]}])

    def test_detect_packages_changes_with_not_locked_and_ranges(self):
        """
        Ranges are used when reporting changes to 3 or more not locked packages
        having consecutive ids.
        """
        message_store = self.broker_service.message_store
        message_store.set_accepted_types(["packages"])

        self.store.add_locked([1, 2, 3])

        self.store.set_hash_ids({HASH1: 1, HASH2: 2, HASH3: 3})
        self.store.add_available([1, 2, 3])

        def got_result(result):
            self.assertMessages(message_store.get_pending_messages(),
                                [{"type": "packages", "not-locked": [(1, 3)]}])
            self.assertEqual(sorted(self.store.get_locked()), [])

        result = self.reporter.detect_packages_changes()
        return result.addCallback(got_result)

    def test_detect_changes_considers_packages_changes(self):
        """
        The L{PackageReporter.detect_changes} method package changes.
        """
        with mock.patch.object(self.reporter, "detect_packages_changes",
                               return_value=succeed(True)) as reporter_mock:
            self.successResultOf(self.reporter.detect_changes())
        reporter_mock.assert_called_once_with()

    def test_detect_changes_fires_package_data_changed(self):
        """
        The L{PackageReporter.detect_changes} method fires an event of
        type 'package-data-changed' if we detected something has changed
        with respect to our previous run.
        """
        callback = mock.Mock()
        self.broker_service.reactor.call_on("package-data-changed", callback)
        with mock.patch.object(self.reporter, "detect_packages_changes",
                               return_value=succeed(True)) as reporter_mock:
            self.successResultOf(self.reporter.detect_changes())
        reporter_mock.assert_called_once_with()
        callback.assert_called_once_with()

    def test_run(self):
        results = [Deferred() for i in range(7)]
        self.reporter.run_apt_update = mock.Mock(return_value=results[0])
        self.reporter.fetch_hash_id_db = mock.Mock(return_value=results[1])
        self.reporter.use_hash_id_db = mock.Mock(return_value=results[2])
        self.reporter.handle_tasks = mock.Mock(return_value=results[3])
        self.reporter.remove_expired_hash_id_requests = mock.Mock(
            return_value=results[4])
        self.reporter.request_unknown_hashes = mock.Mock(
            return_value=results[5])
        self.reporter.detect_changes = mock.Mock(return_value=results[6])

        self.reporter.run()

        # It should be False because deferreds weren't yet fired.
        self.assertFalse(self.reporter.detect_changes.called)

        # Call them in reversed order. It must not make a difference because
        # Twisted is ensuring that things run in the proper order.
        for deferred in reversed(results):
            deferred.callback(None)
        self.assertTrue(self.reporter.run_apt_update.called)
        self.assertTrue(self.reporter.fetch_hash_id_db.called)
        self.assertTrue(self.reporter.use_hash_id_db.called)
        self.assertTrue(self.reporter.handle_tasks.called)
        self.assertTrue(self.reporter.remove_expired_hash_id_requests.called)
        self.assertTrue(self.reporter.request_unknown_hashes.called)
        self.assertTrue(self.reporter.detect_changes.called)

    def test_main(self):
        mocktarget = "landscape.client.package.reporter.run_task_handler"
        with mock.patch(mocktarget) as m:
            m.return_value = "RESULT"
            self.assertEqual("RESULT", main(["ARGS"]))
        m.assert_called_once_with(PackageReporter, ["ARGS"])

    def test_main_resets_locale(self):
        """
        Reporter entry point should reset encoding to utf-8, as libapt-pkg
        encodes description with system encoding and python-apt decodes
        them as utf-8 (LP: #1827857).
        """
        self._add_package_to_deb_dir(
            self.repository_dir, "gosa", description=u"GOsa\u00B2")
        self.facade.reload_channels()

        # Set the only non-utf8 locale which we're sure exists.
        # It behaves slightly differently than the bug, but fails on the
        # same condition.
        locale.setlocale(locale.LC_CTYPE, (None, None))
        self.addCleanup(locale.resetlocale)

        with mock.patch("landscape.client.package.reporter.run_task_handler"):
            main([])

        # With the actual package, the failure will occur looking up the
        # description translation.
        pkg = self.facade.get_packages_by_name("gosa")[0]
        skel = self.facade.get_package_skeleton(pkg, with_info=True)
        self.assertEqual(u"GOsa\u00B2", skel.description)

    def test_find_reporter_command_with_bindir(self):
        self.config.bindir = "/spam/eggs"
        command = find_reporter_command(self.config)

        self.assertEqual("/spam/eggs/landscape-package-reporter", command)

    def test_find_reporter_command_default(self):
        expected = os.path.join(
            os.path.dirname(os.path.abspath(sys.argv[0])),
            "landscape-package-reporter")
        command = find_reporter_command()

        self.assertEqual(expected, command)

    @inlineCallbacks
    def test_resynchronize(self):
        """
        When a resynchronize task arrives, the reporter should clear
        out all the data in the package store, including the hash ids.

        This is done in the reporter so that we know it happens when
        no other reporter is possibly running at the same time.
        """
        self._add_system_package("foo")
        self.facade.reload_channels()
        [foo] = self.facade.get_packages_by_name("foo")
        foo_hash = self.facade.get_package_hash(foo)
        self.facade.set_package_hold(foo)
        self.facade.reload_channels()
        message_store = self.broker_service.message_store
        message_store.set_accepted_types(["package-locks"])

        # create hash_id file
        message_store.set_server_uuid("uuid")
        self.facade.set_arch("arch")
        hash_id_file = os.path.join(
            self.config.hash_id_directory, "uuid_codename_arch")
        os.makedirs(self.config.hash_id_directory)
        with open(hash_id_file, "w"):
            pass

        self.store.set_hash_ids({foo_hash: 3, HASH2: 4})
        self.store.add_available([1])
        self.store.add_available_upgrades([2])
        self.store.add_installed([2])
        self.store.add_locked([3])
        request1 = self.store.add_hash_id_request(["hash3"])
        request2 = self.store.add_hash_id_request(["hash4"])

        # Set the message id to avoid the requests being deleted by the
        # L{PackageReporter.remove_expired_hash_id_requests} method.
        request1.message_id = 1
        request2.message_id = 2

        # Let's make sure the data is there.
        self.assertEqual(self.store.get_available_upgrades(), [2])
        self.assertEqual(self.store.get_available(), [1])
        self.assertEqual(self.store.get_installed(), [2])
        self.assertEqual(self.store.get_hash_id_request(request1.id).id,
                         request1.id)

        self.store.add_task("reporter", {"type": "resynchronize"})

        deferred = self.reporter.run()
        self.reactor.advance(0)
        with mock.patch(
            "landscape.client.package.taskhandler.parse_lsb_release",
            side_effect=lambda _: {"code-name": "codename"}
        ):
            yield deferred

        # The hashes should go away to avoid loops
        # when server gets restored to an early state.
        hash1 = self.store.get_hash_id(foo_hash)
        hash2 = self.store.get_hash_id(HASH2)
        self.assertNotEqual(hash1, 3)
        self.assertNotEqual(hash2, 4)
        self.assertFalse(os.path.exists(hash_id_file))
        self.assertEqual(self.store.get_available_upgrades(), [])

        # After running the resychronize task, the hash db is empty,
        # thus detect_packages_changes will generate an empty set until
        # next run when hash-id db is populated again.
        self.assertEqual(self.store.get_available(), [])
        self.assertEqual(self.store.get_installed(), [])
        self.assertEqual(self.store.get_locked(), [])

        # The two original hash id requests are gone, and a new hash id
        # request should be detected for HASH3.
        [request] = self.store.iter_hash_id_requests()
        self.assertEqual(request.hashes, [HASH3, HASH2, foo_hash, HASH1])

    @mock.patch("logging.warning")
    def test_run_apt_update(self, warning_mock):
        """
        The L{PackageReporter.run_apt_update} method should run apt-update.
        """
        self.reporter.sources_list_filename = "/I/Dont/Exist"
        self.reporter.sources_list_directory = "/I/Dont/Exist"
        self._make_fake_apt_update()
        debug_patcher = mock.patch.object(reporter.logging, "debug")
        debug_mock = debug_patcher.start()
        self.addCleanup(debug_patcher.stop)

        deferred = Deferred()

        def do_test():
            result = self.reporter.run_apt_update()

            def callback(args):
                out, err, code = args
                self.assertEqual("output", out)
                self.assertEqual("error", err)
                self.assertEqual(0, code)
                self.assertFalse(warning_mock.called)
                debug_mock.assert_has_calls([
                    mock.call(
                        "Checking if ubuntu-release-upgrader is running."),
                    mock.call(
                        "'%s' exited with status 0 (out='output', err='error')"
                        % self.reporter.apt_update_filename)
                ])
            result.addCallback(callback)
            self.reactor.advance(0)
            result.chainDeferred(deferred)

        reactor.callWhenRunning(do_test)
        return deferred

    def test_run_apt_update_with_force_apt_update(self):
        """
        L{PackageReporter.run_apt_update} forces an apt-update run if the
        '--force-apt-update' command line option was passed.
        """
        self.makeFile("", path=self.config.update_stamp_filename)
        self.config.load(["--force-apt-update"])
        self._make_fake_apt_update()

        result = self.reporter.run_apt_update()

        def callback(args):
            out, err, code = args
            self.assertEqual("output", out)

        result.addCallback(callback)
        self.reactor.advance(0)
        return result

    def test_run_apt_update_with_force_apt_update_if_sources_changed(self):
        """
        L{PackageReporter.run_apt_update} forces an apt-update run if the APT
        sources.list file has changed.

        """
        self.assertEqual(self.reporter.sources_list_filename,
                         "/etc/apt/sources.list")
        self.reporter.sources_list_filename = self.makeFile("deb ftp://url ./")
        self._make_fake_apt_update()

        result = self.reporter.run_apt_update()

        def callback(args):
            out, err, code = args
            self.assertEqual("output", out)

        result.addCallback(callback)
        self.reactor.advance(0)
        return result

    def test_run_apt_update_warns_about_failures(self):
        """
        The L{PackageReporter.run_apt_update} method should log a warning in
        case apt-update terminates with a non-zero exit code.
        """
        self._make_fake_apt_update(code=2)
        warning_patcher = mock.patch.object(reporter.logging, "warning")
        warning_mock = warning_patcher.start()
        self.addCleanup(warning_patcher.stop)

        result = self.reporter.run_apt_update()

        def callback(args):
            out, err, code = args
            self.assertEqual("output", out)
            self.assertEqual("error", err)
            self.assertEqual(2, code)
            warning_mock.assert_called_once_with(
                "'%s' exited with status 2 (error)" %
                self.reporter.apt_update_filename)

        result.addCallback(callback)
        self.reactor.advance(0)
        return result

    @mock.patch("logging.warning", return_value=None)
    def test_run_apt_update_warns_about_lock_failure(self, logging_mock):
        """
        The L{PackageReporter.run_apt_update} method logs a warnings when
        apt-update fails acquiring the lock.
        """
        self._make_fake_apt_update(code=100)

        spawn_patcher = mock.patch.object(
            reporter,
            "spawn_process",
            side_effect=[
                # Simulate series of failures to acquire the apt lock.
                succeed((b'', b'', 100)),
                succeed((b'', b'', 100)),
                succeed((b'', b'', 100))])
        spawn_patcher.start()
        self.addCleanup(spawn_patcher.stop)

        result = self.reporter.run_apt_update()

        def callback(args):
            out, err, code = args
            self.assertEqual("", out)
            self.assertEqual("", err)
            self.assertEqual(100, code)

        result.addCallback(callback)
        self.reactor.advance(60)
        message = "Could not acquire the apt lock. Retrying in {} seconds."
        calls = [mock.call(message.format(20)),
                 mock.call(message.format(40)),
                 mock.call("'{}' exited with status 1000 ()".format(
                     self.reporter.apt_update_filename))]
        logging_mock.has_calls(calls)
        return result

    def test_run_apt_update_stops_retrying_after_lock_acquired(self):
        """
        When L{PackageReporter.run_apt_update} method successfully acquires the
        lock, it will stop retrying.
        """
        self._make_fake_apt_update(code=100)

        warning_patcher = mock.patch.object(reporter.logging, "warning")
        warning_mock = warning_patcher.start()
        self.addCleanup(warning_patcher.stop)

        spawn_patcher = mock.patch.object(
            reporter,
            "spawn_process",
            side_effect=[
                # Simulate a failed apt lock grab then a successful one.
                succeed((b'', b'', 100)),
                succeed((b'output', b'error', 0))])
        spawn_patcher.start()
        self.addCleanup(spawn_patcher.stop)

        result = self.reporter.run_apt_update()

        def callback(args):
            out, err, code = args
            self.assertEqual("output", out)
            self.assertEqual("error", err)
            self.assertEqual(0, code)
            warning_mock.assert_called_once_with(
                "Could not acquire the apt lock. Retrying in 20 seconds.")

        result.addCallback(callback)
        self.reactor.advance(20)
        return result

    def test_run_apt_update_report_timestamp(self):
        """
        The package-report-result message includes a timestamp of the apt
        update run.
        """
        message_store = self.broker_service.message_store
        message_store.set_accepted_types(["package-reporter-result"])
        self._make_fake_apt_update(err="")
        deferred = Deferred()

        def do_test():
            self.reactor.advance(10)
            result = self.reporter.run_apt_update()

            def callback(ignore):
                self.assertMessages(
                    message_store.get_pending_messages(),
                    [{"type": "package-reporter-result",
                      "report-timestamp": 10.0, "code": 0, "err": u""}])
            result.addCallback(callback)
            self.reactor.advance(0)
            result.chainDeferred(deferred)

        reactor.callWhenRunning(do_test)
        return deferred

    def test_run_apt_update_report_apt_failure(self):
        """
        If L{PackageReporter.run_apt_update} fails, a message is sent to the
        server reporting the error, to be able to fix the problem centrally.
        """
        message_store = self.broker_service.message_store
        message_store.set_accepted_types(["package-reporter-result"])
        self._make_fake_apt_update(code=2)
        deferred = Deferred()

        def do_test():
            result = self.reporter.run_apt_update()

            def callback(ignore):
                self.assertMessages(
                    message_store.get_pending_messages(),
                    [{"type": "package-reporter-result",
                      "report-timestamp": 0.0, "code": 2, "err": u"error"}])
            result.addCallback(callback)
            self.reactor.advance(0)
            result.chainDeferred(deferred)

        reactor.callWhenRunning(do_test)
        return deferred

    def test_run_apt_update_report_no_sources(self):
        """
        L{PackageReporter.run_apt_update} reports a failure if apt succeeds but
        there are no APT sources defined. APT doesn't fail if there are no
        sources, but we fake a failure in order to re-use the
        PackageReporterAlert on the server.
        """
        self.facade.reset_channels()
        message_store = self.broker_service.message_store
        message_store.set_accepted_types(["package-reporter-result"])
        self._make_fake_apt_update()
        deferred = Deferred()

        def do_test():
            result = self.reporter.run_apt_update()

            def callback(ignore):
                error = "There are no APT sources configured in %s or %s." % (
                    self.reporter.sources_list_filename,
                    self.reporter.sources_list_directory)
                self.assertMessages(
                    message_store.get_pending_messages(),
                    [{"type": "package-reporter-result",
                      "report-timestamp": 0.0, "code": 1, "err": error}])
            result.addCallback(callback)
            self.reactor.advance(0)
            result.chainDeferred(deferred)

        reactor.callWhenRunning(do_test)
        return deferred

    def test_run_apt_update_report_apt_failure_no_sources(self):
        """
        If L{PackageReporter.run_apt_update} fails and there are no
        APT sources configured, the APT error takes precedence.
        """
        self.facade.reset_channels()
        message_store = self.broker_service.message_store
        message_store.set_accepted_types(["package-reporter-result"])
        self._make_fake_apt_update(code=2)
        deferred = Deferred()

        def do_test():
            result = self.reporter.run_apt_update()

            def callback(ignore):
                self.assertMessages(
                    message_store.get_pending_messages(),
                    [{"type": "package-reporter-result",
                      "report-timestamp": 0.0, "code": 2, "err": u"error"}])
            result.addCallback(callback)
            self.reactor.advance(0)
            result.chainDeferred(deferred)

        reactor.callWhenRunning(do_test)
        return deferred

    def test_run_apt_update_report_success(self):
        """
        L{PackageReporter.run_apt_update} also reports success to be able to
        know the proper state of the client.
        """
        message_store = self.broker_service.message_store
        message_store.set_accepted_types(["package-reporter-result"])
        self._make_fake_apt_update(err="message")
        deferred = Deferred()

        def do_test():
            result = self.reporter.run_apt_update()

            def callback(ignore):
                self.assertMessages(
                    message_store.get_pending_messages(),
                    [{"type": "package-reporter-result",
                      "report-timestamp": 0.0, "code": 0, "err": u"message"}])
            result.addCallback(callback)
            self.reactor.advance(0)
            result.chainDeferred(deferred)

        reactor.callWhenRunning(do_test)
        return deferred

    def test_run_apt_update_no_run_in_interval(self):
        """
        The L{PackageReporter.run_apt_update} logs a debug message if
        apt-update doesn't run because interval has not passed.
        """
        self.reporter._apt_sources_have_changed = lambda: False
        self.makeFile("", path=self.config.update_stamp_filename)

        debug_patcher = mock.patch.object(reporter.logging, "debug")
        debug_mock = debug_patcher.start()
        self.addCleanup(debug_patcher.stop)

        deferred = Deferred()

        def do_test():
            result = self.reporter.run_apt_update()

            def callback(args):
                out, err, code = args
                self.assertEqual("", out)
                self.assertEqual("", err)
                self.assertEqual(0, code)
                debug_mock.assert_called_once_with(
                    ("'%s' didn't run, conditions not met"
                     ) % self.reporter.apt_update_filename)
            result.addCallback(callback)
            self.reactor.advance(0)
            result.chainDeferred(deferred)

        reactor.callWhenRunning(do_test)
        return deferred

    def test_run_apt_update_no_run_update_notifier_stamp_in_interval(self):
        """
        The L{PackageReporter.run_apt_update} doesn't runs apt-update if the
        interval is passed but the stamp file from update-notifier-common
        reports that 'apt-get update' has been run in the interval.
        """
        self.reporter._apt_sources_have_changed = lambda: False

        # The interval for the apt-update stamp file is expired.
        self.makeFile("", path=self.config.update_stamp_filename)
        expired_time = time.time() - self.config.apt_update_interval - 1
        os.utime(
            self.config.update_stamp_filename, (expired_time, expired_time))
        # The interval for the update-notifier-common stamp file is not
        # expired.
        self.reporter.update_notifier_stamp = self.makeFile("")

        debug_patcher = mock.patch.object(reporter.logging, "debug")
        debug_mock = debug_patcher.start()
        self.addCleanup(debug_patcher.stop)

        deferred = Deferred()

        def do_test():
            result = self.reporter.run_apt_update()

            def callback(args):
                out, err, code = args
                self.assertEqual("", out)
                self.assertEqual("", err)
                self.assertEqual(0, code)
                debug_mock.assert_called_once_with(
                    ("'%s' didn't run, conditions not met"
                     ) % self.reporter.apt_update_filename)
            result.addCallback(callback)
            self.reactor.advance(0)
            result.chainDeferred(deferred)

        reactor.callWhenRunning(do_test)
        return deferred

    def test_run_apt_update_runs_interval_expired(self):
        """
        L{PackageReporter.run_apt_update} runs if both apt-update and
        update-notifier-common stamp files are present and the time
        interval has passed.
        """
        self.reporter._apt_sources_have_changed = lambda: False

        expired_time = time.time() - self.config.apt_update_interval - 1
        # The interval for both stamp files is expired.
        self.makeFile("", path=self.config.update_stamp_filename)
        os.utime(
            self.config.update_stamp_filename, (expired_time, expired_time))
        self.reporter.update_notifier_stamp = self.makeFile("")
        os.utime(
            self.reporter.update_notifier_stamp, (expired_time, expired_time))

        message_store = self.broker_service.message_store
        message_store.set_accepted_types(["package-reporter-result"])
        self._make_fake_apt_update(err="message")
        deferred = Deferred()

        def do_test():
            result = self.reporter.run_apt_update()

            def callback(ignore):
                self.assertMessages(
                    message_store.get_pending_messages(),
                    [{"type": "package-reporter-result",
                      "report-timestamp": 0.0, "code": 0, "err": u"message"}])
            result.addCallback(callback)
            self.reactor.advance(0)
            result.chainDeferred(deferred)

        reactor.callWhenRunning(do_test)
        return deferred

    def test_run_apt_update_touches_stamp_file(self):
        """
        The L{PackageReporter.run_apt_update} method touches a stamp file
        after running the apt-update wrapper.
        """
        self.reporter.sources_list_filename = "/I/Dont/Exist"
        self._make_fake_apt_update()
        deferred = Deferred()

        def do_test():
            result = self.reporter.run_apt_update()

            def callback(ignored):
                self.assertTrue(
                    os.path.exists(self.config.update_stamp_filename))
            result.addCallback(callback)
            self.reactor.advance(0)
            result.chainDeferred(deferred)

        reactor.callWhenRunning(do_test)
        return deferred

    @mock.patch("landscape.client.package.reporter.spawn_process",
                return_value=succeed((b"", b"", 0)))
    def test_run_apt_update_honors_http_proxy(self, mock_spawn_process):
        """
        The PackageReporter.run_apt_update method honors the http_proxy
        config when calling the apt-update wrapper.
        """
        self.config.http_proxy = "http://proxy_server:8080"
        self.reporter.sources_list_filename = "/I/Dont/Exist"

        update_result = self.reporter.run_apt_update()
        # run_apt_update uses reactor.call_later so advance a bit
        self.reactor.advance(0)
        self.successResultOf(update_result)

        mock_spawn_process.assert_called_once_with(
            self.reporter.apt_update_filename,
            env={"http_proxy": "http://proxy_server:8080"})

    @mock.patch("landscape.client.package.reporter.spawn_process",
                return_value=succeed((b"", b"", 0)))
    def test_run_apt_update_honors_https_proxy(self, mock_spawn_process):
        """
        The PackageReporter.run_apt_update method honors the https_proxy
        config when calling the apt-update wrapper.
        """
        self.config.https_proxy = "http://proxy_server:8443"
        self.reporter.sources_list_filename = "/I/Dont/Exist"

        update_result = self.reporter.run_apt_update()
        # run_apt_update uses reactor.call_later, so advance a bit
        self.reactor.advance(0)
        self.successResultOf(update_result)

        mock_spawn_process.assert_called_once_with(
            self.reporter.apt_update_filename,
            env={"https_proxy": "http://proxy_server:8443"})

    def test_run_apt_update_error_on_cache_file(self):
        """
        L{PackageReporter.run_apt_update} succeeds if the command fails because
        one of the cache files is not found. This generally occurs if 'apt-get
        clean' has been concurrently run with 'apt-get update'.  This is not an
        issue for the package lists update.
        """
        message_store = self.broker_service.message_store
        message_store.set_accepted_types(["package-reporter-result"])
        self._make_fake_apt_update(
            code=2, out="not important",
            err=("E: Problem renaming the file "
                 "/var/cache/apt/pkgcache.bin.6ZsRSX to "
                 "/var/cache/apt/pkgcache.bin - rename (2: No such file "
                 "or directory)\n"
                 "W: You may want to run apt-get update to correct these "
                 "problems"))
        deferred = Deferred()

        def do_test():
            result = self.reporter.run_apt_update()

            def callback(ignore):
                self.assertMessages(
                    message_store.get_pending_messages(),
                    [{"type": "package-reporter-result",
                      "report-timestamp": 0.0, "code": 0, "err": u""}])
            result.addCallback(callback)
            self.reactor.advance(0)
            result.chainDeferred(deferred)

        reactor.callWhenRunning(do_test)
        return deferred

    def test_run_apt_update_error_no_cache_files(self):
        """
        L{PackageReporter.run_apt_update} succeeds if the command fails because
        cache files are not found.
        """
        message_store = self.broker_service.message_store
        message_store.set_accepted_types(["package-reporter-result"])
        self._make_fake_apt_update(
            code=2, out="not important",
            err=("E: Problem renaming the file "
                 "/var/cache/apt/srcpkgcache.bin.Pw1Zxy to "
                 "/var/cache/apt/srcpkgcache.bin - rename (2: No such file "
                 "or directory)\n"
                 "E: Problem renaming the file "
                 "/var/cache/apt/pkgcache.bin.wz8ooS to "
                 "/var/cache/apt/pkgcache.bin - rename (2: No such file "
                 "or directory)\n"
                 "E: The package lists or status file could not be parsed "
                 "or opened."))

        deferred = Deferred()

        def do_test():
            result = self.reporter.run_apt_update()

            def callback(ignore):
                self.assertMessages(
                    message_store.get_pending_messages(),
                    [{"type": "package-reporter-result",
                      "report-timestamp": 0.0, "code": 0, "err": u""}])
            result.addCallback(callback)
            self.reactor.advance(0)
            result.chainDeferred(deferred)

        reactor.callWhenRunning(do_test)
        return deferred

    def test_config_apt_update_interval(self):
        """
        L{PackageReporter} uses the C{apt_update_interval} configuration
        parameter to check the age of the update stamp file.
        """
        self.config.apt_update_interval = 1234
        message_store = self.broker_service.message_store
        message_store.set_accepted_types(["package-reporter-result"])
        intervals = []

        def apt_update_timeout_expired(interval):
            intervals.append(interval)
            return False

        deferred = Deferred()

        self.reporter._apt_sources_have_changed = lambda: False
        self.reporter._apt_update_timeout_expired = apt_update_timeout_expired

        def do_test():
            result = self.reporter.run_apt_update()

            def callback(ignore):
                self.assertMessages(message_store.get_pending_messages(), [])
                self.assertEqual([1234], intervals)
            result.addCallback(callback)
            result.chainDeferred(deferred)

        reactor.callWhenRunning(do_test)
        return deferred

    def test_detect_packages_doesnt_creates_stamp_files(self):
        """
        Stamp file is created if not present, and the method returns
        that the information changed in that case.
        """
        result = self.reporter._package_state_has_changed()
        self.assertTrue(result)
        self.assertFalse(os.path.exists(self.check_stamp_file))

    def test_detect_packages_changes_returns_false_if_unchanged(self):
        """
        If a monitored file is not changed (touched), the method returns
        False.
        """
        touch_file(self.check_stamp_file, offset_seconds=2)
        result = self.reporter._package_state_has_changed()
        self.assertFalse(result)

    def test_detect_packages_changes_returns_true_if_changed(self):
        """
        If a monitored file is changed (touched), the method returns True.
        """
        status_file = apt_pkg.config.find_file("dir::state::status")

        touch_file(status_file)
        touch_file(self.check_stamp_file)

        touch_file(status_file)
        result = self.reporter._package_state_has_changed()
        self.assertTrue(result)

    def test_detect_packages_changes_works_for_list_files(self):
        """
        If a list file is touched, the method returns True.
        """
        status_file = apt_pkg.config.find_file("dir::state::status")
        touch_file(status_file)
        touch_file(self.check_stamp_file)

        list_dir = apt_pkg.config.find_dir("dir::state::lists")
        # There are no *Packages files in the fixures, let's create one.
        touch_file(os.path.join(list_dir, "testPackages"))

        result = self.reporter._package_state_has_changed()
        self.assertTrue(result)

    def test_detect_packages_changes_detects_removed_list_file(self):
        """
        If a list file is removed from the system, the method returns True.
        """
        list_dir = apt_pkg.config.find_dir("dir::state::lists")
        test_file = os.path.join(list_dir, "testPackages")
        touch_file(test_file)
        touch_file(self.check_stamp_file)

        os.remove(test_file)
        result = self.reporter._package_state_has_changed()
        self.assertTrue(result)

    def test_is_release_upgrader_running(self):
        """
        The L{PackageReporter._is_release_upgrader_running} method should
        return True if the simle heuristics detects a release upgrader
        running concurrently.
        """
        # no 'release upgrader running'
        self.assertFalse(self.reporter._is_release_upgrader_running())
        # fake 'release ugrader' running with non-root UID
        p = subprocess.Popen([reporter.PYTHON_BIN, '-c',
                              'import time; time.sleep(10)',
                              reporter.RELEASE_UPGRADER_PATTERN + "12345"])
        self.assertFalse(self.reporter._is_release_upgrader_running())
        # fake 'release upgrader' running
        reporter.UID_ROOT = "%d" % os.getuid()
        self.assertTrue(self.reporter._is_release_upgrader_running())
        p.terminate()


class GlobalPackageReporterAptTest(LandscapeTest):

    helpers = [AptFacadeHelper, SimpleRepositoryHelper, BrokerServiceHelper]

    def setUp(self):
        super(GlobalPackageReporterAptTest, self).setUp()
        self.store = FakePackageStore(self.makeFile())
        self.config = PackageReporterConfiguration()
        self.reactor = FakeReactor()
        self.reporter = FakeGlobalReporter(
            self.store, self.facade, self.remote, self.config, self.reactor)
        # Assume update-notifier-common stamp file is not present by
        # default.
        self.reporter.update_notifier_stamp = "/Not/Existing"
        self.config.data_path = self.makeDir()
        os.mkdir(self.config.package_directory)

    def test_store_messages(self):
        """
        L{FakeGlobalReporter} stores messages which are sent.
        """
        message_store = self.broker_service.message_store
        message_store.set_accepted_types(["package-reporter-result"])
        self.reporter.apt_update_filename = self.makeFile(
            "#!/bin/sh\necho -n error >&2\necho -n output\nexit 0")
        os.chmod(self.reporter.apt_update_filename, 0o755)
        deferred = Deferred()

        def do_test():
            self.reporter.get_session_id()
            result = self.reporter.run_apt_update()
            self.reactor.advance(0)

            def callback(ignore):
                message = {"type": "package-reporter-result",
                           "report-timestamp": 0.0, "code": 0, "err": u"error"}
                self.assertMessages(
                    message_store.get_pending_messages(), [message])
                stored = list(self.store._db.execute(
                    "SELECT id, data FROM message").fetchall())
                self.assertEqual(1, len(stored))
                self.assertEqual(1, stored[0][0])
                self.assertEqual(message, bpickle.loads(bytes(stored[0][1])))
            result.addCallback(callback)
            result.chainDeferred(deferred)

        reactor.callWhenRunning(do_test)
        return deferred


class FakePackageReporterTest(LandscapeTest):

    helpers = [EnvironSaverHelper, BrokerServiceHelper]

    def setUp(self):
        super(FakePackageReporterTest, self).setUp()
        self.store = FakePackageStore(self.makeFile())
        global_file = self.makeFile()
        self.global_store = FakePackageStore(global_file)
        os.environ["FAKE_PACKAGE_STORE"] = global_file
        self.config = PackageReporterConfiguration()
        self.reactor = FakeReactor()
        self.reporter = FakeReporter(
            self.store, None, self.remote, self.config, self.reactor)
        self.config.data_path = self.makeDir()
        os.mkdir(self.config.package_directory)

    def test_send_messages(self):
        """
        L{FakeReporter} sends messages stored in the global store specified by
        C{FAKE_PACKAGE_STORE}.
        """
        message_store = self.broker_service.message_store
        message_store.set_accepted_types(["package-reporter-result"])
        message = {"type": "package-reporter-result",
                   "code": 0, "err": u"error"}
        self.global_store.save_message(message)

        def check(ignore):
            messages = message_store.get_pending_messages()
            self.assertMessages(
                messages, [message])
            stored = list(self.store._db.execute(
                "SELECT id FROM message").fetchall())
            self.assertEqual(1, len(stored))
            self.assertEqual(1, stored[0][0])

        deferred = self.reporter.run()
        deferred.addCallback(check)
        return deferred

    def test_filter_message_type(self):
        """
        L{FakeReporter} only sends one message of each type per run.
        """
        message_store = self.broker_service.message_store
        message_store.set_accepted_types(["package-reporter-result"])
        message1 = {"type": "package-reporter-result",
                    "code": 0, "err": u"error"}
        self.global_store.save_message(message1)
        message2 = {"type": "package-reporter-result",
                    "code": 1, "err": u"error"}
        self.global_store.save_message(message2)

        def check1(ignore):
            self.assertMessages(
                message_store.get_pending_messages(), [message1])
            stored = list(self.store._db.execute(
                "SELECT id FROM message").fetchall())
            self.assertEqual(1, stored[0][0])
            return self.reporter.run().addCallback(check2)

        def check2(ignore):
            self.assertMessages(
                message_store.get_pending_messages(), [message1, message2])
            stored = list(self.store._db.execute(
                "SELECT id FROM message").fetchall())
            self.assertEqual(2, len(stored))
            self.assertEqual(1, stored[0][0])
            self.assertEqual(2, stored[1][0])

        return self.reporter.run().addCallback(check1)


class EqualsHashes(object):

    def __init__(self, *hashes):
        self._hashes = sorted(hashes)

    def __eq__(self, other):
        return self._hashes == sorted(other)
