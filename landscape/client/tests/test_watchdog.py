import stat
import time
import sys
import os
import signal

import mock

from twisted.internet.utils import getProcessOutput
from twisted.internet.defer import Deferred, succeed, fail
from twisted.internet import reactor
from twisted.python.fakepwd import UserDatabase

from landscape.lib.encoding import encode_values
from landscape.lib.fs import read_text_file
from landscape.lib.testing import EnvironSaverHelper
from landscape.client.tests.clock import Clock
from landscape.client.tests.helpers import (
        LandscapeTest, FakeBrokerServiceHelper)
from landscape.client.watchdog import (
    Daemon, WatchDog, WatchDogService, ExecutableNotFoundError,
    WatchDogConfiguration, bootstrap_list,
    MAXIMUM_CONSECUTIVE_RESTARTS, RESTART_BURST_DELAY, run,
    Broker, Monitor, Manager)
from landscape.client.amp import ComponentConnector
from landscape.client.broker.amp import RemoteBrokerConnector
from landscape.client.reactor import LandscapeReactor

import landscape.client.watchdog


class StubDaemon(object):
    program = "program-name"


class WatchDogTest(LandscapeTest):
    """
    Tests for L{landscape.client.watchdog.WatchDog}.
    """

    def setUp(self):
        super(WatchDogTest, self).setUp()
        self.broker_factory_patch = (
                mock.patch("landscape.client.watchdog.Broker"))
        self.broker_factory = self.broker_factory_patch.start()
        self.monitor_factory_patch = (
                mock.patch("landscape.client.watchdog.Monitor"))
        self.monitor_factory = self.monitor_factory_patch.start()
        self.manager_factory_patch = (
                mock.patch("landscape.client.watchdog.Manager"))
        self.manager_factory = self.manager_factory_patch.start()
        self.config = WatchDogConfiguration()
        self.addCleanup(self.cleanup_mocks)

    def cleanup_mocks(self):
        self.broker_factory_patch.stop()
        self.monitor_factory_patch.stop()
        self.manager_factory_patch.stop()

    def setup_daemons_mocks(self):
        self.broker = mock.Mock()
        self.monitor = mock.Mock()
        self.manager = mock.Mock()
        self.broker_factory.return_value = self.broker
        self.monitor_factory.return_value = self.monitor
        self.manager_factory.return_value = self.manager
        self.broker.program = "landscape-broker"
        self.monitor.program = "landscape-monitor"
        self.manager.program = "landscape-manager"

    def assert_daemons_mocks(self):
        self.broker_factory.assert_called_with(
            mock.ANY, verbose=False, config=None)
        self.monitor_factory.assert_called_with(
            mock.ANY, verbose=False, config=None)
        self.manager_factory.assert_called_with(
            mock.ANY, verbose=False, config=None)

    def setup_request_exit(self):
        self.broker.request_exit.return_value = succeed(True)
        self.broker.wait_or_die.return_value = succeed(None)
        self.monitor.wait_or_die.return_value = succeed(None)
        self.manager.wait_or_die.return_value = succeed(None)

    def assert_request_exit(self):
        self.broker.prepare_for_shutdown.assert_called_with()
        self.broker.request_exit.assert_called_with()
        self.broker.wait_or_die.assert_called_with()
        self.monitor.prepare_for_shutdown.assert_called_with()
        self.monitor.wait_or_die.assert_called_with()
        self.manager.prepare_for_shutdown.assert_called_with()
        self.manager.wait_or_die.assert_called_with()

    def test_daemon_construction(self):
        """The WatchDog sets up some daemons when constructed."""
        self.setup_daemons_mocks()
        WatchDog(config=self.config)
        self.assert_daemons_mocks()

    def test_limited_daemon_construction(self):
        self.setup_daemons_mocks()
        WatchDog(
            enabled_daemons=[self.broker_factory, self.monitor_factory],
            config=self.config)

        self.broker_factory.assert_called_with(
            mock.ANY, verbose=False, config=None)
        self.monitor_factory.assert_called_with(
            mock.ANY, verbose=False, config=None)
        self.manager_factory.assert_not_called()

    def test_check_running_one(self):
        self.setup_daemons_mocks()
        self.broker.is_running.return_value = succeed(True)
        self.monitor.is_running.return_value = succeed(False)
        self.manager.is_running.return_value = succeed(False)
        result = WatchDog(config=self.config).check_running()

        def got_result(r):
            self.assertEqual([daemon.program for daemon in r],
                             ["landscape-broker"])
            self.assert_daemons_mocks()
            self.broker.is_running.assert_called_with()
            self.monitor.is_running.assert_called_with()
            self.manager.is_running.assert_called_with()

        return result.addCallback(got_result)

    def test_check_running_many(self):
        self.setup_daemons_mocks()
        self.broker.is_running.return_value = succeed(True)
        self.monitor.is_running.return_value = succeed(True)
        self.manager.is_running.return_value = succeed(True)
        result = WatchDog(config=self.config).check_running()

        def got_result(r):
            self.assertEqual([daemon.program for daemon in r],
                             ["landscape-broker", "landscape-monitor",
                              "landscape-manager"])
            self.assert_daemons_mocks()

        return result.addCallback(got_result)

    def test_check_running_limited_daemons(self):
        """
        When the user has explicitly asked not to run some daemons, those
        daemons which are not being run should not checked.
        """
        self.setup_daemons_mocks()
        self.broker.is_running.return_value = succeed(True)
        result = WatchDog(enabled_daemons=[self.broker_factory],
                          config=self.config).check_running()

        def got_result(r):
            self.assertEqual(len(r), 1)
            self.assertEqual(r[0].program, "landscape-broker")

        return result.addCallback(got_result)

    def test_start_and_stop_daemons(self):
        """The WatchDog will start all daemons, starting with the broker."""
        self.setup_daemons_mocks()

        self.broker.start()
        self.monitor.start()
        self.manager.start()

        self.setup_request_exit()

        clock = Clock()
        dog = WatchDog(clock, config=self.config)
        dog.start()
        clock.advance(0)
        result = dog.request_exit()
        result.addCallback(lambda _: self.assert_request_exit())
        return result

    def test_start_limited_daemons(self):
        """
        start only starts the daemons which are actually enabled.
        """
        self.setup_daemons_mocks()

        clock = Clock()
        dog = WatchDog(
            clock, enabled_daemons=[self.broker_factory], config=self.config)
        dog.start()

        self.broker.start.assert_called_once_with()
        self.monitor.start.assert_not_called()
        self.manager.start.assert_not_called()

    def test_request_exit(self):
        """request_exit() asks the broker to exit.

        The broker itself is responsible for notifying other plugins to exit.

        When the deferred returned from request_exit fires, the process should
        definitely be gone.
        """
        self.setup_daemons_mocks()
        self.setup_request_exit()
        result = WatchDog(config=self.config).request_exit()
        result.addCallback(lambda _: self.assert_request_exit())
        return result

    def test_ping_reply_after_request_exit_should_not_restart_processes(self):
        """
        When request_exit occurs between a ping request and response, a failing
        ping response should not cause the process to be restarted.
        """
        self.setup_daemons_mocks()

        self.broker.start()
        self.monitor.start()
        self.manager.start()

        monitor_ping_result = Deferred()

        self.broker.is_running.return_value = succeed(True)
        self.monitor.is_running.return_value = monitor_ping_result
        self.manager.is_running.return_value = succeed(True)

        self.setup_request_exit()

        clock = Clock()

        dog = WatchDog(clock, config=self.config)
        dog.start()
        clock.advance(0)
        clock.advance(5)
        result = dog.request_exit()
        monitor_ping_result.callback(False)

        def check(_):
            # The monitor should never be explicitly stopped / restarted.
            self.monitor.stop.assert_not_called()
            # Start *is* called
            self.monitor.start.call_count = 2
            self.assert_request_exit()

        return result.addCallback(check)

    def test_wb_log_notification(self):
        """
        SIGUSR1 should cause logs to be reopened.
        """
        mock_reactor = mock.Mock()
        watchdog = WatchDog(reactor=mock_reactor, config=self.config)
        os.kill(os.getpid(), signal.SIGUSR1)

        mock_reactor.callFromThread.assert_called_once_with(
            watchdog._notify_rotate_logs)


START = "start"
STOP = "stop"


class BoringDaemon(object):

    def __init__(self, program):
        self.program = program
        self.boots = []

    def start(self):
        self.boots.append(START)

    def stop(self):
        self.boots.append(STOP)
        return succeed(None)

    def is_running(self):
        return succeed(True)

    def request_exit(self):
        return succeed(True)

    def wait(self):
        return succeed(None)

    def wait_or_die(self):
        return self.wait()

    def prepare_for_shutdown(self):
        pass


class AsynchronousPingDaemon(BoringDaemon):
    pings = 0
    deferred = None

    def is_running(self):
        self.pings += 1
        if self.deferred is not None:
            raise AssertionError(
                "is_running called while it's already running!")
        self.deferred = Deferred()
        return self.deferred

    def fire_running(self, value):
        self.deferred.callback(value)
        self.deferred = None


class NonMockerWatchDogTests(LandscapeTest):

    def test_ping_is_not_rescheduled_until_pings_complete(self):
        clock = Clock()
        dog = WatchDog(clock,
                       broker=AsynchronousPingDaemon("test-broker"),
                       monitor=AsynchronousPingDaemon("test-monitor"),
                       manager=AsynchronousPingDaemon("test-manager"))

        dog.start_monitoring()

        clock.advance(5)
        for daemon in dog.daemons:
            self.assertEqual(daemon.pings, 1)
        clock.advance(5)
        for daemon in dog.daemons:
            self.assertEqual(daemon.pings, 1)
            daemon.fire_running(True)
        clock.advance(5)
        for daemon in dog.daemons:
            self.assertEqual(daemon.pings, 2)

    def test_check_daemons(self):
        """
        The daemons are checked to be running every so often. When N=5 of these
        checks fail, the daemon will be restarted.
        """
        clock = Clock()
        dog = WatchDog(clock,
                       broker=AsynchronousPingDaemon("test-broker"),
                       monitor=AsynchronousPingDaemon("test-monitor"),
                       manager=AsynchronousPingDaemon("test-manager"))
        dog.start_monitoring()

        for i in range(4):
            clock.advance(5)
            dog.broker.fire_running(False)
            dog.monitor.fire_running(True)
            dog.manager.fire_running(True)
            self.assertEqual(dog.broker.boots, [])

        clock.advance(5)
        dog.broker.fire_running(False)
        dog.monitor.fire_running(True)
        dog.manager.fire_running(True)
        self.assertEqual(dog.broker.boots, [STOP, START])

    def test_counted_ping_failures_reset_on_success(self):
        """
        When a failing ping is followed by a successful ping, it will then
        require 5 more ping failures to restart the daemon.
        """
        clock = Clock()
        dog = WatchDog(clock,
                       broker=AsynchronousPingDaemon("test-broker"),
                       monitor=AsynchronousPingDaemon("test-monitor"),
                       manager=AsynchronousPingDaemon("test-manager"))
        dog.start_monitoring()

        clock.advance(5)
        dog.broker.fire_running(False)
        dog.monitor.fire_running(True)
        dog.manager.fire_running(True)

        clock.advance(5)
        dog.broker.fire_running(True)
        dog.monitor.fire_running(True)
        dog.manager.fire_running(True)

        for i in range(4):
            clock.advance(5)
            dog.broker.fire_running(False)
            dog.monitor.fire_running(True)
            dog.manager.fire_running(True)
            self.assertEqual(dog.broker.boots, [])

        clock.advance(5)
        dog.broker.fire_running(False)
        dog.monitor.fire_running(True)
        dog.manager.fire_running(True)
        self.assertEqual(dog.broker.boots, [STOP, START])

    def test_exiting_during_outstanding_ping_works(self):
        """
        This is a regression test. Some code called .cancel() on a timed call
        without checking if it was active first. Asynchronous is_running will
        cause the scheduled call to exist but already fired.
        """
        clock = Clock()
        dog = WatchDog(clock,
                       broker=BoringDaemon("test-broker"),
                       monitor=BoringDaemon("test-monitor"),
                       manager=AsynchronousPingDaemon("test-manager"))
        dog.start_monitoring()
        clock.advance(5)
        return dog.request_exit()

    def test_wait_for_stop_before_start(self):
        """
        When a daemon times out and the watchdog attempts to kill it, it should
        not be restarted until the process has fully died.
        """
        clock = Clock()
        dog = WatchDog(clock,
                       broker=AsynchronousPingDaemon("test-broker"),
                       monitor=BoringDaemon("test-monitor"),
                       manager=BoringDaemon("test-manager"))
        stop_result = Deferred()
        dog.broker.stop = lambda: stop_result
        dog.start_monitoring()

        for i in range(5):
            clock.advance(5)
            dog.broker.fire_running(False)

        self.assertEqual(dog.broker.boots, [])
        stop_result.callback(None)
        self.assertEqual(dog.broker.boots, ["start"])

    def test_wait_for_stop_before_ping(self):
        """
        When a daemon times out and the watchdog restarts it, it should not be
        pinged until after the restart completes.
        """
        clock = Clock()
        dog = WatchDog(clock,
                       broker=AsynchronousPingDaemon("test-broker"),
                       monitor=BoringDaemon("test-monitor"),
                       manager=BoringDaemon("test-manager"))
        stop_result = Deferred()
        dog.broker.stop = lambda: stop_result
        dog.start_monitoring()

        for i in range(5):
            clock.advance(5)
            dog.broker.fire_running(False)

        self.assertEqual(dog.broker.boots, [])
        self.assertEqual(dog.broker.pings, 5)
        clock.advance(5)  # wait some more to see if a ping happens
        self.assertEqual(dog.broker.pings, 5)
        stop_result.callback(None)
        self.assertEqual(dog.broker.boots, ["start"])
        clock.advance(5)
        self.assertEqual(dog.broker.pings, 6)

    def test_ping_failure_counter_reset_after_restart(self):
        """
        When a daemon stops responding and gets restarted after 5 failed pings,
        it will wait for another 5 failed pings before it will be restarted
        again.
        """
        clock = Clock()
        dog = WatchDog(clock,
                       broker=AsynchronousPingDaemon("test-broker"),
                       monitor=BoringDaemon("test-monitor"),
                       manager=BoringDaemon("test-manager"))
        dog.start_monitoring()

        for i in range(5):
            clock.advance(5)
            dog.broker.fire_running(False)

        self.assertEqual(dog.broker.boots, ["stop", "start"])
        for i in range(4):
            clock.advance(5)
            dog.broker.fire_running(False)
            self.assertEqual(dog.broker.boots, ["stop", "start"])
        clock.advance(5)
        dog.broker.fire_running(False)
        self.assertEqual(dog.broker.boots, ["stop", "start", "stop", "start"])

    def test_die_when_broker_unavailable(self):
        """
        If the broker is not running, the client should still be able to shut
        down.
        """
        self.log_helper.ignore_errors(
            "Couldn't request that broker gracefully shut down; "
            "killing forcefully.")
        clock = Clock()
        dog = WatchDog(clock,
                       broker=BoringDaemon("test-broker"),
                       monitor=BoringDaemon("test-monitor"),
                       manager=BoringDaemon("test-manager"))

        # request_exit returns False when there's no broker, as tested by
        # DaemonTest.test_request_exit_without_broker
        dog.broker.request_exit = lambda: succeed(False)
        # The manager's wait method never fires its deferred because nothing
        # told it to die because the broker is dead!

        manager_result = Deferred()
        dog.manager.wait = lambda: manager_result

        def stop():
            manager_result.callback(True)
            return succeed(True)
        dog.manager.stop = stop

        result = dog.request_exit()
        return result


class StubBroker(object):

    name = "broker"


class RemoteStubBrokerConnector(ComponentConnector):

    component = StubBroker


class DaemonTestBase(LandscapeTest):

    connector_factory = RemoteStubBrokerConnector

    EXEC_NAME = "landscape-broker"

    def setUp(self):
        super(DaemonTestBase, self).setUp()

        if hasattr(self, "broker_service"):
            # DaemonBrokerTest
            self.broker_service.startService()
            self.config = self.broker_service.config
        else:
            # DaemonTest
            self.config = WatchDogConfiguration()
            self.config.data_path = self.makeDir()
            self.makeDir(path=self.config.sockets_path)

        self.connector = self.connector_factory(LandscapeReactor(),
                                                self.config)
        self.daemon = self.get_daemon()

    def tearDown(self):
        if hasattr(self, "broker_service"):
            # DaemonBrokerTest
            self.broker_service.stopService()
        super(DaemonTestBase, self).tearDown()

    def get_daemon(self, **kwargs):
        if 'username' in kwargs:
            class MyDaemon(Daemon):
                username = kwargs.pop('username')
        else:
            MyDaemon = Daemon
        daemon = MyDaemon(self.connector, **kwargs)
        daemon.program = self.EXEC_NAME
        daemon.factor = 0.01
        return daemon


class FileChangeWaiter(object):

    def __init__(self, filename):
        os.utime(filename, (0, 0))
        self._mtime = os.path.getmtime(filename)
        self._filename = filename

    def wait(self, timeout=60):
        if timeout:
            end = time.time() + timeout
        while self._mtime == os.path.getmtime(self._filename):
            time.sleep(0.1)
            if timeout and time.time() > end:
                raise RuntimeError(
                    "timed out after {} seconds".format(timeout))


class DaemonTest(DaemonTestBase):

    def _write_script(self, content):
        filename = self.write_script(self.config, self.EXEC_NAME, content)
        self.daemon.BIN_DIR = self.config.bindir
        return filename

    def test_find_executable_works(self):
        expected = self._write_script("I'm the broker.")
        command = self.daemon.find_executable()

        self.assertEqual(expected, command)

    def test_find_executable_cant_find_file(self):
        self.daemon.BIN_DIR = "/fake/bin"

        with self.assertRaises(ExecutableNotFoundError):
            self.daemon.find_executable()

    def test_start_process(self):
        output_filename = self.makeFile("NOT RUN")
        self._write_script(
            '#!/bin/sh\necho "RUN $@" > %s' % output_filename)

        waiter = FileChangeWaiter(output_filename)

        self.daemon.start()

        waiter.wait()

        self.assertEqual(open(output_filename).read(),
                         "RUN --ignore-sigint --quiet\n")

        return self.daemon.stop()

    def test_start_process_with_verbose(self):
        output_filename = self.makeFile("NOT RUN")
        self._write_script(
            '#!/bin/sh\necho "RUN $@" > %s' % output_filename)

        waiter = FileChangeWaiter(output_filename)

        daemon = self.get_daemon(verbose=True)
        daemon.BIN_DIR = self.config.bindir
        daemon.start()

        waiter.wait(timeout=10)

        self.assertEqual(open(output_filename).read(),
                         "RUN --ignore-sigint\n")

        return daemon.stop()

    def test_kill_process_with_sigterm(self):
        """The stop() method sends SIGTERM to the subprocess."""
        output_filename = self.makeFile("NOT RUN")
        self._write_script(
            ("#!%s\n"
             "import time\n"
             "file = open(%r, 'w')\n"
             "file.write('RUN')\n"
             "file.close()\n"
             "time.sleep(1000)\n"
             ) % (sys.executable, output_filename))

        waiter = FileChangeWaiter(output_filename)
        self.daemon.start()
        waiter.wait()
        self.assertEqual(open(output_filename).read(), "RUN")
        return self.daemon.stop()

    def test_kill_process_with_sigkill(self):
        """
        Verify that killing process really works, even if something is
        holding the process badly.  In these cases, a SIGKILL is performed
        some time after the SIGTERM was issued and didn't work.
        """
        output_filename = self.makeFile("NOT RUN")
        self._write_script(
            ("#!%s\n"
             "import signal, os\n"
             "signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
             "file = open(%r, 'w')\n"
             "file.write('RUN')\n"
             "file.close()\n"
             "os.kill(os.getpid(), signal.SIGSTOP)\n"
             ) % (sys.executable, output_filename))

        self.addCleanup(setattr, landscape.client.watchdog, "SIGKILL_DELAY",
                        landscape.client.watchdog.SIGKILL_DELAY)
        landscape.client.watchdog.SIGKILL_DELAY = 1

        waiter = FileChangeWaiter(output_filename)
        self.daemon.start()
        waiter.wait()
        self.assertEqual(open(output_filename).read(), "RUN")
        return self.daemon.stop()

    def test_wait_for_process(self):
        """
        The C{wait} method returns a Deferred that fires when the process has
        died.
        """
        output_filename = self.makeFile("NOT RUN")
        self._write_script(
            '#!/bin/sh\necho "RUN" > %s' % output_filename)

        self.daemon.start()

        def got_result(result):
            self.assertEqual(open(output_filename).read(), "RUN\n")
        return self.daemon.wait().addCallback(got_result)

    def test_wait_or_die_dies_happily(self):
        """
        The C{wait_or_die} method will wait for the process to die for a
        certain amount of time, just like C{wait}.
        """
        output_filename = self.makeFile("NOT RUN")
        self._write_script(
            '#!/bin/sh\necho "RUN" > %s' % output_filename)

        self.daemon.start()

        def got_result(result):
            self.assertEqual(open(output_filename).read(), "RUN\n")
        return self.daemon.wait_or_die().addCallback(got_result)

    def test_wait_or_die_terminates(self):
        """wait_or_die eventually terminates the process."""
        output_filename = self.makeFile("NOT RUN")
        self._write_script(
            """\
#!%(exe)s
import time
import signal
file = open(%(out)r, 'w')
file.write('unsignalled')
file.close()
def term(frame, sig):
    file = open(%(out)r, 'w')
    file.write('TERMINATED')
    file.close()
signal.signal(signal.SIGTERM, term)
time.sleep(999)
        """ % {"exe": sys.executable, "out": output_filename})

        self.addCleanup(setattr,
                        landscape.client.watchdog, "GRACEFUL_WAIT_PERIOD",
                        landscape.client.watchdog.GRACEFUL_WAIT_PERIOD)
        landscape.client.watchdog.GRACEFUL_WAIT_PERIOD = 0.2
        self.daemon.start()

        def got_result(result):
            self.assertEqual(open(output_filename).read(), "TERMINATED")
        return self.daemon.wait_or_die().addCallback(got_result)

    def test_wait_or_die_kills(self):
        """
        wait_or_die eventually falls back to KILLing a process, after waiting
        and terminating don't work.
        """
        output_filename = self.makeFile("NOT RUN")
        self._write_script(
            ("#!%s\n"
             "import signal, os\n"
             "signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
             "file = open(%r, 'w')\n"
             "file.write('RUN')\n"
             "file.close()\n"
             "os.kill(os.getpid(), signal.SIGSTOP)\n"
             ) % (sys.executable, output_filename))

        self.addCleanup(setattr,
                        landscape.client.watchdog, "SIGKILL_DELAY",
                        landscape.client.watchdog.SIGKILL_DELAY)
        self.addCleanup(setattr,
                        landscape.client.watchdog, "GRACEFUL_WAIT_PERIOD",
                        landscape.client.watchdog.GRACEFUL_WAIT_PERIOD)
        landscape.client.watchdog.GRACEFUL_WAIT_PERIOD = 1
        landscape.client.watchdog.SIGKILL_DELAY = 1

        waiter = FileChangeWaiter(output_filename)
        self.daemon.start()
        waiter.wait()
        self.assertEqual(open(output_filename).read(), "RUN")
        return self.daemon.wait_or_die()

    def test_wait_for_unstarted_process(self):
        """
        If a process has never been started, waiting for it is
        immediately successful.
        """
        daemon = self.get_daemon()

        def assert_wait(is_running):
            self.assertFalse(is_running)
            return daemon.wait()

        result = daemon.is_running()
        result.addCallback(assert_wait)
        return result

    def test_wait_or_die_for_unstarted_process(self):
        """
        If a process has never been started, wait_or_die is
        immediately successful.
        """
        daemon = self.get_daemon()
        calls = []
        daemon.wait_or_die().addCallback(calls.append)
        self.assertEqual(calls, [None])

    def test_simulate_broker_not_starting_up(self):
        """
        When a daemon repeatedly dies, the watchdog gives up entirely and shuts
        down.
        """
        stop = []
        stopped = []
        self.log_helper.ignore_errors("Can't keep landscape-broker running. "
                                      "Exiting.")

        output_filename = self.makeFile("NOT RUN")

        self._write_script(
            "#!/bin/sh\necho RUN >> %s" % output_filename)

        def got_result(result):
            self.assertEqual(len(list(open(output_filename))),
                             MAXIMUM_CONSECUTIVE_RESTARTS)

            self.assertTrue("Can't keep landscape-broker running." in
                            self.logfile.getvalue())
            self.assertCountEqual([True], stopped)
            reactor.stop = stop[0]

        result = Deferred()
        result.addCallback(got_result)

        def mock_reactor_stop():
            stop.append(reactor.stop)
            reactor.stop = lambda: stopped.append(True)

        reactor.callLater(0, mock_reactor_stop)
        reactor.callLater(1, result.callback, None)

        daemon = self.get_daemon(reactor=reactor)
        daemon.BIN_DIR = self.config.bindir
        daemon.start()

        return result

    def test_simulate_broker_not_starting_up_with_delay(self):
        """
        The watchdog won't shutdown entirely when a daemon dies repeatedly as
        long as it is not dying too quickly.
        """
        # This test hacks the first time() call to make it return a timestamp
        # that happend a while ago, and so give the impression that some time
        # has passed and it's fine to restart more times again.
        self.log_helper.ignore_errors("Can't keep landscape-broker running. "
                                      "Exiting.")
        stop = []
        stopped = []

        output_filename = self.makeFile("NOT RUN")

        self._write_script(
            "#!/bin/sh\necho RUN >> %s" % output_filename)

        def got_result(result):
            # Pay attention to the +1 bellow. It's the reason for this test.
            self.assertEqual(len(list(open(output_filename))),
                             MAXIMUM_CONSECUTIVE_RESTARTS + 1)

            self.assertTrue("Can't keep landscape-broker running." in
                            self.logfile.getvalue())
            self.assertCountEqual([True], stopped)
            reactor.stop = stop[0]

        result = Deferred()
        result.addCallback(lambda x: self.daemon.stop())
        result.addCallback(got_result)
        original_time = time.time

        # Make the *first* call to time return 0, so that it will try one
        # more time, and exercise the burst protection system.
        def time_sideeffect(before=[]):
            if not before:
                before.append(True)
                return original_time() - RESTART_BURST_DELAY
            return original_time()
        time_patcher = mock.patch.object(
            time, "time", side_effect=time_sideeffect)
        time_patcher.start()
        self.addCleanup(time_patcher.stop)

        # It's important to call start() shortly after the mocking above,
        # as we don't want anyone else getting the fake time.
        daemon = self.get_daemon(reactor=reactor)
        daemon.BIN_DIR = self.config.bindir
        daemon.start()

        def mock_reactor_stop():
            stop.append(reactor.stop)
            reactor.stop = lambda: stopped.append(True)

        reactor.callLater(0, mock_reactor_stop)
        reactor.callLater(1, result.callback, None)

        return result

    def test_is_not_running(self):
        result = self.daemon.is_running()
        result.addCallback(self.assertFalse)
        return result

    @mock.patch("pwd.getpwnam")
    @mock.patch("os.getuid", return_value=0)
    def test_spawn_process_with_uid(self, getuid, getpwnam):
        """
        When the current UID as reported by os.getuid is not the uid of the
        username of the daemon, the watchdog explicitly switches to the uid of
        the username of the daemon. It also specifies the gid as the primary
        group of that user.
        """
        self._write_script("#!/bin/sh")

        class getpwnam_result:
            pw_uid = 123
            pw_gid = 456
            pw_dir = "/var/lib/landscape"

        getpwnam.return_value = getpwnam_result()

        reactor = mock.Mock()

        daemon = self.get_daemon(reactor=reactor)
        daemon.BIN_DIR = self.config.bindir
        daemon.start()

        getuid.assert_called_with()
        getpwnam.assert_called_with("landscape")

        env = os.environ.copy()
        env["HOME"] = "/var/lib/landscape"
        env["USER"] = "landscape"
        env["LOGNAME"] = "landscape"
        # This looks like testing implementation, but we want to assert that
        # the environment variables are encoded before passing to
        # spawnProcess() to cope with unicode in them.
        env = encode_values(env)

        reactor.spawnProcess.assert_called_with(
            mock.ANY, mock.ANY, args=mock.ANY, env=env, uid=123, gid=456)

    @mock.patch("os.getuid", return_value=555)
    def test_spawn_process_without_root(self, mock_getuid):
        """
        If the watchdog is not running as root, no uid or gid switching will
        occur.
        """
        self._write_script("#!/bin/sh")

        reactor = mock.Mock()
        daemon = self.get_daemon(reactor=reactor)
        daemon.BIN_DIR = self.config.bindir
        daemon.start()

        reactor.spawnProcess.assert_called_with(
            mock.ANY, mock.ANY, args=mock.ANY, env=mock.ANY, uid=None,
            gid=None)

    @mock.patch("os.getgid", return_value=0)
    @mock.patch("os.getuid", return_value=0)
    def test_spawn_process_same_uid(self, getuid, getgid):
        """
        If the daemon is specified to run as root, and the watchdog is running
        as root, no uid or gid switching will occur.
        """
        self._write_script("#!/bin/sh")
        reactor = mock.Mock()

        daemon = self.get_daemon(reactor=reactor, username="root")
        daemon.BIN_DIR = self.config.bindir
        daemon.start()

        reactor.spawnProcess.assert_called_with(
            mock.ANY, mock.ANY, args=mock.ANY, env=mock.ANY, uid=None,
            gid=None)

    def test_request_exit(self):
        """The request_exit() method calls exit() on the broker process."""

        output_filename = self.makeFile("NOT CALLED")
        socket_filename = os.path.join(self.config.sockets_path, "broker.sock")
        broker_filename = self.makeFile(STUB_BROKER %
                                        {"executable": sys.executable,
                                         "path": sys.path,
                                         "output_filename": output_filename,
                                         "socket": socket_filename})

        os.chmod(broker_filename, 0o755)
        env = encode_values(os.environ)
        process_result = getProcessOutput(broker_filename, env=env,
                                          errortoo=True)

        # Wait until the process starts up. This can take a few seconds
        # depending on io, so keep trying the call a few times.
        self.daemon.factor = 2.8
        self.daemon.max_retries = 10
        self.daemon.request_exit()

        def got_result(result):
            self.assertEqual(result, b"")
            self.assertEqual(read_text_file(output_filename), "CALLED")

        return process_result.addCallback(got_result)

    def test_request_exit_without_broker(self):
        """
        The request_exit method returns False when the broker can't be
        contacted.
        """
        result = self.daemon.request_exit()
        return self.assertSuccess(result, False)


class DaemonBrokerTest(DaemonTestBase):

    helpers = [FakeBrokerServiceHelper]

    @property
    def connector_factory(self):
        return RemoteBrokerConnector

    def test_is_running(self):
        self.daemon._connector._reactor = self.broker_service.reactor
        result = self.daemon.is_running()
        result.addCallback(self.assertTrue)
        return result


class WatchDogOptionsTest(LandscapeTest):

    def setUp(self):
        super(WatchDogOptionsTest, self).setUp()
        self.config = WatchDogConfiguration()
        self.config.default_config_filenames = []

    def test_daemon(self):
        self.config.load(["--daemon"])
        self.assertTrue(self.config.daemon)

    def test_daemon_default(self):
        self.config.load([])
        self.assertFalse(self.config.daemon)

    def test_pid_file(self):
        self.config.load(["--pid-file", "wubble.txt"])
        self.assertEqual(self.config.pid_file, "wubble.txt")

    def test_pid_file_default(self):
        self.config.load([])
        self.assertEqual(self.config.pid_file, None)

    def test_monitor_only(self):
        self.config.load(["--monitor-only"])
        self.assertEqual(self.config.get_enabled_daemons(),
                         [Broker, Monitor])

    def test_default_daemons(self):
        self.config.load([])
        self.assertEqual(self.config.get_enabled_daemons(),
                         [Broker, Monitor, Manager])


class WatchDogServiceTest(LandscapeTest):

    def setUp(self):
        super(WatchDogServiceTest, self).setUp()
        self.configuration = WatchDogConfiguration()
        self.data_path = self.makeDir()
        self.log_dir = self.makeDir()
        self.config_filename = self.makeFile("[client]\n")
        self.configuration.load(["--config", self.config_filename,
                                 "--data-path", self.data_path,
                                 "--log-dir", self.log_dir])

    @mock.patch("landscape.client.watchdog.daemonize")
    @mock.patch("landscape.client.watchdog.WatchDog")
    def test_daemonize(self, mock_watchdog, mock_daemonize):
        mock_watchdog().check_running.return_value = succeed([])
        self.configuration.daemon = True

        service = WatchDogService(self.configuration)
        service.startService()
        mock_watchdog().check_running.assert_called_once_with()
        mock_watchdog().start.assert_called_once_with()
        mock_daemonize.assert_called_once_with()

    @mock.patch("landscape.client.watchdog.daemonize")
    @mock.patch("landscape.client.watchdog.WatchDog")
    def test_pid_file(self, mock_watchdog, mock_daemonize):
        mock_watchdog().check_running.return_value = succeed([])
        pid_file = self.makeFile()

        self.configuration.daemon = True
        self.configuration.pid_file = pid_file

        service = WatchDogService(self.configuration)
        service.startService()
        self.assertEqual(int(open(pid_file, "r").read()), os.getpid())
        mock_watchdog().check_running.assert_called_once_with()
        mock_watchdog().start.assert_called_once_with()
        mock_daemonize.assert_called_once_with()

    @mock.patch("landscape.client.watchdog.reactor")
    @mock.patch("landscape.client.watchdog.daemonize")
    @mock.patch("landscape.client.watchdog.WatchDog")
    def test_dont_write_pid_file_until_we_really_start(
            self, mock_watchdog, mock_daemonize, mock_reactor):
        """
        If the client can't be started because another client is still running,
        the client shouldn't be daemonized and the pid file shouldn't be
        written.
        """
        mock_watchdog().check_running.return_value = succeed([StubDaemon()])
        mock_reactor.crash.return_value = None
        self.log_helper.ignore_errors(
            "ERROR: The following daemons are already running: program-name")
        pid_file = self.makeFile()

        self.configuration.daemon = True
        self.configuration.pid_file = pid_file
        service = WatchDogService(self.configuration)

        service.startService()
        self.assertFalse(os.path.exists(pid_file))
        mock_daemonize.assert_not_called()
        mock_watchdog().check_running.assert_called_once_with()
        mock_watchdog().start.assert_not_called()
        mock_reactor.crash.assert_called_once_with()

    @mock.patch("landscape.client.watchdog.daemonize")
    @mock.patch("landscape.client.watchdog.WatchDog")
    def test_remove_pid_file(self, mock_watchdog, mock_daemonize):
        """
        When the service is stopped, the pid file is removed.
        """
        mock_watchdog().start.return_value = succeed(None)
        mock_watchdog().check_running.return_value = succeed([])
        mock_watchdog().request_exit.return_value = succeed(None)

        pid_file = self.makeFile()
        self.configuration.daemon = True
        self.configuration.pid_file = pid_file
        service = WatchDogService(self.configuration)
        service.startService()
        self.assertEqual(int(open(pid_file).read()), os.getpid())
        service.stopService()
        self.assertFalse(os.path.exists(pid_file))
        self.assertTrue(mock_watchdog.called)
        mock_watchdog().start.assert_called_once_with()
        mock_watchdog().check_running.assert_called_once_with()
        self.assertTrue(mock_daemonize.called)
        self.assertTrue(mock_watchdog().request_exit.called)

    @mock.patch("landscape.client.watchdog.WatchDog")
    def test_remove_pid_file_only_when_ours(self, mock_watchdog):
        mock_watchdog().request_exit.return_value = succeed(None)
        pid_file = self.makeFile()
        self.configuration.pid_file = pid_file
        service = WatchDogService(self.configuration)
        open(pid_file, "w").write("abc")
        service.stopService()
        self.assertTrue(os.path.exists(pid_file))
        self.assertTrue(mock_watchdog().request_exit.called)

    # Make os.access say that the file isn't writable
    @mock.patch("landscape.client.watchdog.os.access", return_value=False)
    @mock.patch("landscape.client.watchdog.WatchDog")
    def test_remove_pid_file_doesnt_explode_on_inaccessibility(
            self, mock_watchdog, mock_access):
        mock_watchdog().request_exit.return_value = succeed(None)
        pid_file = self.makeFile()

        self.configuration.pid_file = pid_file
        service = WatchDogService(self.configuration)
        open(pid_file, "w").write(str(os.getpid()))
        service.stopService()
        self.assertTrue(mock_watchdog().request_exit.called)
        self.assertTrue(os.path.exists(pid_file))
        mock_access.assert_called_once_with(
            pid_file, os.W_OK)

    @mock.patch("landscape.client.watchdog.reactor")
    @mock.patch("landscape.client.watchdog.bootstrap_list")
    def test_start_service_exits_when_already_running(
            self, mock_bootstrap_list, mock_reactor):
        self.log_helper.ignore_errors(
            "ERROR: The following daemons are already running: program-name")
        service = WatchDogService(self.configuration)

        service.watchdog = mock.Mock()
        service.watchdog.check_running.return_value = succeed([StubDaemon()])
        result = service.startService()
        self.assertEqual(service.exit_code, 1)
        mock_bootstrap_list.bootstrap.assert_called_once_with(
            data_path=self.data_path, log_dir=self.log_dir)
        service.watchdog.check_running.assert_called_once_with()
        self.assertTrue(mock_reactor.crash.called)
        return result

    @mock.patch("landscape.client.watchdog.reactor")
    @mock.patch("landscape.client.watchdog.bootstrap_list")
    def test_start_service_exits_when_unknown_errors_occur(
            self, mock_bootstrap_list, mock_reactor):
        self.log_helper.ignore_errors(ZeroDivisionError)
        service = WatchDogService(self.configuration)

        service.watchdog = mock.Mock()
        service.watchdog.check_running.return_value = succeed([])
        deferred = fail(ZeroDivisionError("I'm an unknown error!"))
        service.watchdog.start.return_value = deferred

        result = service.startService()
        self.assertEqual(service.exit_code, 2)
        mock_bootstrap_list.bootstrap.assert_called_once_with(
            data_path=self.data_path, log_dir=self.log_dir)
        service.watchdog.check_running.assert_called_once_with()
        service.watchdog.start.assert_called_once_with()
        mock_reactor.crash.assert_called_once_with()
        return result

    @mock.patch("landscape.client.watchdog.os.chown")
    @mock.patch("landscape.lib.bootstrap.grp.getgrnam")
    @mock.patch("landscape.lib.bootstrap.os.getuid", return_value=0)
    def test_bootstrap(self, mock_getuid, mock_getgrnam, mock_chown):
        data_path = self.makeDir()
        log_dir = self.makeDir()
        fake_pwd = UserDatabase()
        fake_pwd.addUser("landscape", None, 1234, None, None, None, None)

        mock_getgrnam("root").gr_gid = 5678

        with mock.patch("landscape.lib.bootstrap.pwd", new=fake_pwd):
            bootstrap_list.bootstrap(data_path=data_path,
                                     log_dir=log_dir)

        def path(*suffix):
            return os.path.join(data_path, *suffix)

        paths = ["package",
                 "package/hash-id",
                 "package/binaries",
                 "package/upgrade-tool",
                 "messages",
                 "sockets",
                 "custom-graph-scripts",
                 log_dir,
                 "package/database"]
        calls = [mock.call(path(path_comps), 1234, 5678)
                 for path_comps in paths]
        mock_chown.assert_has_calls([mock.call(path(), 1234, 5678)] + calls)
        self.assertTrue(os.path.isdir(path()))
        self.assertTrue(os.path.isdir(path("package")))
        self.assertTrue(os.path.isdir(path("messages")))
        self.assertTrue(os.path.isdir(path("custom-graph-scripts")))
        self.assertTrue(os.path.isdir(log_dir))
        self.assertTrue(os.path.isfile(path("package/database")))

        def mode(*suffix):
            return stat.S_IMODE(os.stat(path(*suffix)).st_mode)

        self.assertEqual(mode(), 0o755)
        self.assertEqual(mode("messages"), 0o755)
        self.assertEqual(mode("package"), 0o755)
        self.assertEqual(mode("package/hash-id"), 0o755)
        self.assertEqual(mode("package/binaries"), 0o755)
        self.assertEqual(mode("sockets"), 0o750)
        self.assertEqual(mode("custom-graph-scripts"), 0o755)
        self.assertEqual(mode("package/database"), 0o644)


STUB_BROKER = """\
#!%(executable)s
import sys

import warnings
warnings.filterwarnings("ignore", "Python C API version mismatch",
                        RuntimeWarning)

from twisted.internet import reactor

sys.path = %(path)r

from landscape.lib.amp import MethodCallServerFactory
from landscape.client.broker.server import BrokerServer
from landscape.client.amp import get_remote_methods

class StubBroker(object):

    def exit(self):
        file = open(%(output_filename)r, "w")
        file.write("CALLED")
        file.close()
        reactor.callLater(1, reactor.stop)

stub_broker = StubBroker()
methods = get_remote_methods(BrokerServer)
factory = MethodCallServerFactory(stub_broker, methods)
reactor.listenUNIX(%(socket)r, factory)
reactor.run()
"""


class FakeReactor(Clock):
    running = False

    def run(self):
        self.running = True


class WatchDogRunTests(LandscapeTest):

    helpers = [EnvironSaverHelper]

    def setUp(self):
        super(WatchDogRunTests, self).setUp()
        self.fake_pwd = UserDatabase()

    @mock.patch("os.getuid", return_value=1000)
    def test_non_root(self, mock_getuid):
        """
        The watchdog should print an error message and exit if run by a normal
        user.
        """
        self.fake_pwd.addUser(
            "landscape", None, 1001, None, None, None, None)
        with mock.patch("landscape.client.watchdog.pwd", new=self.fake_pwd):
            sys_exit = self.assertRaises(SystemExit, run, ["landscape-client"])
        self.assertIn("landscape-client can only be run"
                      " as 'root' or 'landscape'.", str(sys_exit))

    def test_landscape_user(self):
        """
        The watchdog *can* be run as the 'landscape' user.
        """
        self.fake_pwd.addUser(
            "landscape", None, os.getuid(), None, None, None, None)
        reactor = FakeReactor()
        with mock.patch("landscape.client.watchdog.pwd", new=self.fake_pwd):
            run(["--log-dir", self.makeDir()], reactor=reactor)
        self.assertTrue(reactor.running)

    def test_no_landscape_user(self):
        """
        The watchdog should print an error message and exit if the
        'landscape' user doesn't exist.
        """
        with mock.patch("landscape.client.watchdog.pwd", new=self.fake_pwd):
            sys_exit = self.assertRaises(SystemExit, run, ["landscape-client"])
        self.assertIn("The 'landscape' user doesn't exist!", str(sys_exit))

    def test_clean_environment(self):
        self.fake_pwd.addUser(
            "landscape", None, os.getuid(), None, None, None, None)
        os.environ["DEBIAN_YO"] = "yo"
        os.environ["DEBCONF_YO"] = "yo"
        os.environ["LANDSCAPE_ATTACHMENTS"] = "some attachments"
        os.environ["MAIL"] = "/some/path"
        os.environ["UNRELATED"] = "unrelated"

        reactor = FakeReactor()
        with mock.patch("landscape.client.watchdog.pwd", new=self.fake_pwd):
            run(["--log-dir", self.makeDir()], reactor=reactor)
        self.assertNotIn("DEBIAN_YO", os.environ)
        self.assertNotIn("DEBCONF_YO", os.environ)
        self.assertNotIn("LANDSCAPE_ATTACHMENTS", os.environ)
        self.assertNotIn("MAIL", os.environ)
        self.assertEqual(os.environ["UNRELATED"], "unrelated")
