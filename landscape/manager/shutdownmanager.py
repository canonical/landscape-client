import logging

from twisted.internet.defer import Deferred
from twisted.internet.protocol import ProcessProtocol
from twisted.internet.error import ProcessDone

from landscape.manager.manager import ManagerPlugin, SUCCEEDED, FAILED


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
        super(ShutdownManager, self).register(registry)
        registry.register_message("shutdown", self.perform_shutdown)

    def perform_shutdown(self, message):
        operation_id = message["operation-id"]
        protocol = ShutdownProcessProtocol(reboot=message["reboot"])
        protocol.set_timeout(self.registry.reactor)
        protocol.result.addCallbacks(
            self._respond_success, errback=self._respond_failure,
            callbackArgs=[operation_id], errbackArgs=[operation_id])
        command, arguments = protocol.get_command_and_arguments()
        self._process_factory.spawnProcess(protocol, command, args=arguments)

    def _respond_success(self, data, operation_id):
        logging.info("Shutdown request succeeded.")
        return self._respond(SUCCEEDED, data, operation_id)

    def _respond_failure(self, failure, operation_id):
        logging.info("Shutdown request failed.")
        return self._respond(FAILED, failure.value.data, operation_id)

    def _respond(self, status, data, operation_id):
        message = {"type": "operation-result",
                   "status": status,
                   "result-text": data,
                   "operation-id": operation_id}
        return self.registry.broker.send_message(message, True)


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
        Default is 600 seconds.  The time will be converted to minutes using
        integer division when passed to C{shutdown}.
    """

    def __init__(self, reboot=False, delay=600):
        self.result = Deferred()
        self.reboot = reboot
        self.delay = delay
        self._data = []
        self._running = True

    def get_command_and_arguments(self):
        """
        Returns a C{command, arguments} 2-tuple suitable for use with
        L{IReactorProcess.spawnProcess}.
        """
        minutes = "+%d" % (self.delay // 60,)
        if self.reboot:
            arguments = ["-r", minutes, "Landscape is rebooting the system"]
        else:
            arguments = ["-h", minutes, "Landscape is shutting down the system"]
        return "/sbin/shutdown", arguments

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
        if self._running:
            self._data.append(data)

    def processEnded(self, reason):
        """Fire back the C{result} L{Deferred}.

        C{result}'s callback will be fired with the string of data received
        from the subprocess, or if the subprocess failed C{result}'s errback
        will be fired with the string of data received from the subprocess.
        """
        if self._running:
            if reason.check(ProcessDone):
                self._succeed()
            else:
                self._fail()

    def _succeed(self):
        """Fire C{result}'s callback with data accumulated from the process."""
        if self._running:
            data = "".join(self._data)
            self.result.callback(data)
            self._running = False

    def _fail(self):
        """Fire C{result}'s errback with data accumulated from the process."""
        if self._running:
            data = "".join(self._data)
            self.result.errback(ShutdownFailedError(data))
            self._running = False
