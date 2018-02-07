import os

from mock import patch, Mock, ANY

from twisted.internet.defer import Deferred, fail, succeed

from landscape.lib.apt.package.facade import AptFacade
from landscape.lib.apt.package.store import HashIdStore, PackageStore
from landscape.lib.apt.package.testing import AptFacadeHelper
from landscape.lib.lock import lock_path
from landscape.lib.testing import EnvironSaverHelper, FakeReactor
from landscape.client.broker.amp import RemoteBrokerConnector
from landscape.client.package.taskhandler import (
    PackageTaskHandlerConfiguration, PackageTaskHandler, run_task_handler,
    LazyRemoteBroker)
from landscape.client.tests.helpers import LandscapeTest, BrokerServiceHelper


SAMPLE_LSB_RELEASE = "DISTRIB_CODENAME=codename\n"


class PackageTaskHandlerConfigurationTest(LandscapeTest):

    def test_update_stamp_option(self):
        """
        L{PackageReporterConfiguration.update_stamp_filename} points
        to the update-stamp file.
        """
        config = PackageTaskHandlerConfiguration()
        self.assertEqual(
            config.update_stamp_filename,
            "/var/lib/landscape/client/package/update-stamp")


class PackageTaskHandlerTest(LandscapeTest):

    helpers = [AptFacadeHelper, EnvironSaverHelper, BrokerServiceHelper]

    def setUp(self):
        super(PackageTaskHandlerTest, self).setUp()
        self.config = PackageTaskHandlerConfiguration()
        self.store = PackageStore(self.makeFile())
        self.reactor = FakeReactor()
        self.handler = PackageTaskHandler(
            self.store, self.facade, self.remote, self.config, self.reactor)

    def test_use_hash_id_db(self):

        # We don't have this hash=>id mapping
        self.assertEqual(self.store.get_hash_id(b"hash"), None)

        # An appropriate hash=>id database is available
        self.config.data_path = self.makeDir()
        os.makedirs(os.path.join(self.config.data_path, "package", "hash-id"))
        hash_id_db_filename = os.path.join(self.config.data_path, "package",
                                           "hash-id", "uuid_codename_arch")
        HashIdStore(hash_id_db_filename).set_hash_ids({b"hash": 123})

        # Fake uuid, codename and arch
        message_store = self.broker_service.message_store
        message_store.set_server_uuid("uuid")
        self.handler.lsb_release_filename = self.makeFile(SAMPLE_LSB_RELEASE)
        self.facade.set_arch("arch")

        # Attach the hash=>id database to our store
        result = self.handler.use_hash_id_db()

        # Now we do have the hash=>id mapping
        def callback(ignored):
            self.assertEqual(self.store.get_hash_id(b"hash"), 123)
        result.addCallback(callback)

        return result

    @patch("logging.warning")
    def test_use_hash_id_db_undetermined_codename(self, logging_mock):

        # Fake uuid
        message_store = self.broker_service.message_store
        message_store.set_server_uuid("uuid")

        # Undetermined codename
        self.handler.lsb_release_filename = self.makeFile("Foo=bar")

        # Go!
        result = self.handler.use_hash_id_db()

        # The failure should be properly logged
        logging_mock.assert_called_with(
            "Couldn't determine which hash=>id database to use: "
            "missing code-name key in %s" % self.handler.lsb_release_filename)

        return result

    @patch("logging.warning")
    def test_use_hash_id_db_wit_non_existing_lsb_release(self, logging_mock):

        # Fake uuid
        message_store = self.broker_service.message_store
        message_store.set_server_uuid("uuid")

        # Undetermined codename
        self.handler.lsb_release_filename = self.makeFile()

        # Go!
        result = self.handler.use_hash_id_db()

        # The failure should be properly logged
        logging_mock.assert_called_with(
            "Couldn't determine which hash=>id database to use: "
            "[Errno 2] No such file or directory: '%s'" %
            self.handler.lsb_release_filename)

        return result

    def test_wb_determine_hash_id_db_filename_server_uuid_is_none(self):
        """
        The L{PaclageTaskHandler._determine_hash_id_db_filename} method should
        return C{None} if the server uuid is C{None}.
        """
        message_store = self.broker_service.message_store
        message_store.set_server_uuid(None)

        result = self.handler._determine_hash_id_db_filename()

        def callback(hash_id_db_filename):
            self.assertIs(hash_id_db_filename, None)
        result.addCallback(callback)
        return result

    @patch("logging.warning")
    def test_use_hash_id_db_undetermined_server_uuid(self, logging_mock):
        """
        If the server-uuid can't be determined for some reason, no hash-id db
        should be used and the failure should be properly logged.
        """
        message_store = self.broker_service.message_store
        message_store.set_server_uuid(None)

        result = self.handler.use_hash_id_db()

        logging_mock.assert_called_with(
            "Couldn't determine which hash=>id database to use: "
            "server UUID not available")

        def callback(ignore):
            self.assertFalse(self.store.has_hash_id_db())
        result.addCallback(callback)
        return result

    def test_get_session_id(self):
        """
        L{get_session_id} returns a session ID.
        """

        def assertHaveSessionId(session_id):
            self.assertTrue(session_id is not None)

        result = self.handler.get_session_id()
        result.addCallback(assertHaveSessionId)
        return result

    @patch("logging.warning")
    def test_use_hash_id_db_undetermined_arch(self, logging_mock):

        # Fake uuid and codename
        message_store = self.broker_service.message_store
        message_store.set_server_uuid("uuid")
        self.handler.lsb_release_filename = self.makeFile(SAMPLE_LSB_RELEASE)

        # Undetermined arch
        self.facade.set_arch(None)

        # Go!
        result = self.handler.use_hash_id_db()

        # The failure should be properly logged
        logging_mock.assert_called_with(
            "Couldn't determine which hash=>id database to use: "
            "unknown dpkg architecture")

        return result

    def test_use_hash_id_db_database_not_found(self):

        # Clean path, we don't have an appropriate hash=>id database
        self.config.data_path = self.makeDir()

        # Fake uuid, codename and arch
        message_store = self.broker_service.message_store
        message_store.set_server_uuid("uuid")
        self.handler.lsb_release_filename = self.makeFile(SAMPLE_LSB_RELEASE)
        self.facade.set_arch("arch")

        # Let's try
        result = self.handler.use_hash_id_db()

        # We go on without the hash=>id database
        def callback(ignored):
            self.assertFalse(self.store.has_hash_id_db())
        result.addCallback(callback)

        return result

    @patch("logging.warning")
    def test_use_hash_id_with_invalid_database(self, logging_mock):

        # Let's say the appropriate database is actually garbage
        self.config.data_path = self.makeDir()
        os.makedirs(os.path.join(self.config.data_path, "package", "hash-id"))
        hash_id_db_filename = os.path.join(self.config.data_path, "package",
                                           "hash-id", "uuid_codename_arch")
        open(hash_id_db_filename, "w").write("junk")

        # Fake uuid, codename and arch
        message_store = self.broker_service.message_store
        message_store.set_server_uuid("uuid")
        self.handler.lsb_release_filename = self.makeFile(SAMPLE_LSB_RELEASE)
        self.facade.set_arch("arch")

        # Try to attach it
        result = self.handler.use_hash_id_db()

        # The failure should be properly logged
        logging_mock.assert_called_with(
            "Invalid hash=>id database %s" % hash_id_db_filename)

        # We remove the broken hash=>id database and go on without it
        def callback(ignored):
            self.assertFalse(os.path.exists(hash_id_db_filename))
            self.assertFalse(self.store.has_hash_id_db())
        result.addCallback(callback)

        return result

    def test_run(self):
        self.handler.handle_tasks = Mock(return_value="WAYO!")
        self.assertEqual(self.handler.run(), "WAYO!")

    def test_handle_tasks(self):
        queue_name = PackageTaskHandler.queue_name

        self.store.add_task(queue_name, 0)
        self.store.add_task(queue_name, 1)
        self.store.add_task(queue_name, 2)

        results = [Deferred() for i in range(3)]

        stash = []

        def handle_task(task):
            result = results[task.data]
            result.addCallback(lambda x: stash.append(task.data))
            return result

        self.handler.handle_task = Mock(side_effect=handle_task)

        handle_tasks_result = self.handler.handle_tasks()

        self.assertEqual(stash, [])

        results[1].callback(None)
        self.assertEqual(stash, [])
        self.assertEqual(self.store.get_next_task(queue_name).data, 0)

        results[0].callback(None)
        self.assertEqual(stash, [0, 1])
        self.assertTrue(handle_tasks_result.called)
        self.assertEqual(self.store.get_next_task(queue_name).data, 2)

        results[2].callback(None)
        self.assertEqual(stash, [0, 1, 2])
        self.assertTrue(handle_tasks_result.called)
        self.assertEqual(self.store.get_next_task(queue_name), None)

        handle_tasks_result = self.handler.handle_tasks()
        self.assertTrue(handle_tasks_result.called)
        self.assertEqual(3, self.handler.handle_task.call_count)

    def test_handle_py2_tasks(self):
        """Check py27-serialized messages-types are decoded."""
        queue_name = PackageTaskHandler.queue_name

        self.store.add_task(queue_name, {"type": b"spam"})
        self.store.add_task(queue_name, {"type": "ham"})

        stash = []

        def handle_task(task):
            stash.append(task.data["type"])
            return succeed(None)

        self.handler.handle_task = Mock(side_effect=handle_task)

        self.handler.handle_tasks()
        self.assertEqual(stash, ["spam", "ham"])
        self.assertEqual(2, self.handler.handle_task.call_count)

    def test_handle_tasks_hooks_errback(self):
        queue_name = PackageTaskHandler.queue_name

        self.store.add_task(queue_name, 0)

        class MyException(Exception):
            pass

        def handle_task(task):
            result = Deferred()
            result.errback(MyException())
            return result

        self.handler.handle_task = Mock(side_effect=handle_task)

        stash = []
        handle_tasks_result = self.handler.handle_tasks()
        handle_tasks_result.addErrback(stash.append)

        self.assertEqual(len(stash), 1)
        self.assertEqual(stash[0].type, MyException)

    def test_default_handle_task(self):
        result = self.handler.handle_task(None)
        self.assertTrue(isinstance(result, Deferred))
        self.assertTrue(result.called)

    @patch("os.umask")
    @patch("landscape.client.package.taskhandler.RemoteBrokerConnector")
    @patch("landscape.client.package.taskhandler.LandscapeReactor")
    @patch("landscape.client.package.taskhandler.init_logging")
    @patch("landscape.client.package.taskhandler.lock_path")
    def test_run_task_handler(self, lock_path_mock, init_logging_mock,
                              reactor_class_mock, connector_class_mock, umask):
        """
        The L{run_task_handler} function creates and runs the given task
        handler with the proper arguments.
        """
        # Mock the different parts of run_task_handler(), to ensure it
        # does what it's supposed to do, without actually creating files
        # and starting processes.

        # This is a slightly lengthy one, so bear with me.

        # Prepare the mock objects.
        connector_mock = Mock(name="mock-connector")
        connector_class_mock.return_value = connector_mock

        handler_args = []

        class HandlerMock(PackageTaskHandler):

            def __init__(self, *args):
                handler_args.extend(args)
                super(HandlerMock, self).__init__(*args)

        call_when_running = []
        reactor_mock = Mock(name="mock-reactor")
        reactor_class_mock.return_value = reactor_mock
        reactor_mock.call_when_running.side_effect = call_when_running.append
        reactor_mock.run.side_effect = lambda: call_when_running[0]()

        def assert_task_handler(ignored):

            store, facade, broker, config, reactor = handler_args

            # Verify the arguments passed to the reporter constructor.
            self.assertEqual(type(store), PackageStore)
            self.assertEqual(type(facade), AptFacade)
            self.assertEqual(type(broker), LazyRemoteBroker)
            self.assertEqual(type(config), PackageTaskHandlerConfiguration)
            self.assertIn("mock-reactor", repr(reactor))

            # Let's see if the store path is where it should be.
            filename = os.path.join(self.data_path, "package", "database")
            store.add_available([1, 2, 3])
            other_store = PackageStore(filename)
            self.assertEqual(other_store.get_available(), [1, 2, 3])

            # Check the hash=>id database directory as well
            self.assertTrue(os.path.exists(
                os.path.join(self.data_path, "package", "hash-id")))

        result = run_task_handler(HandlerMock, ["-c", self.config_filename])

        # Assert that we acquired a lock as the same task handler should
        # never have two instances running in parallel.  The 'default'
        # below comes from the queue_name attribute.
        lock_path_mock.assert_called_once_with(
            os.path.join(self.data_path, "package", "default.lock"))

        # Once locking is done, it's safe to start logging without
        # corrupting the file.  We don't want any output unless it's
        # breaking badly, so the quiet option should be set.
        init_logging_mock.assert_called_once_with(ANY, "handler-mock")

        connector_mock.disconnect.assert_called_once_with()
        reactor_mock.call_later.assert_called_once_with(0, ANY)

        # We also expect the umask to be set appropriately before running the
        # commands
        umask.assert_called_once_with(0o22)

        return result.addCallback(assert_task_handler)

    def test_run_task_handler_when_already_locked(self):

        lock_path(os.path.join(self.data_path, "package", "default.lock"))

        try:
            run_task_handler(PackageTaskHandler, ["-c", self.config_filename])
        except SystemExit as e:
            self.assertIn("default is already running", str(e))
        else:
            self.fail("SystemExit not raised")

    def test_run_task_handler_when_already_locked_and_quiet_option(self):
        lock_path(os.path.join(self.data_path, "package", "default.lock"))

        try:
            run_task_handler(PackageTaskHandler,
                             ["-c", self.config_filename, "--quiet"])
        except SystemExit as e:
            self.assertEqual(str(e), "")
        else:
            self.fail("SystemExit not raised")

    @patch("landscape.client.package.taskhandler.init_logging")
    def test_errors_are_printed_and_exit_program(self, init_logging_mock):

        class MyException(Exception):
            pass

        self.log_helper.ignore_errors(MyException)

        class HandlerMock(PackageTaskHandler):

            def run(self):
                return fail(MyException("Hey error"))

        # Ok now for some real stuff

        def assert_log(ignored):
            self.assertIn("MyException", self.logfile.getvalue())
            init_logging_mock.assert_called_once_with(ANY, "handler-mock")

        result = run_task_handler(HandlerMock,
                                  ["-c", self.config_filename],
                                  reactor=FakeReactor())

        return result.addCallback(assert_log)


class LazyRemoteBrokerTest(LandscapeTest):

    helpers = [BrokerServiceHelper]

    def test_wb_is_lazy(self):
        """
        The L{LazyRemoteBroker} class doesn't initialize the actual remote
        broker until one of its attributes gets actually accessed.
        """
        reactor = FakeReactor()
        connector = RemoteBrokerConnector(reactor, self.broker_service.config)
        self.broker = LazyRemoteBroker(connector)
        self.assertIs(self.broker._remote, None)

        def close_connection(result):
            self.assertTrue(result)
            connector.disconnect()

        result = self.broker.ping()
        return result.addCallback(close_connection)
