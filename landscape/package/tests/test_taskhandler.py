import os

from twisted.internet import reactor
from twisted.internet.defer import Deferred, fail

from landscape.lib.lock import lock_path
from landscape.reactor import TwistedReactor
from landscape.broker.amp import RemoteBrokerConnector
from landscape.package.taskhandler import (
    PackageTaskHandlerConfiguration, PackageTaskHandler, run_task_handler,
    LazyRemoteBroker)
from landscape.package.facade import AptFacade
from landscape.package.store import HashIdStore, PackageStore
from landscape.package.tests.helpers import AptFacadeHelper
from landscape.tests.helpers import (
    LandscapeTest, BrokerServiceHelper, EnvironSaverHelper)
from landscape.tests.mocker import ANY, ARGS, MATCH


def ISTYPE(match_type):
    return MATCH(lambda arg: type(arg) is match_type)


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

        def set_up(ignored):
            self.config = PackageTaskHandlerConfiguration()
            self.store = PackageStore(self.makeFile())
            self.handler = PackageTaskHandler(
                self.store, self.facade, self.remote, self.config)

        result = super(PackageTaskHandlerTest, self).setUp()
        return result.addCallback(set_up)

    def test_use_hash_id_db(self):

        # We don't have this hash=>id mapping
        self.assertEqual(self.store.get_hash_id("hash"), None)

        # An appropriate hash=>id database is available
        self.config.data_path = self.makeDir()
        os.makedirs(os.path.join(self.config.data_path, "package", "hash-id"))
        hash_id_db_filename = os.path.join(self.config.data_path, "package",
                                           "hash-id", "uuid_codename_arch")
        HashIdStore(hash_id_db_filename).set_hash_ids({"hash": 123})

        # Fake uuid, codename and arch
        message_store = self.broker_service.message_store
        message_store.set_server_uuid("uuid")
        self.handler.lsb_release_filename = self.makeFile(SAMPLE_LSB_RELEASE)
        self.facade.set_arch("arch")

        # Attach the hash=>id database to our store
        self.mocker.replay()
        result = self.handler.use_hash_id_db()

        # Now we do have the hash=>id mapping
        def callback(ignored):
            self.assertEqual(self.store.get_hash_id("hash"), 123)
        result.addCallback(callback)

        return result

    def test_use_hash_id_db_undetermined_codename(self):

        # Fake uuid
        message_store = self.broker_service.message_store
        message_store.set_server_uuid("uuid")

        # Undetermined codename
        self.handler.lsb_release_filename = self.makeFile("Foo=bar")

        # The failure should be properly logged
        logging_mock = self.mocker.replace("logging.warning")
        logging_mock("Couldn't determine which hash=>id database to use: "
                     "missing code-name key in %s" %
                     self.handler.lsb_release_filename)
        self.mocker.result(None)

        # Go!
        self.mocker.replay()
        result = self.handler.use_hash_id_db()
        return result

    def test_use_hash_id_db_wit_non_existing_lsb_release(self):

        # Fake uuid
        message_store = self.broker_service.message_store
        message_store.set_server_uuid("uuid")

        # Undetermined codename
        self.handler.lsb_release_filename = self.makeFile()

        # The failure should be properly logged
        logging_mock = self.mocker.replace("logging.warning")
        logging_mock("Couldn't determine which hash=>id database to use: "
                     "[Errno 2] No such file or directory: '%s'" %
                     self.handler.lsb_release_filename)
        self.mocker.result(None)

        # Go!
        self.mocker.replay()
        result = self.handler.use_hash_id_db()
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

    def test_use_hash_id_db_undetermined_server_uuid(self):
        """
        If the server-uuid can't be determined for some reason, no hash-id db
        should be used and the failure should be properly logged.
        """
        message_store = self.broker_service.message_store
        message_store.set_server_uuid(None)

        logging_mock = self.mocker.replace("logging.warning")
        logging_mock("Couldn't determine which hash=>id database to use: "
                     "server UUID not available")
        self.mocker.result(None)
        self.mocker.replay()

        result = self.handler.use_hash_id_db()

        def callback(ignore):
            self.assertFalse(self.store.has_hash_id_db())
        result.addCallback(callback)
        return result

    def test_use_hash_id_db_undetermined_arch(self):

        # Fake uuid and codename
        message_store = self.broker_service.message_store
        message_store.set_server_uuid("uuid")
        self.handler.lsb_release_filename = self.makeFile(SAMPLE_LSB_RELEASE)

        # Undetermined arch
        self.facade.set_arch(None)

        # The failure should be properly logged
        logging_mock = self.mocker.replace("logging.warning")
        logging_mock("Couldn't determine which hash=>id database to use: "\
                     "unknown dpkg architecture")
        self.mocker.result(None)

        # Go!
        self.mocker.replay()
        result = self.handler.use_hash_id_db()

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
        self.mocker.replay()
        result = self.handler.use_hash_id_db()

        # We go on without the hash=>id database
        def callback(ignored):
            self.assertFalse(self.store.has_hash_id_db())
        result.addCallback(callback)

        return result

    def test_use_hash_id_with_invalid_database(self):

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

        # The failure should be properly logged
        logging_mock = self.mocker.replace("logging.warning")
        logging_mock("Invalid hash=>id database %s" % hash_id_db_filename)
        self.mocker.result(None)

        # Try to attach it
        self.mocker.replay()
        result = self.handler.use_hash_id_db()

        # We remove the broken hash=>id database and go on without it
        def callback(ignored):
            self.assertFalse(os.path.exists(hash_id_db_filename))
            self.assertFalse(self.store.has_hash_id_db())
        result.addCallback(callback)

        return result

    def test_run(self):
        handler_mock = self.mocker.patch(self.handler)
        handler_mock.handle_tasks()
        self.mocker.result("WAYO!")

        self.mocker.replay()

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

        handler_mock = self.mocker.patch(self.handler)
        handler_mock.handle_task(ANY)
        self.mocker.call(handle_task)
        self.mocker.count(3)
        self.mocker.replay()

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

    def test_handle_tasks_hooks_errback(self):
        queue_name = PackageTaskHandler.queue_name

        self.store.add_task(queue_name, 0)

        class MyException(Exception):
            pass

        def handle_task(task):
            result = Deferred()
            result.errback(MyException())
            return result

        handler_mock = self.mocker.patch(self.handler)
        handler_mock.handle_task(ANY)
        self.mocker.call(handle_task)
        self.mocker.replay()

        stash = []
        handle_tasks_result = self.handler.handle_tasks()
        handle_tasks_result.addErrback(stash.append)

        self.assertEqual(len(stash), 1)
        self.assertEqual(stash[0].type, MyException)

    def test_default_handle_task(self):
        result = self.handler.handle_task(None)
        self.assertTrue(isinstance(result, Deferred))
        self.assertTrue(result.called)

    def _mock_run_task_handler(self):
        """
        Mock the different parts of run_task_handler(), to ensure it
        does what it's supposed to do, without actually creating files
        and starting processes.
        """
        # This is a slightly lengthy one, so bear with me.

        # Prepare the mock objects.
        lock_path_mock = self.mocker.replace("landscape.lib.lock.lock_path",
                                             passthrough=False)
        init_logging_mock = self.mocker.replace("landscape.deployment"
                                                ".init_logging",
                                                passthrough=False)
        reactor_mock = self.mocker.patch(TwistedReactor)
        connector_mock = self.mocker.patch(RemoteBrokerConnector)
        HandlerMock = self.mocker.proxy(PackageTaskHandler)

        # The goal of this method is to perform a sequence of tasks
        # where the ordering is important.
        self.mocker.order()

        # First, we must acquire a lock as the same task handler should
        # never have two instances running in parallel.  The 'default'
        # below comes from the queue_name attribute.
        lock_path_mock(os.path.join(self.data_path, "package", "default.lock"))

        # Once locking is done, it's safe to start logging without
        # corrupting the file.  We don't want any output unless it's
        # breaking badly, so the quiet option should be set.
        init_logging_mock(ISTYPE(PackageTaskHandlerConfiguration),
                          "package-task-handler")

        # We also expect the umask to be set appropriately before running the
        # commands
        umask = self.mocker.replace("os.umask")
        umask(022)

        handler_args = []
        HandlerMock(ANY, ANY, ANY, ANY)
        self.mocker.passthrough()  # Let the real constructor run for testing.
        self.mocker.call(lambda *args: handler_args.extend(args))

        call_when_running = []
        reactor_mock.call_when_running(ANY)
        self.mocker.call(lambda f: call_when_running.append(f))
        reactor_mock.run()
        self.mocker.call(lambda: call_when_running[0]())
        connector_mock.disconnect()
        reactor_mock.call_later(0, reactor.stop)

        # Okay, the whole playground is set.
        self.mocker.replay()

        return HandlerMock, handler_args

    def test_run_task_handler(self):
        """
        The L{run_task_handler} function creates and runs the given task
        handler with the proper arguments.
        """
        HandlerMock, handler_args = self._mock_run_task_handler()

        def assert_task_handler(ignored):

            store, facade, broker, config = handler_args

            try:
                # Verify the arguments passed to the reporter constructor.
                self.assertEqual(type(store), PackageStore)
                self.assertEqual(type(facade), AptFacade)
                self.assertEqual(type(broker), LazyRemoteBroker)
                self.assertEqual(type(config),
                                 PackageTaskHandlerConfiguration)

                # Let's see if the store path is where it should be.
                filename = os.path.join(self.data_path, "package", "database")
                store.add_available([1, 2, 3])
                other_store = PackageStore(filename)
                self.assertEqual(other_store.get_available(), [1, 2, 3])

                # Check the hash=>id database directory as well
                self.assertTrue(os.path.exists(
                    os.path.join(self.data_path, "package", "hash-id")))

            finally:
                # Put reactor back in place before returning.
                self.mocker.reset()

        result = run_task_handler(HandlerMock, ["-c", self.config_filename])
        return result.addCallback(assert_task_handler)

    def test_run_task_handler_when_already_locked(self):

        lock_path(os.path.join(self.data_path, "package", "default.lock"))

        try:
            run_task_handler(PackageTaskHandler, ["-c", self.config_filename])
        except SystemExit, e:
            self.assertIn("default is already running", str(e))
        else:
            self.fail("SystemExit not raised")

    def test_run_task_handler_when_already_locked_and_quiet_option(self):
        lock_path(os.path.join(self.data_path, "package", "default.lock"))

        try:
            run_task_handler(PackageTaskHandler,
                             ["-c", self.config_filename, "--quiet"])
        except SystemExit, e:
            self.assertEqual(str(e), "")
        else:
            self.fail("SystemExit not raised")

    def test_errors_in_tasks_are_printed_and_exit_program(self):
        # Ignore a bunch of crap that we don't care about
        reactor_mock = self.mocker.patch(TwistedReactor)
        init_logging_mock = self.mocker.replace("landscape.deployment"
                                                ".init_logging",
                                                passthrough=False)
        init_logging_mock(ARGS)
        reactor_mock.run()

        class MyException(Exception):
            pass

        self.log_helper.ignore_errors(MyException)

        # Simulate a task handler which errors out.
        handler_factory_mock = self.mocker.proxy(PackageTaskHandler)
        handler_mock = handler_factory_mock(ARGS)
        self.expect(handler_mock.run()).result(fail(MyException("Hey error")))

        reactor_mock.call_later(0, reactor.stop)

        self.mocker.replay()

        # Ok now for some real stuff

        def assert_log(ignored):
            self.assertIn("MyException", self.logfile.getvalue())

        result = run_task_handler(handler_factory_mock,
                                  ["-c", self.config_filename])
        return result.addCallback(assert_log)


class LazyRemoteBrokerTest(LandscapeTest):

    helpers = [BrokerServiceHelper]

    def test_wb_is_lazy(self):
        """
        The L{LazyRemoteBroker} class doesn't initialize the actual remote
        broker until one of its attributes gets actually accessed.
        """
        reactor = TwistedReactor()
        connector = RemoteBrokerConnector(reactor, self.broker_service.config)
        self.broker = LazyRemoteBroker(connector)
        self.assertIs(self.broker._remote, None)

        def close_connection(result):
            self.assertTrue(result)
            connector.disconnect()

        result = self.broker.ping()
        return result.addCallback(close_connection)
