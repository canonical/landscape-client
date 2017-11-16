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
from resource import setrlimit, RLIMIT_NOFILE

from twisted.internet import reactor
from twisted.internet.defer import Deferred, succeed
from twisted.internet.protocol import ProcessProtocol
from twisted.internet.error import ProcessExitedAlready
from twisted.application.service import Service, Application
from twisted.application.app import startApplication

from landscape.client.deployment import init_logging, Configuration
from landscape.lib.config import get_bindir
from landscape.lib.encoding import encode_values
from landscape.lib.twisted_util import gather_results
from landscape.lib.log import log_failure
from landscape.lib.logging import rotate_logs
from landscape.lib.bootstrap import (BootstrapList, BootstrapFile,
                                     BootstrapDirectory)
from landscape.client.broker.amp import (
    RemoteBrokerConnector, RemoteMonitorConnector, RemoteManagerConnector)
from landscape.client.reactor import LandscapeReactor

GRACEFUL_WAIT_PERIOD = 10
MAXIMUM_CONSECUTIVE_RESTARTS = 5
RESTART_BURST_DELAY = 30  # seconds
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
    @cvar max_retries: The maximum number of retries before giving up when
        trying to connect to the watched daemon.
    @cvar factor: The factor by which the delay between subsequent connection
        attempts will increase.

    @param connector: The L{ComponentConnector} of the daemon.
    @param reactor: The reactor used to spawn the process and schedule timed
        calls.
    @param verbose: Optionally, report more information when running this
        program.  Defaults to False.
    """

    username = "landscape"
    max_retries = 3
    factor = 1.1
    options = None

    BIN_DIR = None

    def __init__(self, connector, reactor=reactor, verbose=False,
                 config=None):
        self._connector = connector
        self._reactor = reactor
        self._env = os.environ.copy()
        my_uid = os.getuid()
        if my_uid == 0:
            pwd_info = pwd.getpwnam(self.username)
            target_uid = pwd_info.pw_uid
            target_gid = pwd_info.pw_gid
            if target_uid != my_uid:
                self._uid = target_uid
            else:
                self._uid = None
            if target_gid != os.getgid():
                self._gid = target_gid
            else:
                self._gid = None
            self._env["HOME"] = pwd_info.pw_dir
            self._env["USER"] = self.username
            self._env["LOGNAME"] = self.username
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
        self._allow_restart = True

    def find_executable(self):
        """Find the fully-qualified path to the executable.

        If the executable can't be found, L{ExecutableNotFoundError} will be
        raised.
        """
        dirname = self.BIN_DIR or get_bindir()
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
        if self.options is not None:
            args.extend(self.options)
        env = encode_values(self._env)
        self._reactor.spawnProcess(self._process, exe, args=args,
                                   env=env, uid=self._uid, gid=self._gid)

    def stop(self):
        """Stop this daemon."""
        if not self._process:
            return succeed(None)
        return self._process.kill()

    def _connect_and_call(self, name, *args, **kwargs):
        """Connect to the remote daemon over AMP and perform the given command.

        @param name: The name of the command to perform.
        @param args: Arguments list to be passed to the connect method
        @param kwargs: Keywords arguments to pass to the connect method.
        @return: A L{Deferred} resulting in C{True} if the command was
            successful or C{False} otherwise.
        @see: L{RemoteLandscapeComponentCreator.connect}.
        """

        def disconnect(ignored):
            self._connector.disconnect()
            return True

        connected = self._connector.connect(self.max_retries, self.factor,
                                            quiet=True)
        connected.addCallback(lambda remote: getattr(remote, name)())
        connected.addCallback(disconnect)
        connected.addErrback(lambda x: False)
        return connected

    def request_exit(self):
        return self._connect_and_call("exit")

    def is_running(self):
        # FIXME Error cases may not be handled in the best possible way
        # here. We're basically return False if any error happens from the
        # AMP ping.
        return self._connect_and_call("ping")

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

    def prepare_for_shutdown(self):
        """Called by the watchdog when starting to shut us down.

        It will prevent our L{WatchedProcessProtocol} to restart the process
        when it exits.
        """
        self._allow_restart = False

    def allow_restart(self):
        """Return a boolean indicating if the daemon should be restarted."""
        return self._allow_restart

    def rotate_logs(self):
        self._process.rotate_logs()


class Broker(Daemon):
    program = "landscape-broker"


class Monitor(Daemon):
    program = "landscape-monitor"


class Manager(Daemon):
    program = "landscape-manager"
    username = "root"


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
        if self.transport.pid is None:
            return succeed(None)
        self._wait_result = Deferred()
        return self._wait_result

    def wait_or_die(self):
        self._delayed_terminate = reactor.callLater(GRACEFUL_WAIT_PERIOD,
                                                    self._terminate, warn=True)
        return self.wait()

    def outReceived(self, data):
        # it's *probably* going to always be line buffered, by accident
        sys.stdout.buffer.write(data)

    def errReceived(self, data):
        sys.stderr.buffer.write(data)

    def processEnded(self, reason):
        """The process has ended; restart it."""
        if self._delayed_really_kill is not None:
            self._delayed_really_kill.cancel()
        if (self._delayed_terminate is not None and
                self._delayed_terminate.active()):
            self._delayed_terminate.cancel()
        if self._wait_result is not None:
            self._wait_result.callback(None)
        elif self.daemon.allow_restart():
            self.daemon.start()


class WatchDog(object):
    """
    The Landscape WatchDog starts all other landscape daemons and ensures that
    they are working.
    """

    def __init__(self, reactor=reactor, verbose=False, config=None,
                 broker=None, monitor=None, manager=None,
                 enabled_daemons=None):
        landscape_reactor = LandscapeReactor()
        if enabled_daemons is None:
            enabled_daemons = [Broker, Monitor, Manager]
        if broker is None and Broker in enabled_daemons:
            broker = Broker(
                RemoteBrokerConnector(landscape_reactor, config),
                verbose=verbose, config=config.config)
        if monitor is None and Monitor in enabled_daemons:
            monitor = Monitor(
                RemoteMonitorConnector(landscape_reactor, config),
                verbose=verbose, config=config.config)
        if manager is None and Manager in enabled_daemons:
            manager = Manager(
                RemoteManagerConnector(landscape_reactor, config),
                verbose=verbose, config=config.config)

        self.broker = broker
        self.monitor = monitor
        self.manager = manager
        self.daemons = [daemon
                        for daemon in [self.broker, self.monitor, self.manager]
                        if daemon]
        self.reactor = reactor
        self._checking = None
        self._stopping = False
        signal.signal(
            signal.SIGUSR1,
            lambda signal, frame: reactor.callFromThread(
                self._notify_rotate_logs))
        if config is not None and config.clones > 0:
            options = ["--clones", str(config.clones),
                       "--start-clones-over", str(config.start_clones_over)]
            for daemon in self.daemons:
                daemon.options = options

        self._ping_failures = {}

    def check_running(self):
        """Return a list of any daemons that are already running."""
        results = []
        for daemon in self.daemons:
            # This method is called on startup, we basically try to connect
            # a few times in fast sequence (with exponential backoff), if we
            # don't get a response we assume the daemon is not running.
            result = daemon.is_running()
            result.addCallback(lambda is_running, d=daemon: (is_running, d))
            results.append(result)

        def got_all_results(r):
            return [x[1] for x in r if x[0]]
        return gather_results(results).addCallback(got_all_results)

    def start(self):
        """
        Start all daemons. The broker will be started first, and no other
        daemons will be started before it is running and responding to AMP
        messages.

        @return: A deferred which fires when all services have successfully
            started. If a daemon could not be started, the deferred will fail
            with L{DaemonError}.
        """
        for daemon in self.daemons:
            daemon.start()
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

        # This tells the daemons to not automatically restart when they end
        for daemon in self.daemons:
            daemon.prepare_for_shutdown()

        def terminate_processes(broker_stopped):
            if broker_stopped:
                results = [daemon.wait_or_die() for daemon in self.daemons]
            else:
                # If request_exit fails, we should just kill the daemons
                # immediately.
                error("Couldn't request that broker gracefully shut down; "
                      "killing forcefully.")
                results = [x.stop() for x in self.daemons]
            return gather_results(results)

        result = self.broker.request_exit()
        return result.addCallback(terminate_processes)

    def _notify_rotate_logs(self):
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
        parser.add_option("--monitor-only", action="store_true",
                          help="Don't enable management features. This is "
                          "useful if you want to run the client as a non-root "
                          "user.")
        return parser

    def get_enabled_daemons(self):
        daemons = [Broker, Monitor]
        if not self.monitor_only:
            daemons.append(Manager)
        return daemons


def daemonize():
    # See http://www.steve.org.uk/Reference/Unix/faq_2.html#SEC16
    if os.fork():  # launch child and...
        os._exit(0)  # kill off parent
    os.setsid()
    if os.fork():  # launch child and...
        os._exit(0)  # kill off parent again.
    # some argue that this umask should be 0, but that's annoying.
    os.umask(0o077)
    null = os.open('/dev/null', os.O_RDWR)
    for i in range(3):
        try:
            os.dup2(null, i)
        except OSError as e:
            if e.errno != errno.EBADF:
                raise
    os.close(null)


class WatchDogService(Service):

    def __init__(self, config):
        self._config = config
        self.watchdog = WatchDog(verbose=not config.daemon,
                                 config=config,
                                 enabled_daemons=config.get_enabled_daemons())
        self.exit_code = 0

    def startService(self):
        Service.startService(self)
        bootstrap_list.bootstrap(data_path=self._config.data_path,
                                 log_dir=self._config.log_dir)
        if self._config.clones > 0:

            # Let clones open an appropriate number of fds
            setrlimit(RLIMIT_NOFILE, (self._config.clones * 100,
                                      self._config.clones * 200))

            # Increase the timeout of AMP's MethodCalls.
            # XXX: we should find a better way to expose this knot, and
            # not set it globally on the class
            from landscape.lib.amp import MethodCallSender
            MethodCallSender.timeout = 300

            # Create clones log and data directories
            for i in range(self._config.clones):
                suffix = "-clone-%d" % i
                bootstrap_list.bootstrap(
                    data_path=self._config.data_path + suffix,
                    log_dir=self._config.log_dir + suffix)

        result = succeed(None)
        result.addCallback(lambda _: self.watchdog.check_running())

        def start_if_not_running(running_daemons):
            if running_daemons:
                error("ERROR: The following daemons are already running: %s"
                      % (", ".join(x.program for x in running_daemons)))
                self.exit_code = 1
                reactor.crash()  # so stopService isn't called.
                return
            self._daemonize()
            info("Watchdog watching for daemons.")
            return self.watchdog.start()

        def die(failure):
            log_failure(failure, "Unknown error occurred!")
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

        done = self.watchdog.request_exit()
        done.addBoth(lambda r: self._remove_pid())
        return done

    def _remove_pid(self):
        pid_file = self._config.pid_file
        if pid_file is not None and os.access(pid_file, os.W_OK):
            stream = open(pid_file)
            pid = stream.read()
            stream.close()
            if pid == str(os.getpid()):
                os.unlink(pid_file)


bootstrap_list = BootstrapList([
    BootstrapDirectory("$data_path", "landscape", "root", 0o755),
    BootstrapDirectory("$data_path/package", "landscape", "root", 0o755),
    BootstrapDirectory(
        "$data_path/package/hash-id", "landscape", "root", 0o755),
    BootstrapDirectory(
        "$data_path/package/binaries", "landscape", "root", 0o755),
    BootstrapDirectory(
        "$data_path/package/upgrade-tool", "landscape", "root", 0o755),
    BootstrapDirectory("$data_path/messages", "landscape", "root", 0o755),
    BootstrapDirectory("$data_path/sockets", "landscape", "root", 0o750),
    BootstrapDirectory(
        "$data_path/custom-graph-scripts", "landscape", "root", 0o755),
    BootstrapDirectory("$log_dir", "landscape", "root", 0o755),
    BootstrapFile("$data_path/package/database", "landscape", "root", 0o644)])


def clean_environment():
    """Unset dangerous environment variables.

    In particular unset all variables beginning with DEBIAN_ or DEBCONF_,
    to avoid any problems when landscape-client is invoked from its
    postinst script.  Some environment variables may be set which would affect
    *other* maintainer scripts which landscape-client invokes.
    """
    for key in list(os.environ.keys()):
        if (key.startswith(("DEBIAN_", "DEBCONF_")) or
                key in ["LANDSCAPE_ATTACHMENTS", "MAIL"]):
            del os.environ[key]


def run(args=sys.argv, reactor=None):
    """Start the watchdog.

    This is the topmost function that kicks off the Landscape client.  It
    cleans up the environment, loads the configuration, and starts the
    reactor.

    @param args: Command line arguments, including the program name as the
        first element.
    @param reactor: The reactor to use.  If none is specified, the global
        reactor is used.
    @raise SystemExit: if command line arguments are bad, or when landscape-
        client is not running as 'root' or 'landscape'.
    """
    clean_environment()

    config = WatchDogConfiguration()
    config.load(args)

    try:
        landscape_uid = pwd.getpwnam("landscape").pw_uid
    except KeyError:
        sys.exit("The 'landscape' user doesn't exist!")

    if os.getuid() not in (0, landscape_uid):
        sys.exit("landscape-client can only be run as 'root' or 'landscape'.")

    init_logging(config, "watchdog")

    application = Application("landscape-client")
    watchdog_service = WatchDogService(config)
    watchdog_service.setServiceParent(application)

    if reactor is None:
        from twisted.internet import reactor
    # We add a small delay to work around a Twisted bug: this method should
    # only be called when the reactor is running, but we still get a
    # PotentialZombieWarning.
    reactor.callLater(0, startApplication, application, False)
    reactor.run()
    return watchdog_service.exit_code
