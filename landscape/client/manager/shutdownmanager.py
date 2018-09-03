import logging

from twisted.internet.defer import Deferred
from twisted.internet.protocol import ProcessProtocol
from twisted.internet.error import ProcessDone

from landscape.client.manager.plugin import ManagerPlugin, SUCCEEDED, FAILED


class ShutdownFailedError(Exception):
    """Raised when a call to C{/sbin/shutdown} fails.

    @ivar data: The data that the process printed before failing.
    """

    def __init__(self, data):
        self.data = data


class ShutdownManager(ManagerPlugin):

    def __init__(self, process_factory=None):
        if process_factory is None:
            from twisted.internet import reactor as process_factory
        self._process_factory = process_factory

    def register(self, registry):
        """Add this plugin to C{registry}.

        The shutdown manager handles C{shutdown} activity messages broadcast
        from the server.
        """
        super(ShutdownManager, self).register(registry)
        registry.register_message("shutdown", self.perform_shutdown)

    def perform_shutdown(self, message):
        """Request a system restart or shutdown.

        If the call to C{/sbin/shutdown} runs without errors the activity
        specified in the message will be responded as succeeded.  Otherwise,
        it will be responded as failed.
        """
        operation_id = message["operation-id"]
        reboot = message["reboot"]
        protocol = ShutdownProcessProtocol()
        protocol.set_timeout(self.registry.reactor)
        protocol.result.addCallback(self._respond_success, operation_id)
        protocol.result.addErrback(self._respond_failure, operation_id, reboot)
        command, args = self._get_command_and_args(protocol, reboot)
        self._process_factory.spawnProcess(protocol, command, args=args)

    def _respond_success(self, data, operation_id):
        logging.info("Shutdown request succeeded.")
        deferred = self._respond(SUCCEEDED, data, operation_id)
        # After sending the result to the server, stop accepting messages and
        # wait for the reboot/shutdown.
        deferred.addCallback(
            lambda _: self.registry.broker.stop_exchanger())
        return deferred

    def _respond_failure(self, failure, operation_id, reboot):
        logging.info("Shutdown request failed.")
        failure_report = '\n'.join([
            failure.value.data,
            "",
            "Attempting to force {operation}. Please note that if this "
            "succeeds, Landscape will have no way of knowing and will still "
            "mark this activity as having failed. It is recommended you check "
            "the state of the machine manually to determine whether "
            "{operation} succeeded.".format(
                operation="reboot" if reboot else "shutdown")
        ])
        deferred = self._respond(FAILED, failure_report, operation_id)
        # Add another callback spawning the poweroff or reboot command (which
        # seem more reliable in aberrant situations like a post-trusty release
        # upgrade where upstart has been replaced with systemd). If this
        # succeeds, we won't have any opportunity to report it and if it fails
        # we'll already have responded indicating we're attempting to force
        # the operation so either way there's no sense capturing output
        protocol = ProcessProtocol()
        command, args = self._get_command_and_args(protocol, reboot, True)
        deferred.addCallback(
            lambda _: self._process_factory.spawnProcess(
                protocol, command, args=args))
        return deferred

    def _respond(self, status, data, operation_id):
        message = {"type": "operation-result",
                   "status": status,
                   "result-text": data,
                   "operation-id": operation_id}
        return self.registry.broker.send_message(
            message, self._session_id, True)

    def _get_command_and_args(self, protocol, reboot, force=False):
        """
        Returns a C{command, args} 2-tuple suitable for use with
        L{IReactorProcess.spawnProcess}.
        """
        minutes = None if force else "+%d" % (protocol.delay // 60,)
        args = {
            (False, False): [
                "/sbin/shutdown", "-h", minutes,
                "Landscape is shutting down the system"],
            (False, True): [
                "/sbin/shutdown", "-r", minutes,
                "Landscape is rebooting the system"],
            (True, False): ["/sbin/poweroff"],
            (True, True): ["/sbin/reboot"],
        }[force, reboot]
        return args[0], args


class ShutdownProcessProtocol(ProcessProtocol):
    """A ProcessProtocol for calling C{/sbin/shutdown}.

    C{shutdown} doesn't return immediately when a time specification is
    provided.  Failures are reported immediately after it starts and return a
    non-zero exit code.  The process protocol calls C{shutdown} and waits for
    failures for C{timeout} seconds.  If no failures are reported it fires
    C{result}'s callback with whatever output was received from the process.
    If failures are reported C{result}'s errback is fired.

    @ivar result: A L{Deferred} fired when C{shutdown} fails or
        succeeds.
    @ivar reboot: A flag indicating whether a shutdown or reboot should be
        performed.  Default is C{False}.
    @ivar delay: The time in seconds from now to schedule the shutdown.
        Default is 240 seconds.  The time will be converted to minutes using
        integer division when passed to C{shutdown}.
    """

    def __init__(self, reboot=False, delay=240):
        self.result = Deferred()
        self.reboot = reboot
        self.delay = delay
        self._data = []
        self._waiting = True

    def get_data(self):
        """Get the data printed by the subprocess."""
        return b"".join(self._data).decode("utf-8", "replace")

    def set_timeout(self, reactor, timeout=10):
        """
        Set the error checking timeout, after which C{result}'s callback will
        be fired.
        """
        reactor.call_later(timeout, self._succeed)

    def childDataReceived(self, fd, data):
        """Some data was received from the child.

        Add it to our buffer to pass to C{result} when it's fired.
        """
        if self._waiting:
            self._data.append(data)

    def processEnded(self, reason):
        """Fire back the C{result} L{Deferred}.

        C{result}'s callback will be fired with the string of data received
        from the subprocess, or if the subprocess failed C{result}'s errback
        will be fired with the string of data received from the subprocess.
        """
        if self._waiting:
            if reason.check(ProcessDone):
                self._succeed()
            else:
                self.result.errback(ShutdownFailedError(self.get_data()))
                self._waiting = False

    def _succeed(self):
        """Fire C{result}'s callback with data accumulated from the process."""
        if self._waiting:
            self.result.callback(self.get_data())
            self._waiting = False
