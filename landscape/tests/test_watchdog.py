import stat
import time
import sys
import os
import signal
import logging

import dbus

from twisted.internet.utils import getProcessOutput
from twisted.internet.defer import Deferred, succeed, fail
from twisted.internet import reactor

from landscape.broker.broker import BUS_NAME, OBJECT_PATH, IFACE_NAME
from landscape.tests.mocker import ARGS, KWARGS
from landscape.tests.clock import Clock
from landscape.tests.helpers import (
    LandscapeIsolatedTest, LandscapeTest, DBusHelper, RemoteBrokerHelper,
    EnvironSaverHelper)
from landscape.watchdog import (
    Daemon, WatchDog, WatchDogService, ExecutableNotFoundError,
    WatchDogConfiguration, bootstrap_list,
    MAXIMUM_CONSECUTIVE_RESTARTS, RESTART_BURST_DELAY, run,
    Broker, Monitor, Manager)
import landscape.watchdog


class StubDaemon(object):
    program = "program-name"


class WatchDogTest(LandscapeTest):
    """
    Tests for L{landscape.watchdog.WatchDog}.
    """

    def setUp(self):
        super(WatchDogTest, self).setUp()
        self.bus = object()
        self.broker_factory = self.mocker.replace("landscape.watchdog.Broker",
                                                  passthrough=False)
        self.monitor_factory = self.mocker.replace("landscape.watchdog.Monitor",
                                                   passthrough=False)
        self.manager_factory = self.mocker.replace("landscape.watchdog.Manager",
                                                   passthrough=False)

    def start_all_daemons(self):
        self.broker = self.broker_factory(self.bus, verbose=False,
                                          config=None)
        self.monitor = self.monitor_factory(self.bus, verbose=False,
                                            config=None)
        self.manager = self.manager_factory(self.bus, verbose=False,
                                            config=None)

        self.expect(self.broker.program).result("landscape-broker")
        self.mocker.count(0, None)
        self.expect(self.manager.program).result("landscape-manager")
        self.mocker.count(0, None)
        self.expect(self.monitor.program).result("landscape-monitor")
        self.mocker.count(0, None)

    def test_daemon_construction(self):
        """The WatchDog sets up some daemons when constructed."""
        self.start_all_daemons()
        self.mocker.replay()
        WatchDog(self.bus)

    def test_limited_daemon_construction(self):
        broker = self.broker_factory(self.bus, verbose=False, config=None)
        monitor = self.monitor_factory(self.bus, verbose=False, config=None)
        # The manager should *not* be constructed
        manager = self.manager_factory(ARGS, KWARGS)
        self.mocker.count(0)
        self.mocker.replay()

        WatchDog(self.bus, enabled_daemons=[Broker, Monitor])


    def test_check_running_one(self):
        self.start_all_daemons()
        self.expect(self.broker.is_running()).result(succeed(True))
        self.expect(self.monitor.is_running()).result(succeed(False))
        self.expect(self.manager.is_running()).result(succeed(False))
        self.mocker.replay()
        result = WatchDog(self.bus).check_running()
        def got_result(r):
            self.assertEquals([daemon.program for daemon in r],
                              ["landscape-broker"])
        return result.addCallback(got_result)

    def test_check_running_many(self):
        self.start_all_daemons()
        self.expect(self.broker.is_running()).result(succeed(True))
        self.expect(self.monitor.is_running()).result(succeed(True))
        self.expect(self.manager.is_running()).result(succeed(True))
        self.mocker.replay()
        result = WatchDog(self.bus).check_running()
        def got_result(r):
            self.assertEquals([daemon.program for daemon in r],
                              ["landscape-broker", "landscape-monitor",
                               "landscape-manager"])
        return result.addCallback(got_result)

    def test_check_running_limited_daemons(self):
        """
        When the user has explicitly asked not to run some daemons, those
        daemons which are not being run should not checked.
        """
        self.broker = self.broker_factory(self.bus, verbose=False,
                                          config=None)
        self.expect(self.broker.program).result("landscape-broker")
        self.expect(self.broker.is_running()).result(succeed(True))
        self.mocker.replay()
        result = WatchDog(self.bus, enabled_daemons=[Broker]).check_running()
        def got_result(r):
            self.assertEquals(len(r), 1)
            self.assertEquals(r[0].program, "landscape-broker")
        return result.addCallback(got_result)

    def expect_request_exit(self):
        self.expect(self.broker.request_exit()).result(succeed(False))
        self.expect(self.broker.wait_or_die()).result(succeed(None))
        self.expect(self.monitor.wait_or_die()).result(succeed(None))
        self.expect(self.manager.wait_or_die()).result(succeed(None))

    def test_start_and_stop_daemons(self):
        """The WatchDog will start all daemons, starting with the broker."""
        self.start_all_daemons()
        self.mocker.order()

        self.broker.start()
        self.monitor.start()
        self.manager.start()

        self.expect_request_exit()

        self.mocker.replay()

        clock = Clock()
        dog = WatchDog(self.bus, clock)
        dog.start()
        clock.advance(0)
        return dog.request_exit()

    def test_start_limited_daemons(self):
        """
        start only starts the daemons which are actually enabled.
        """
        self.broker = self.broker_factory(self.bus, verbose=False,
                                          config=None)
        self.expect(self.broker.program).result("landscape-broker")
        self.mocker.count(0, None)
        self.broker.start()

        self.mocker.replay()

        clock = Clock()
        dog = WatchDog(self.bus, clock, enabled_daemons=[Broker])
        dog.start()

    def test_request_exit(self):
        """request_exit() asks the broker to exit.

        The broker itself is responsible for notifying other plugins to exit.

        When the deferred returned from request_exit fires, the process should
        definitely be gone.
        """
        self.start_all_daemons()
        self.expect_request_exit()
        self.mocker.replay()
        return WatchDog(self.bus).request_exit()

    def test_ping_reply_after_request_exit_should_not_restart_processes(self):
        """
        When request_exit occurs between a ping request and response, a failing
        ping response should not cause the process to be restarted.
        """
        self.start_all_daemons()
        self.mocker.order()

        self.broker.start()
        self.monitor.start()
        self.manager.start()

        monitor_ping_result = Deferred()
        self.expect(self.broker.is_running()).result(succeed(True))
        self.expect(self.monitor.is_running()).result(monitor_ping_result)
        self.expect(self.manager.is_running()).result(succeed(True))

        self.expect_request_exit()

        # And the monitor should never be explicitly stopped / restarted.
        self.expect(self.monitor.stop()).count(0)
        self.expect(self.monitor.start()).count(0)

        self.mocker.replay()

        clock = Clock()

        dog = WatchDog(self.bus, clock)
        dog.start()
        clock.advance(0)
        clock.advance(5)
        result = dog.request_exit()
        monitor_ping_result.callback(False)
        return result


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
        return True

    def wait(self):
        return succeed(None)

    def wait_or_die(self):
        return self.wait()


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
    # mocker is hard

    def test_ping_is_not_rescheduled_until_pings_complete(self):
        clock = Clock()
        dog = WatchDog(object(), clock,
                       broker=AsynchronousPingDaemon("test-broker"),
                       monitor=AsynchronousPingDaemon("test-monitor"),
                       manager=AsynchronousPingDaemon("test-manager"))

        dog.start_monitoring()

        clock.advance(5)
        for daemon in dog.daemons:
            self.assertEquals(daemon.pings, 1)
        clock.advance(5)
        for daemon in dog.daemons:
            self.assertEquals(daemon.pings, 1)
            daemon.fire_running(True)
        clock.advance(5)
        for daemon in dog.daemons:
            self.assertEquals(daemon.pings, 2)

    def test_check_daemons(self):
        """
        The daemons are checked to be running every so often. When N=5 of these
        checks fail, the daemon will be restarted.
        """
        clock = Clock()
        dog = WatchDog(object(), clock,
                       broker=AsynchronousPingDaemon("test-broker"),
                       monitor=AsynchronousPingDaemon("test-monitor"),
                       manager=AsynchronousPingDaemon("test-manager"))
        dog.start_monitoring()


        for i in range(4):
            clock.advance(5)
            dog.broker.fire_running(False)
            dog.monitor.fire_running(True)
            dog.manager.fire_running(True)
            self.assertEquals(dog.broker.boots, [])

        clock.advance(5)
        dog.broker.fire_running(False)
        dog.monitor.fire_running(True)
        dog.manager.fire_running(True)
        self.assertEquals(dog.broker.boots, [STOP, START])

    def test_counted_ping_failures_reset_on_success(self):
        """
        When a failing ping is followed by a successful ping, it will then
        require 5 more ping failures to restart the daemon.
        """
        clock = Clock()
        dog = WatchDog(object(), clock,
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
            self.assertEquals(dog.broker.boots, [])

        clock.advance(5)
        dog.broker.fire_running(False)
        dog.monitor.fire_running(True)
        dog.manager.fire_running(True)
        self.assertEquals(dog.broker.boots, [STOP, START])

    def test_exiting_during_outstanding_ping_works(self):
        """
        This is a regression test. Some code called .cancel() on a timed call
        without checking if it was active first. Asynchronous is_running will
        cause the scheduled call to exist but already fired.
        """
        clock = Clock()
        dog = WatchDog(object(), clock,
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
        dog = WatchDog(object(), clock,
                       broker=AsynchronousPingDaemon("test-broker"),
                       monitor=BoringDaemon("test-monitor"),
                       manager=BoringDaemon("test-manager"))
        stop_result = Deferred()
        dog.broker.stop = lambda: stop_result
        dog.start_monitoring()

        for i in range(5):
            clock.advance(5)
            dog.broker.fire_running(False)

        self.assertEquals(dog.broker.boots, [])
        stop_result.callback(None)
        self.assertEquals(dog.broker.boots, ["start"])

    def test_wait_for_stop_before_ping(self):
        """
        When a daemon times out and the watchdog restarts it, it should not be
        pinged until after the restart completes.
        """
        clock = Clock()
        dog = WatchDog(object(), clock,
                       broker=AsynchronousPingDaemon("test-broker"),
                       monitor=BoringDaemon("test-monitor"),
                       manager=BoringDaemon("test-manager"))
        stop_result = Deferred()
        dog.broker.stop = lambda: stop_result
        dog.start_monitoring()

        for i in range(5):
            clock.advance(5)
            dog.broker.fire_running(False)

        self.assertEquals(dog.broker.boots, [])
        self.assertEquals(dog.broker.pings, 5)
        clock.advance(5) # wait some more to see if a ping happens
        self.assertEquals(dog.broker.pings, 5)
        stop_result.callback(None)
        self.assertEquals(dog.broker.boots, ["start"])
        clock.advance(5)
        self.assertEquals(dog.broker.pings, 6)

    def test_ping_failure_counter_reset_after_restart(self):
        """
        When a daemon stops responding and gets restarted after 5 failed pings,
        it will wait for another 5 failed pings before it will be restarted
        again.
        """
        clock = Clock()
        dog = WatchDog(object(), clock,
                       broker=AsynchronousPingDaemon("test-broker"),
                       monitor=BoringDaemon("test-monitor"),
                       manager=BoringDaemon("test-manager"))
        dog.start_monitoring()

        for i in range(5):
            clock.advance(5)
            dog.broker.fire_running(False)

        self.assertEquals(dog.broker.boots, ["stop", "start"])
        for i in range(4):
            clock.advance(5)
            dog.broker.fire_running(False)
            self.assertEquals(dog.broker.boots, ["stop", "start"])
        clock.advance(5)
        dog.broker.fire_running(False)
        self.assertEquals(dog.broker.boots, ["stop", "start", "stop", "start"])

    def test_die_when_broker_unavailable(self):
        """
        If the broker is not running, the client should still be able to shut
        down.
        """
        self.log_helper.ignore_errors(
            "Couldn't request that broker gracefully shut down; "
            "killing forcefully.")
        clock = Clock()
        dog = WatchDog(object(), clock,
                       broker=BoringDaemon("test-broker"),
                       monitor=BoringDaemon("test-monitor"),
                       manager=BoringDaemon("test-manager"))

        # request_exit returns False when there's no broker, as tested by
        # DaemonTest.test_request_exit_without_broker
        dog.broker.request_exit = lambda: False
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


class DaemonTestBase(LandscapeIsolatedTest):
    bus = None

    def setUp(self):
        super(DaemonTestBase, self).setUp()

        self.exec_dir = self.makeDir()
        self.exec_name = os.path.join(self.exec_dir, "landscape-broker")

        self.daemon = self.get_daemon()

        self.saved_argv = sys.argv
        sys.argv = [os.path.join(self.exec_dir, "arv0_execname")]

    def tearDown(self):
        sys.argv = self.saved_argv
        super(DaemonTestBase, self).tearDown()

    def get_daemon(self, **kwargs):
        daemon = Daemon(self.bus, **kwargs)
        daemon.program = os.path.basename(self.exec_name)
        daemon.bus_name = BUS_NAME
        daemon.object_path = OBJECT_PATH
        return daemon


class FileChangeWaiter(object):
    # XXX This should be reimplemented using a named pipe.

    def __init__(self, filename):
        os.utime(filename, (0, 0))
        self._mtime = os.path.getmtime(filename)
        self._filename = filename

    def wait(self):
        while self._mtime == os.path.getmtime(self._filename):
            time.sleep(0.1)


class DaemonTest(DaemonTestBase):

    helpers = [DBusHelper]

    def test_find_executable_works(self):
        self.makeFile("I'm the broker.", path=self.exec_name)
        self.assertEquals(self.daemon.find_executable(), self.exec_name)

    def test_find_executable_cant_find_file(self):
        self.assertRaises(ExecutableNotFoundError, self.daemon.find_executable)

    def test_start_process(self):
        output_filename = self.makeFile("NOT RUN")
        self.makeFile('#!/bin/sh\necho "RUN $@" > %s' % output_filename,
                      path=self.exec_name)
        os.chmod(self.exec_name, 0755)

        waiter = FileChangeWaiter(output_filename)

        self.daemon.start()

        waiter.wait()

        self.assertEquals(open(output_filename).read(),
                          "RUN --ignore-sigint --quiet\n")

        return self.daemon.stop()

    def test_start_process_with_verbose(self):
        output_filename = self.makeFile("NOT RUN")
        self.makeFile('#!/bin/sh\necho "RUN $@" > %s' % output_filename,
                      path=self.exec_name)
        os.chmod(self.exec_name, 0755)

        waiter = FileChangeWaiter(output_filename)

        daemon = self.get_daemon(verbose=True)
        daemon.start()

        waiter.wait()

        self.assertEquals(open(output_filename).read(), "RUN --ignore-sigint\n")

        return daemon.stop()

    def test_kill_process_with_sigterm(self):
        """The stop() method sends SIGTERM to the subprocess."""
        output_filename = self.makeFile("NOT RUN")
        self.makeFile("#!%s\n"
                      "import time\n"
                      "file = open(%r, 'w')\n"
                      "file.write('RUN')\n"
                      "file.close()\n"
                      "time.sleep(1000)\n"
                      % (sys.executable, output_filename),
                      path=self.exec_name)
        os.chmod(self.exec_name, 0755)

        waiter = FileChangeWaiter(output_filename)
        self.daemon.start()
        waiter.wait()
        self.assertEquals(open(output_filename).read(), "RUN")
        return self.daemon.stop()

    def test_kill_process_with_sigkill(self):
        """
        Verify that killing process really works, even if something is
        holding the process badly.  In these cases, a SIGKILL is performed
        some time after the SIGTERM was issued and didn't work.
        """
        output_filename = self.makeFile("NOT RUN")
        self.makeFile("#!%s\n"
                      "import signal, os\n"
                      "signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
                      "file = open(%r, 'w')\n"
                      "file.write('RUN')\n"
                      "file.close()\n"
                      "os.kill(os.getpid(), signal.SIGSTOP)\n"
                      % (sys.executable, output_filename),
                      path=self.exec_name)
        os.chmod(self.exec_name, 0755)

        self.addCleanup(setattr, landscape.watchdog, "SIGKILL_DELAY",
                        landscape.watchdog.SIGKILL_DELAY)
        landscape.watchdog.SIGKILL_DELAY = 1

        waiter = FileChangeWaiter(output_filename)
        self.daemon.start()
        waiter.wait()
        self.assertEquals(open(output_filename).read(), "RUN")
        return self.daemon.stop()

    def test_wait_for_process(self):
        """
        The C{wait} method returns a Deferred that fires when the process has
        died.
        """
        output_filename = self.makeFile("NOT RUN")
        self.makeFile('#!/bin/sh\necho "RUN" > %s' % output_filename,
                      path=self.exec_name)
        os.chmod(self.exec_name, 0755)

        self.daemon.start()
        def got_result(result):
            self.assertEquals(open(output_filename).read(), "RUN\n")
        return self.daemon.wait().addCallback(got_result)

    def test_wait_or_die_dies_happily(self):
        """
        The C{wait_or_die} method will wait for the process to die for a
        certain amount of time, just like C{wait}.
        """
        output_filename = self.makeFile("NOT RUN")
        self.makeFile('#!/bin/sh\necho "RUN" > %s' % output_filename,
                      path=self.exec_name)
        os.chmod(self.exec_name, 0755)

        self.daemon.start()
        def got_result(result):
            self.assertEquals(open(output_filename).read(), "RUN\n")
        return self.daemon.wait_or_die().addCallback(got_result)

    def test_wait_or_die_terminates(self):
        """wait_or_die eventually terminates the process."""
        output_filename = self.makeFile("NOT RUN")
        self.makeFile("""\
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
        """
                      % {"exe": sys.executable, "out": output_filename},
                      path=self.exec_name)
        os.chmod(self.exec_name, 0755)

        self.addCleanup(setattr, landscape.watchdog, "GRACEFUL_WAIT_PERIOD",
                        landscape.watchdog.GRACEFUL_WAIT_PERIOD)
        landscape.watchdog.GRACEFUL_WAIT_PERIOD = 0.2
        self.daemon.start()
        def got_result(result):
            self.assertEquals(open(output_filename).read(), "TERMINATED")
        return self.daemon.wait_or_die().addCallback(got_result)

    def test_wait_or_die_kills(self):
        """
        wait_or_die eventually falls back to KILLing a process, after waiting
        and terminating don't work.
        """
        output_filename = self.makeFile("NOT RUN")
        self.makeFile("#!%s\n"
                      "import signal, os\n"
                      "signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
                      "file = open(%r, 'w')\n"
                      "file.write('RUN')\n"
                      "file.close()\n"
                      "os.kill(os.getpid(), signal.SIGSTOP)\n"
                      % (sys.executable, output_filename),
                      path=self.exec_name)
        os.chmod(self.exec_name, 0755)

        self.addCleanup(setattr, landscape.watchdog, "SIGKILL_DELAY",
                        landscape.watchdog.SIGKILL_DELAY)
        self.addCleanup(setattr, landscape.watchdog, "GRACEFUL_WAIT_PERIOD",
                        landscape.watchdog.GRACEFUL_WAIT_PERIOD)
        landscape.watchdog.GRACEFUL_WAIT_PERIOD = 1
        landscape.watchdog.SIGKILL_DELAY = 1

        waiter = FileChangeWaiter(output_filename)
        self.daemon.start()
        waiter.wait()
        self.assertEquals(open(output_filename).read(), "RUN")
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
        l = []
        daemon.wait_or_die().addCallback(l.append)
        self.assertEquals(l, [None])


    def test_simulate_broker_not_starting_up(self):
        """
        When a daemon repeatedly dies, the watchdog gives up entirely and shuts
        down.
        """
        self.log_helper.ignore_errors("Can't keep landscape-broker running. "
                                      "Exiting.")

        output_filename = self.makeFile("NOT RUN")

        self.makeFile("#!/bin/sh\necho RUN >> %s" % output_filename,
                      path=self.exec_name)
        os.chmod(self.exec_name, 0755)

        def got_result(result):
            self.assertEquals(len(list(open(output_filename))),
                              MAXIMUM_CONSECUTIVE_RESTARTS)

            self.assertTrue("Can't keep landscape-broker running." in
                            self.logfile.getvalue())

        reactor_mock = self.mocker.proxy(reactor, passthrough=True)
        reactor_mock.stop()
        self.mocker.replay()

        result = Deferred()
        result.addCallback(lambda x: self.daemon.stop())
        result.addCallback(got_result)

        reactor.callLater(1, result.callback, None)

        daemon = self.get_daemon(reactor=reactor_mock)
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

        output_filename = self.makeFile("NOT RUN")

        self.makeFile("#!/bin/sh\necho RUN >> %s" % output_filename,
                      path=self.exec_name)
        os.chmod(self.exec_name, 0755)

        def got_result(result):
            # Pay attention to the +1 bellow. It's the reason for this test.
            self.assertEquals(len(list(open(output_filename))),
                              MAXIMUM_CONSECUTIVE_RESTARTS + 1)

            self.assertTrue("Can't keep landscape-broker running." in
                            self.logfile.getvalue())

        result = Deferred()
        result.addCallback(lambda x: self.daemon.stop())
        result.addCallback(got_result)

        reactor_mock = self.mocker.proxy(reactor, passthrough=True)
        reactor_mock.stop()

        # Make the *first* call to time return 0, so that it will try one
        # more time, and exercise the burst protection system.
        time_mock = self.mocker.replace("time.time")
        self.expect(time_mock()).result(time.time() - RESTART_BURST_DELAY)
        self.expect(time_mock()).passthrough().count(0, None)

        self.mocker.replay()

        # It's important to call start() shortly after the mocking above,
        # as we don't want anyone else getting the fake time.
        daemon = self.get_daemon(reactor=reactor_mock)
        daemon.start()

        reactor.callLater(1, result.callback, None)

        return result

    def test_is_not_running(self):
        result = self.daemon.is_running()
        result.addCallback(self.assertFalse)
        return result

    def test_spawn_process_with_uid(self):
        """
        When the current UID as reported by os.getuid is not the uid of the
        username of the daemon, the watchdog explicitly switched to the uid of
        the username of the daemon. It also specified the gid as the primary
        group of that user.
        """
        self.makeFile("", path=self.exec_name)

        getuid = self.mocker.replace("os.getuid")
        getpwnam = self.mocker.replace("pwd.getpwnam")
        reactor = self.mocker.mock()
        self.expect(getuid()).result(0)
        info = getpwnam("landscape")
        self.expect(info.pw_uid).result(123)
        self.expect(info.pw_gid).result(456)
        self.expect(info.pw_dir).result("/var/lib/landscape")

        env = os.environ.copy()
        env["HOME"] = "/var/lib/landscape"
        env["USER"] = "landscape"
        env["LOGNAME"] = "landscape"

        reactor.spawnProcess(ARGS, KWARGS, env=env, uid=123, gid=456)

        self.mocker.replay()

        daemon = self.get_daemon(reactor=reactor)
        daemon.start()

    def test_spawn_process_without_uid(self):
        """
        If the daemon is specified to run as the current user, no uid or gid
        switching will occur.
        """
        self.makeFile("", path=self.exec_name)
        getuid = self.mocker.replace("os.getuid")
        reactor = self.mocker.mock()
        self.expect(getuid()).result(555)

        reactor.spawnProcess(ARGS, KWARGS, uid=None, gid=None)

        self.mocker.replay()

        daemon = self.get_daemon(reactor=reactor)
        daemon.start()

    def test_request_exit(self):
        """The request_exit() method calls exit() on the broker synchronously.

        The method must be synchronous because we don't want the watchdog to
        do anything else while we're requesting the broker to exit.  This makes
        testing it a bit wild unfortunately.  We have to spawn the a stub
        broker into a different process.
        """

        output_filename = self.makeFile("NOT CALLED")
        broker_filename = self.makeFile(STUB_BROKER %
                                        {"executable": sys.executable,
                                         "path": sys.path,
                                         "output_filename": output_filename,
                                         "bus_name": BUS_NAME,
                                         "object_path": OBJECT_PATH,
                                         "iface_name": IFACE_NAME})

        os.chmod(broker_filename, 0755)

        process_result = getProcessOutput(broker_filename, env=os.environ,
                                          errortoo=True)

        # Wait until the process starts up, trying the call a few times.
        for i in range(50):
            if self.daemon.request_exit():
                break
            time.sleep(0.1)
        else:
            self.fail("request_exit() never returned True.")

        def got_result(result):
            self.assertEquals(result, "")
            self.assertEquals(open(output_filename).read(), "CALLED")

        return process_result.addCallback(got_result)

    def test_request_exit_without_broker(self):
        """
        The request_exit method returns False when the broker can't be
        contacted.
        """
        self.assertFalse(self.daemon.request_exit())


class DaemonBrokerTest(DaemonTestBase):

    helpers = [RemoteBrokerHelper]

    @property
    def bus(self):
        return self.broker_service.bus

    def test_is_running(self):
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
        self.assertEquals(self.config.pid_file, "wubble.txt")

    def test_pid_file_default(self):
        self.config.load([])
        self.assertEquals(self.config.pid_file, None)

    def test_monitor_only(self):
        self.config.load(["--monitor-only"])
        self.assertEquals(self.config.get_enabled_daemons(),
                          [Broker, Monitor])

    def test_default_daemons(self):
        self.config.load([])
        self.assertEquals(self.config.get_enabled_daemons(),
                          [Broker, Monitor, Manager])


class WatchDogServiceTest(LandscapeTest):

    def setUp(self):
        super(WatchDogServiceTest, self).setUp()
        self.configuration = WatchDogConfiguration()
        self.data_path = self.makeDir()
        self.log_dir = self.makeDir()
        self.configuration.load(["--bus", "system",
                                 "--data-path", self.data_path,
                                 "--log-dir", self.log_dir])

    def test_daemonize(self):
        self.mocker.order()
        watchdog = self.mocker.patch(WatchDog)
        watchdog.check_running()
        self.mocker.result(succeed([]))
        daemonize = self.mocker.replace("landscape.watchdog.daemonize",
                                        passthrough=False)
        daemonize()
        watchdog.start()
        self.mocker.result(succeed(None))

        self.mocker.replay()
        self.configuration.daemon = True

        service = WatchDogService(self.configuration)
        service.startService()

    def test_pid_file(self):
        pid_file = self.makeFile()

        watchdog = self.mocker.patch(WatchDog)
        watchdog.check_running()
        self.mocker.result(succeed([]))
        daemonize = self.mocker.replace("landscape.watchdog.daemonize",
                                        passthrough=False)
        daemonize()
        watchdog.start()
        self.mocker.result(succeed(None))

        self.mocker.replay()
        self.configuration.daemon = True
        self.configuration.pid_file = pid_file

        service = WatchDogService(self.configuration)
        service.startService()
        self.assertEquals(int(open(pid_file, "r").read()), os.getpid())

    def test_dont_write_pid_file_until_we_really_start(self):
        """
        If the client can't be started because another client is still running,
        the client shouldn't be daemonized and the pid file shouldn't be
        written.
        """
        self.log_helper.ignore_errors(
            "ERROR: The following daemons are already running: program-name")
        pid_file = self.makeFile()

        daemonize = self.mocker.replace("landscape.watchdog.daemonize",
                                        passthrough=False)
        daemonize()
        # daemonize should *not* be called
        self.mocker.count(0)

        watchdog = self.mocker.patch(WatchDog)
        watchdog.check_running()
        self.mocker.result(succeed([StubDaemon()]))
        watchdog.start()
        self.mocker.count(0)

        reactor = self.mocker.replace("twisted.internet.reactor",
                                      passthrough=False)
        reactor.crash()

        self.mocker.replay()

        self.configuration.daemon = True
        self.configuration.pid_file = pid_file
        service = WatchDogService(self.configuration)

        try:
            service.startService()
            self.mocker.verify()
        finally:
            self.mocker.reset()
        self.assertFalse(os.path.exists(pid_file))

    def test_remove_pid_file(self):
        """
        When the service is stopped, the pid file is removed.
        """
        #don't really daemonize or request an exit
        daemonize = self.mocker.replace("landscape.watchdog.daemonize",
                                        passthrough=False)
        watchdog_factory = self.mocker.replace("landscape.watchdog.WatchDog",
                                               passthrough=False)
        watchdog = watchdog_factory(ARGS, KWARGS)
        watchdog.start()
        self.mocker.result(succeed(None))

        watchdog.check_running()
        self.mocker.result(succeed([]))

        daemonize()

        watchdog.request_exit()
        self.mocker.result(succeed(None))

        self.mocker.replay()

        pid_file = self.makeFile()
        self.configuration.daemon = True
        self.configuration.pid_file = pid_file
        service = WatchDogService(self.configuration)
        service.startService()
        self.assertEquals(int(open(pid_file).read()), os.getpid())
        service.stopService()
        self.assertFalse(os.path.exists(pid_file))

    def test_remove_pid_file_only_when_ours(self):
        #don't really request an exit
        watchdog = self.mocker.patch(WatchDog)
        watchdog.request_exit()
        self.mocker.result(succeed(None))

        self.mocker.replay()

        pid_file = self.makeFile()
        self.configuration.pid_file = pid_file
        service = WatchDogService(self.configuration)
        open(pid_file, "w").write("abc")
        service.stopService()
        self.assertTrue(os.path.exists(pid_file))

    def test_remove_pid_file_doesnt_explode_on_inaccessibility(self):
        pid_file = self.makeFile()
        # Make os.access say that the file isn't writable
        mock_os = self.mocker.replace("os")
        mock_os.access(pid_file, os.W_OK)
        self.mocker.result(False)

        watchdog = self.mocker.patch(WatchDog)
        watchdog.request_exit()
        self.mocker.result(succeed(None))
        self.mocker.replay()

        self.configuration.pid_file = pid_file
        service = WatchDogService(self.configuration)
        open(pid_file, "w").write(str(os.getpid()))
        service.stopService()
        self.assertTrue(os.path.exists(pid_file))

    def test_start_service_uses_right_bus(self):
        service = WatchDogService(self.configuration)
        self.assertEquals(type(service.bus), dbus.SystemBus)

    def test_start_service_exits_when_already_running(self):
        self.log_helper.ignore_errors(
            "ERROR: The following daemons are already running: program-name")

        bootstrap_list_mock = self.mocker.patch(bootstrap_list)
        bootstrap_list_mock.bootstrap(data_path=self.data_path,
                                      log_dir=self.log_dir)

        service = WatchDogService(self.configuration)

        self.mocker.order()

        watchdog_mock = self.mocker.replace(service.watchdog)
        watchdog_mock.check_running()
        self.mocker.result(succeed([StubDaemon()]))

        reactor = self.mocker.replace("twisted.internet.reactor",
                                      passthrough=False)
        reactor.crash()

        self.mocker.replay()
        try:
            result = service.startService()
            self.mocker.verify()
        finally:
            self.mocker.reset()
        self.assertEquals(service.exit_code, 1)
        return result

    def test_start_service_exits_when_unknown_errors_occur(self):
        self.log_helper.ignore_errors(ZeroDivisionError)
        service = WatchDogService(self.configuration)

        bootstrap_list_mock = self.mocker.patch(bootstrap_list)
        bootstrap_list_mock.bootstrap(data_path=self.data_path,
                                      log_dir=self.log_dir)

        self.mocker.order()

        watchdog_mock = self.mocker.replace(service.watchdog)
        watchdog_mock.check_running()
        self.mocker.result(succeed([]))
        watchdog_mock.start()
        deferred = fail(ZeroDivisionError("I'm an unknown error!"))
        self.mocker.result(deferred)

        reactor = self.mocker.replace("twisted.internet.reactor",
                                      passthrough=False)
        reactor.crash()

        self.mocker.replay()
        try:
            result = service.startService()
            self.mocker.verify()
        finally:
            self.mocker.reset()
        self.assertEquals(service.exit_code, 2)
        return result

    def test_bootstrap(self):

        data_path = self.makeDir()
        log_dir = self.makeDir()

        def path(*suffix):
            return os.path.join(data_path, *suffix)

        getuid = self.mocker.replace("os.getuid")
        getuid()
        self.mocker.result(0)
        self.mocker.count(1, None)

        getpwnam = self.mocker.replace("pwd.getpwnam")
        value = getpwnam("landscape")
        self.mocker.count(1, None)
        value.pw_uid
        self.mocker.result(1234)
        self.mocker.count(1, None)

        getgrnam = self.mocker.replace("grp.getgrnam")
        value = getgrnam("root")
        self.mocker.count(1, None)
        value.gr_gid
        self.mocker.result(5678)
        self.mocker.count(1, None)

        chown = self.mocker.replace("os.chown")
        chown(path(), 1234, 5678)
        chown(path("messages"), 1234, 5678)
        chown(path("package"), 1234, 5678)
        chown(path("package/hash-id"), 1234, 5678)
        chown(path("package/upgrade-tool"), 1234, 5678)
        chown(path("custom-graph-scripts"), 1234, 5678)
        chown(path("package/database"), 1234, 5678)
        chown(log_dir, 1234, 5678)

        self.mocker.replay()

        bootstrap_list.bootstrap(data_path=data_path,
                                 log_dir=log_dir)

        self.assertTrue(os.path.isdir(path()))
        self.assertTrue(os.path.isdir(path("package")))
        self.assertTrue(os.path.isdir(path("messages")))
        self.assertTrue(os.path.isdir(path("custom-graph-scripts")))
        self.assertTrue(os.path.isdir(log_dir))
        self.assertTrue(os.path.isfile(path("package/database")))

        def mode(*suffix):
            return stat.S_IMODE(os.stat(path(*suffix)).st_mode)

        self.assertEquals(mode(), 0755)
        self.assertEquals(mode("messages"), 0755)
        self.assertEquals(mode("package"), 0755)
        self.assertEquals(mode("custom-graph-scripts"), 0755)
        self.assertEquals(mode("package/database"), 0644)

    def test_log_notification(self):
        """
        SIGUSR1 should cause logs to be reopened.
        """
        logging.getLogger().addHandler(logging.FileHandler(self.makeFile()))
        service = WatchDogService(self.configuration)
        # We expect the Watchdog to delegate to each of the sub-processes
        daemon_mock = self.mocker.patch(Daemon)
        daemon_mock.rotate_logs()
        self.mocker.count(3)
        self.mocker.replay()

        # Store the initial set of handlers
        original_streams = [handler.stream for handler in
                            logging.getLogger().handlers if
                            isinstance(handler, logging.FileHandler)]

        # We fire the signal
        os.kill(os.getpid(), signal.SIGUSR1)
        new_streams = [handler.stream for handler in
                       logging.getLogger().handlers if
                       isinstance(handler, logging.FileHandler)]

        for stream in new_streams:
            self.assertTrue(stream not in original_streams)


STUB_BROKER = """\
#!%(executable)s
import sys

import warnings
warnings.filterwarnings("ignore", "Python C API version mismatch",
                        RuntimeWarning)

from dbus import SessionBus
import dbus.glib

from twisted.internet.glib2reactor import install
install()
from twisted.internet import reactor

sys.path = %(path)r

from landscape.lib.dbus_util import Object, method


class StubBroker(Object):
    bus_name = %(bus_name)r
    object_path = %(object_path)r

    @method(%(iface_name)r)
    def exit(self):
        file = open(%(output_filename)r, "w")
        file.write("CALLED")
        file.close()
        reactor.callLater(1, reactor.stop)

stub_broker = StubBroker(SessionBus())

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
        self.addCleanup(setattr, WatchDogConfiguration,
                        "default_config_filenames",
                        WatchDogConfiguration.default_config_filenames)
        WatchDogConfiguration.default_config_filenames = []

    def test_non_root(self):
        """
        The watchdog should print an error message and exit if run by a normal
        user.
        """
        self.mocker.replace("os.getuid")()
        self.mocker.count(1, None)
        self.mocker.result(1000)
        getpwnam = mock = self.mocker.replace("pwd.getpwnam")
        getpwnam("landscape").pw_uid
        self.mocker.result(1001)
        self.mocker.replay()
        sys_exit = self.assertRaises(SystemExit, run, ["--bus", "system"])
        self.assertIn("landscape-client must be run as root", str(sys_exit))

    def test_landscape_user(self):
        """
        The watchdog *can* be run as the 'landscape' user.
        """
        getpwnam = self.mocker.replace("pwd.getpwnam")
        getpwnam("landscape").pw_uid
        self.mocker.result(os.getuid())
        self.mocker.replay()
        reactor = FakeReactor()
        run(["--bus", "system", "--log-dir", self.makeFile()],
            reactor=reactor)
        self.assertTrue(reactor.running)

    def test_clean_environment(self):
        os.environ["DEBIAN_YO"] = "yo"
        os.environ["DEBCONF_YO"] = "yo"
        os.environ["LANDSCAPE_ATTACHMENTS"] = "some attachments"
        os.environ["MAIL"] = "/some/path"
        os.environ["UNRELATED"] = "unrelated"

        reactor = FakeReactor()
        run(["--bus", "session", "--log-dir", self.makeFile()],
            reactor=reactor)
        self.assertNotIn("DEBIAN_YO", os.environ)
        self.assertNotIn("DEBCONF_YO", os.environ)
        self.assertNotIn("LANDSCAPE_ATTACHMENTS", os.environ)
        self.assertNotIn("MAIL", os.environ)
        self.assertEquals(os.environ["UNRELATED"], "unrelated")
