import os
import sys
import shutil

from cStringIO import StringIO

from twisted.internet import reactor
from twisted.internet.defer import Deferred, fail

from landscape.lib.lock import lock_path

from landscape.deployment import Configuration
from landscape.broker.remote import RemoteBroker

from landscape.package.taskhandler import PackageTaskHandler, run_task_handler
from landscape.package.facade import SmartFacade
from landscape.package.store import PackageStore
from landscape.package.tests.helpers import SmartFacadeHelper

from landscape.tests.helpers import (
    LandscapeIsolatedTest, LandscapeTest, RemoteBrokerHelper)
from landscape.tests.mocker import ANY, ARGS, MATCH


def ISTYPE(match_type):
    return MATCH(lambda arg: type(arg) is match_type)


class PackageTaskHandlerTest(LandscapeIsolatedTest):

    helpers = [SmartFacadeHelper, RemoteBrokerHelper]

    def setUp(self):
        super(PackageTaskHandlerTest, self).setUp()

        self.config = Configuration()
        self.config.data_path = self.makeDir()
        self.store = PackageStore(self.makeFile())

        self.handler = PackageTaskHandler(self.store, self.facade, self.remote, self.config)

    def test_ensure_channels_reloaded(self):
        self.assertEquals(len(self.facade.get_packages()), 0)
        self.handler.ensure_channels_reloaded()
        self.assertEquals(len(self.facade.get_packages()), 3)

        # Calling it once more won't reload channels again.
        self.facade.get_packages_by_name("name1")[0].installed = True
        self.handler.ensure_channels_reloaded()
        self.assertTrue(self.facade.get_packages_by_name("name1")[0].installed)

    def test_use_hash_id_db(self):

        hash_id_db_directory = os.path.join(self.config.data_path,
                                           "package/hash-id")
        os.makedirs(hash_id_db_directory)
        hash_id_db_filename = os.path.join(hash_id_db_directory,
                                          "fake-uuid_hardy_i386")
        PackageStore(hash_id_db_filename).set_hash_ids({"hash": 123})
        codename_mock = self.mocker.replace("landscape.package."
                                            "taskhandler.get_host_codename")
        codename_mock()
        self.mocker.call(lambda: "hardy")

        arch_mock = self.mocker.replace("landscape.package."
                                        "taskhandler.get_host_arch")
        arch_mock()
        self.mocker.call(lambda: "i386")

        deferred = Deferred()
        remote_mock = self.mocker.patch(RemoteBroker)
        remote_mock.get_server_uuid()
        self.mocker.result(deferred)

        self.mocker.replay()

        self.handler.use_hash_id_db()

        deferred.callback("fake-uuid")

        self.assertEquals(self.store.get_hash_id("hash"), 123)

    def test_run(self):
        handler_mock = self.mocker.patch(self.handler)
        handler_mock.handle_tasks()
        self.mocker.result("WAYO!")

        self.mocker.replay()

        self.assertEquals(self.handler.run(), "WAYO!")

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

        self.assertEquals(stash, [])

        results[1].callback(None)
        self.assertEquals(stash, [])
        self.assertEquals(self.store.get_next_task(queue_name).data, 0)

        results[0].callback(None)
        self.assertEquals(stash, [0, 1])
        self.assertFalse(handle_tasks_result.called)
        self.assertEquals(self.store.get_next_task(queue_name).data, 2)

        results[2].callback(None)
        self.assertEquals(stash, [0, 1, 2])
        self.assertTrue(handle_tasks_result.called)
        self.assertEquals(self.store.get_next_task(queue_name), None)

        handle_tasks_result = self.handler.handle_tasks()
        self.assertTrue(handle_tasks_result.called)

    def test_handle_tasks_hooks_errback(self):
        queue_name = PackageTaskHandler.queue_name

        self.store.add_task(queue_name, 0)

        class MyException(Exception): pass

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

        self.assertEquals(len(stash), 1)
        self.assertEquals(stash[0].type, MyException)

    def test_default_handle_task(self):
        result = self.handler.handle_task(None)
        self.assertTrue(isinstance(result, Deferred))
        self.assertTrue(result.called)

    def test_run_task_handler(self):

        # This is a slightly lengthy one, so bear with me.

        data_path = self.makeDir()

        # Prepare the mock objects.
        lock_path_mock = self.mocker.replace("landscape.lib.lock.lock_path",
                                             passthrough=False)
        install_mock = self.mocker.replace("twisted.internet."
                                           "glib2reactor.install")
        reactor_mock = self.mocker.replace("twisted.internet.reactor",
                                           passthrough=False)
        init_logging_mock = self.mocker.replace("landscape.deployment"
                                                ".init_logging",
                                                passthrough=False)
        HandlerMock = self.mocker.proxy(PackageTaskHandler)

        # The goal of this method is to perform a sequence of tasks
        # where the ordering is important.
        self.mocker.order()

        # As the very first thing, install the twisted glib2 reactor
        # so that we can use DBUS safely.
        install_mock()

        # Then, we must acquire a lock as the same task handler should
        # never have two instances running in parallel.  The 'default'
        # below comes from the queue_name attribute.
        lock_path_mock(os.path.join(data_path, "package/default.lock"))

        # Once locking is done, it's safe to start logging without
        # corrupting the file.  We don't want any output unless it's
        # breaking badly, so the quiet option should be set.
        init_logging_mock(ISTYPE(Configuration), "package-default")

        # Then, it must create an instance of the TaskHandler subclass
        # passed in as a parameter.  We'll keep track of the arguments
        # given and verify them later.
        handler_args = []
        handler_mock = HandlerMock(ANY, ANY, ANY, ANY)
        self.mocker.passthrough() # Let the real constructor run for testing.
        self.mocker.call(lambda *args: handler_args.extend(args))

        # Finally, the task handler must be run, and will return a deferred.
        # We'll return a real deferred so that we can call it back and test
        # whatever was hooked in as well.
        deferred = Deferred()
        handler_mock.run()
        self.mocker.result(deferred)

        # With all of that done, the Twisted reactor must be run, so that
        # deferred tasks are correctly performed.
        reactor_mock.run()

        self.mocker.unorder()

        # The following tasks are hooked in as callbacks of our deferred.
        # We must use callLater() so that stop() won't happen before run().
        reactor_mock.callLater(0, "STOP METHOD")
        reactor_mock.stop
        self.mocker.result("STOP METHOD")

        # We also expect the umask to be set appropriately before running the
        # commands
        umask = self.mocker.replace("os.umask")
        umask(022)

        # Okay, the whole playground is set.
        self.mocker.replay()

        try:
            # DO IT!
            result = run_task_handler(HandlerMock,
                                      ["--data-path", data_path,
                                       "--bus", "session"])

            # reactor.stop() wasn't run yet, so it must fail right now.
            self.assertRaises(AssertionError, self.mocker.verify)

            # DO THE REST OF IT! :-)
            result.callback(None)

            # Are we there yet!?
            self.mocker.verify()
        finally:
            # Put reactor back in place before returning.
            self.mocker.reset()

        store, facade, broker, config = handler_args

        # Verify if the arguments to the reporter constructor were correct.
        self.assertEquals(type(store), PackageStore)
        self.assertEquals(type(facade), SmartFacade)
        self.assertEquals(type(broker), RemoteBroker)
        self.assertEquals(type(config), Configuration)

        # Let's see if the store path is where it should be.
        filename = os.path.join(data_path, "package/database")
        store.add_available([1, 2, 3])
        other_store = PackageStore(filename)
        self.assertEquals(other_store.get_available(), [1, 2, 3])

    def test_run_task_handler_when_already_locked(self):
        data_path = self.makeDir()

        install_mock = self.mocker.replace("twisted.internet."
                                           "glib2reactor.install")
        install_mock()

        self.mocker.replay()

        os.mkdir(os.path.join(data_path, "package"))
        lock_path(os.path.join(data_path, "package/default.lock"))

        try:
            run_task_handler(PackageTaskHandler, ["--data-path", data_path])
        except SystemExit, e:
            self.assertIn("default is already running", str(e))
        else:
            self.fail("SystemExit not raised")

    def test_run_task_handler_when_already_locked_and_quiet_option(self):
        data_path = self.makeDir()

        install_mock = self.mocker.replace("twisted.internet."
                                           "glib2reactor.install")
        install_mock()

        self.mocker.replay()

        os.mkdir(os.path.join(data_path, "package"))
        lock_path(os.path.join(data_path, "package/default.lock"))

        try:
            run_task_handler(PackageTaskHandler,
                             ["--data-path", data_path, "--quiet"])
        except SystemExit, e:
            self.assertEquals(str(e), "")
        else:
            self.fail("SystemExit not raised")

    def test_errors_in_tasks_are_printed_and_exit_program(self):
        # Ignore a bunch of crap that we don't care about
        install_mock = self.mocker.replace("twisted.internet."
                                           "glib2reactor.install")
        install_mock()
        reactor_mock = self.mocker.proxy(reactor)
        init_logging_mock = self.mocker.replace("landscape.deployment"
                                                ".init_logging",
                                                passthrough=False)
        init_logging_mock(ARGS)
        reactor_mock.run()

        # Get a deferred which will fire when the reactor is stopped, so the
        # test runs until the reactor is stopped.
        done = Deferred()
        self.expect(reactor_mock.stop()).call(lambda: done.callback(None))

        class MyException(Exception): pass

        self.log_helper.ignore_errors(MyException)

        # Simulate a task handler which errors out.
        handler_factory_mock = self.mocker.proxy(PackageTaskHandler)
        handler_mock = handler_factory_mock(ARGS)
        self.expect(handler_mock.run()).result(fail(MyException("Hey error")))

        self.mocker.replay()

        # Ok now for some real stuff

        result = run_task_handler(handler_factory_mock,
                                  ["--data-path", self.data_path,
                                   "--bus", "session"],
                                  reactor=reactor_mock)

        def everything_stopped(result):
            self.assertIn("MyException", self.logfile.getvalue())

        return done.addCallback(everything_stopped)
