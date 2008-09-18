"""See L{WatchDog}.

The WatchDog must run as root, because it spawns the Landscape Manager.

The main C{landscape-client} program uses this watchdog.
"""

import os
import errno
import sys
import pwd
import signal
import time

from logging import warning, info, error

from dbus import DBusException
import dbus.glib # Side-effects rule!

from twisted.internet import reactor
from twisted.internet.defer import Deferred, succeed
from twisted.internet.protocol import ProcessProtocol
from twisted.internet.error import ProcessExitedAlready
from twisted.application.service import Service, Application
from twisted.application.app import startApplication

from landscape.deployment import Configuration, init_logging
from landscape.lib.dbus_util import get_bus
from landscape.lib.twisted_util import gather_results
from landscape.lib.log import log_failure
from landscape.lib.bootstrap import (BootstrapList, BootstrapFile,
                                     BootstrapDirectory)
from landscape.log import rotate_logs

GRACEFUL_WAIT_PERIOD = 10
MAXIMUM_CONSECUTIVE_RESTARTS = 5
RESTART_BURST_DELAY = 30 # seconds
SIGKILL_DELAY = 10


class DaemonError(Exception):
    """One of the daemons could not be started."""


class TimeoutError(Exception):
    """Something took too long."""


class ExecutableNotFoundError(Exception):
    """An executable was not found."""


class Daemon(object):
    """A Landscape daemon which can be started and tracked.

    This class should be subclassed to specify individual daemon.

    @cvar program: The name of the executable program that will start this
        daemon.
    @cvar username: The name of the user to switch to, by default.
    @cvar service: The DBus service name that the program will be expected to
        listen on.
    @cvar path: The DBus path that the program will be expected to listen on.
    """

    username = "landscape"

    def __init__(self, bus, reactor=reactor, verbose=False, config=None):
        """
        @param bus: The bus which this program will listen and respond to pings
            on.
        @param reactor: The reactor with which to spawn the process and
            schedule timed calls.
        @param verbose: Optionally, report more information when
            running this program.  Defaults to False.
        """
        self._bus = bus
        self._reactor = reactor
        if os.getuid() == 0:
            info = pwd.getpwnam(self.username)
            self._uid = info.pw_uid
            self._gid = info.pw_gid
        else:
            # We can only switch UIDs if we're root, so simply don't switch
            # UIDs if we're not.
            self._uid = None
            self._gid = None
        self._verbose = verbose
        self._config = config
        self._process = None
        self._last_started = 0
        self._quick_starts = 0

    def find_executable(self):
        """Find the fully-qualified path to the executable.

        If the executable can't be found, L{ExecutableNotFoundError} will be
        raised.
        """
        dirname = os.path.dirname(os.path.abspath(sys.argv[0]))
        executable = os.path.join(dirname, self.program)
        if not os.path.exists(executable):
            raise ExecutableNotFoundError("%s doesn't exist" % (executable,))
        return executable

    def start(self):
        """Start this daemon."""
        self._process = None

        now = time.time()
        if self._last_started + RESTART_BURST_DELAY > now:
            self._quick_starts += 1
            if self._quick_starts == MAXIMUM_CONSECUTIVE_RESTARTS:
                error("Can't keep %s running. Exiting." % self.program)
                self._reactor.stop()
                return
        else:
            self._quick_starts = 0

        self._last_started = now

        self._process = WatchedProcessProtocol(self)
        exe = self.find_executable()
        args = [exe, "--ignore-sigint"]
        if not self._verbose:
            args.append("--quiet")
        if self._config:
            args.extend(["-c", self._config])
        self._reactor.spawnProcess(self._process, exe, args=args,
                                   env=os.environ,uid=self._uid, gid=self._gid)

    def stop(self):
        """Stop this daemon."""
        if not self._process:
            return succeed(None)
        return self._process.kill()

    def request_exit(self):
        try:
            object = self._bus.get_object(self.bus_name, self.object_path,
                                          introspect=False)
            object.exit(dbus_interface=self.bus_name)
        except DBusException, e:
            return False
        return True

    def is_running(self):
        # FIXME Error cases may not be handled in the best possible way
        # here. We're basically return False if any error happens from the
        # dbus ping.
        result = Deferred()
        try:
            object = self._bus.get_object(self.bus_name, self.object_path,
                                          introspect=False)
            object.ping(reply_handler=result.callback,
                        error_handler=lambda f: result.callback(False),
                        dbus_interface=self.bus_name)
        except DBusException, e:
            result.callback(False)
        return result

    def wait(self):
        """
        Return a Deferred which will fire when the process has died.
        """
        if not self._process:
            return succeed(None)
        return self._process.wait()

    def wait_or_die(self):
        """
        Wait for the process to die for C{GRACEFUL_WAIT_PERIOD}. If it hasn't
        died by that point, send it a SIGTERM. If it doesn't die for
        C{SIGKILL_DELAY},
        """
        if not self._process:
            return succeed(None)
        return self._process.wait_or_die()

    def rotate_logs(self):
        self._process.rotate_logs()


class Broker(Daemon):
    program = "landscape-broker"

    from landscape.broker.broker import BUS_NAME as bus_name
    from landscape.broker.broker import OBJECT_PATH as object_path


class Monitor(Daemon):
    program = "landscape-monitor"

    from landscape.monitor.monitor import BUS_NAME as bus_name
    from landscape.monitor.monitor import OBJECT_PATH as object_path


class Manager(Daemon):
    program = "landscape-manager"
    username = "root"

    from landscape.manager.manager import BUS_NAME as bus_name
    from landscape.manager.manager import OBJECT_PATH as object_path


class WatchedProcessProtocol(ProcessProtocol):
    """
    A process-watching protocol which sends any of its output to the log file
    and restarts it when it dies.
    """

    _killed = False

    def __init__(self, daemon):
        self.daemon = daemon
        self._wait_result = None
        self._delayed_really_kill = None
        self._delayed_terminate = None

    def kill(self):
        self._terminate()
        return self.wait()

    def _terminate(self, warn=False):
        if self.transport is not None:
            if warn:
                warning("%s didn't exit. Sending SIGTERM"
                        % (self.daemon.program,))
            try:
                self.transport.signalProcess(signal.SIGTERM)
            except ProcessExitedAlready:
                pass
            else:
                # Give some time for the process, and then show who's the boss.
                delayed = reactor.callLater(SIGKILL_DELAY, self._really_kill)
                self._delayed_really_kill = delayed

    def _really_kill(self):
        try:
            self.transport.signalProcess(signal.SIGKILL)
        except ProcessExitedAlready:
            pass
        else:
            warning("%s didn't die.  Sending SIGKILL." % self.daemon.program)
        self._delayed_really_kill = None

    def rotate_logs(self):
        if self.transport is not None:
            try:
                self.transport.signalProcess(signal.SIGUSR1)
            except ProcessExitedAlready:
                pass

    def wait(self):
        self._wait_result = Deferred()
        return self._wait_result

    def wait_or_die(self):
        self._delayed_terminate = reactor.callLater(GRACEFUL_WAIT_PERIOD,
                                                    self._terminate, warn=True)
        return self.wait()

    def outReceived(self, data):
        # it's *probably* going to always be line buffered, by accident
        sys.stdout.write(data)

    def errReceived(self, data):
        sys.stderr.write(data)

    def processEnded(self, reason):
        """The process has ended; restart it."""
        if self._delayed_really_kill is not None:
            self._delayed_really_kill.cancel()
        if (self._delayed_terminate is not None
            and self._delayed_terminate.active()):
            self._delayed_terminate.cancel()
        if self._wait_result is not None:
            self._wait_result.callback(None)
        else:
            self.daemon.start()


class WatchDog(object):
    """
    The Landscape WatchDog starts all other landscape daemons and ensures that
    they are working.
    """

    def __init__(self, bus, reactor=reactor, verbose=False, config=None,
                 broker=None, monitor=None, manager=None):
        self.bus = bus
        if broker is None:
            broker = Broker(self.bus, verbose=verbose, config=config)
        if monitor is None:
            monitor = Monitor(self.bus, verbose=verbose, config=config)
        if manager is None:
            manager = Manager(self.bus, verbose=verbose, config=config)

        self.broker = broker
        self.monitor = monitor
        self.manager = manager
        self.daemons = [self.broker, self.monitor, self.manager]
        self.reactor = reactor
        self._checking = None
        self._stopping = False
        signal.signal(signal.SIGUSR1, self._notify_rotate_logs)

        self._ping_failures = {}

    def check_running(self):
        """Return a list of any daemons that are already running."""
        results = []
        for daemon in self.daemons:
            result = daemon.is_running()
            result.addCallback(lambda is_running, d=daemon: (is_running, d))
            results.append(result)
        def got_all_results(r):
            return [x[1] for x in r if x[0]]
        return gather_results(results).addCallback(got_all_results)

    def start(self):
        """
        Start all daemons. The broker will be started first, and no other
        daemons will be started before it is running and responding to DBUS
        messages.

        @return: A deferred which fires when all services have successfully
            started. If a daemon could not be started, the deferred will fail
            with L{DaemonError}.
        """
        self.broker.start()
        self.monitor.start()
        self.manager.start()
        self.start_monitoring()

    def start_monitoring(self):
        """Start monitoring processes which have already been started."""
        # Must wait before daemons actually start, otherwise check will
        # restart them *again*.
        self._checking = self.reactor.callLater(5, self._check)

    def _restart_if_not_running(self, is_running, daemon):
        if (not is_running) and (not self._stopping):
            warning("%s failed to respond to a ping."
                    % (daemon.program,))
            if daemon not in self._ping_failures:
                self._ping_failures[daemon] = 0
            self._ping_failures[daemon] += 1
            if self._ping_failures[daemon] == 5:
                warning("%s died! Restarting." % (daemon.program,))
                stopping = daemon.stop()
                def stopped(ignored):
                    daemon.start()
                    self._ping_failures[daemon] = 0
                stopping.addBoth(stopped)
                return stopping
        else:
            self._ping_failures[daemon] = 0

    def _check(self):
        all_running = []
        for daemon in self.daemons:
            is_running = daemon.is_running()
            is_running.addCallback(self._restart_if_not_running, daemon)
            all_running.append(is_running)
        def reschedule(ignored):
            self._checking = self.reactor.callLater(5, self._check)
        gather_results(all_running).addBoth(reschedule)

    def request_exit(self):
        if self._checking is not None and self._checking.active():
            self._checking.cancel()
        # Set a flag so that the pinger will avoid restarting the daemons if a
        # ping has already been sent but not yet responded to.
        self._stopping = True

        # If request_exit fails, we should just kill the daemons immediately.
        if self.broker.request_exit():
            results = [x.wait_or_die() for x in self.daemons]
        else:
            error("Couldn't request that broker gracefully shut down; "
                  "killing forcefully.")
            results = [x.stop() for x in self.daemons]
        return gather_results(results)

    def _notify_rotate_logs(self, signal, frame):
        for daemon in self.daemons:
            daemon.rotate_logs()
        rotate_logs()


class WatchDogConfiguration(Configuration):

    def make_parser(self):
        parser = super(WatchDogConfiguration, self).make_parser()
        parser.add_option("--daemon", action="store_true",
                          help="Fork and run in the background.")
        parser.add_option("--pid-file", type="str",
                          help="The file to write the PID to.")
        return parser


def daemonize():
    # See http://web.archive.org/web/20070410070022/www.erlenstar.demon.co.uk/unix/faq_2.html#SEC13
    if os.fork():   # launch child and...
        os._exit(0) # kill off parent
    os.setsid()
    if os.fork():   # launch child and...
        os._exit(0) # kill off parent again.
    # some argue that this umask should be 0, but that's annoying.
    os.umask(077)
    null=os.open('/dev/null', os.O_RDWR)
    for i in range(3):
        try:
            os.dup2(null, i)
        except OSError, e:
            if e.errno != errno.EBADF:
                raise
    os.close(null)


class WatchDogService(Service):

    def __init__(self, config):
        self._config = config
        self.bus = get_bus(config.bus)
        self.watchdog = WatchDog(self.bus,
                                 verbose=not config.daemon,
                                 config=config.config)
        self.exit_code = 0

    def startService(self):
        Service.startService(self)

        bootstrap_list.bootstrap(data_path=self._config.data_path,
                                 log_dir=self._config.log_dir)

        result = self.watchdog.check_running()

        def start_if_not_running(running_daemons):
            if running_daemons:
                error("ERROR: The following daemons are already running: %s"
                      % (", ".join(x.program for x in running_daemons)))
                self.exit_code = 1
                reactor.crash() # so stopService isn't called.
                return
            self._daemonize()
            info("Watchdog watching for daemons on %r bus." % self._config.bus)
            return self.watchdog.start()
        def die(failure):
            self.exit_code = 2
            reactor.crash()
        result.addCallback(start_if_not_running)
        result.addErrback(die)

        return result

    def _daemonize(self):
        if self._config.daemon:
            daemonize()
            if self._config.pid_file:
                stream = open(self._config.pid_file, "w")
                stream.write(str(os.getpid()))
                stream.close()

    def stopService(self):
        info("Stopping client...")
        Service.stopService(self)

        # If CTRL-C is pressed twice in a row, the second SIGINT actually
        # kills us before subprocesses die, and that makes them hang around.
        signal.signal(signal.SIGINT, signal.SIG_IGN)

        return self.watchdog.request_exit()


bootstrap_list = BootstrapList([
    BootstrapDirectory("$data_path", "landscape", "root", 0755),
    BootstrapDirectory("$data_path/package", "landscape", "root", 0755),
    BootstrapDirectory("$data_path/messages", "landscape", "root", 0755),
    BootstrapDirectory("$log_dir", "landscape", "root", 0755),
    BootstrapFile("$data_path/package/database", "landscape", "root", 0644),
    ])


def run(args=sys.argv):
    config = WatchDogConfiguration()
    config.load(args)

    init_logging(config, "watchdog")

    if os.getuid() != 0:
        warning("Daemons will be run as %s" % pwd.getpwuid(os.getuid()).pw_name)

    application = Application("landscape-client")
    watchdog_service = WatchDogService(config)
    watchdog_service.setServiceParent(application)

    from twisted.internet import reactor
    # We add a small delay to work around a Twisted bug: this method should
    # only be called when the reactor is running, but we still get a
    # PotentialZombieWarning.
    reactor.callLater(0, startApplication, application, False)

    reactor.run()
    return watchdog_service.exit_code
