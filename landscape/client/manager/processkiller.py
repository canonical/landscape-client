import os
import signal
import logging
from datetime import datetime

from landscape.lib.process import ProcessInformation
from landscape.client.manager.plugin import ManagerPlugin


class ProcessNotFoundError(Exception):
    pass


class ProcessMismatchError(Exception):
    pass


class SignalProcessError(Exception):
    pass


class ProcessKiller(ManagerPlugin):
    """
    A management plugin that signals processes upon receiving a message from
    the server.
    """

    def __init__(self, process_info=None):
        if process_info is None:
            process_info = ProcessInformation()
        self.process_info = process_info

    def register(self, registry):
        super(ProcessKiller, self).register(registry)
        registry.register_message("signal-process",
                                  self._handle_signal_process)

    def _handle_signal_process(self, message):
        self.call_with_operation_result(message, self.signal_process,
                                        message["pid"], message["name"],
                                        message["start-time"],
                                        message["signal"])

    def signal_process(self, pid, name, start_time, signame):
        logging.info("Sending %s signal to the process with PID %d.",
                     signame, pid)
        process_info = self.process_info.get_process_info(pid)
        if not process_info:
            start_time = datetime.utcfromtimestamp(start_time)
            message = ("The process %s with PID %d that started at %s UTC was "
                       "not found") % (name, pid, start_time)
            raise ProcessNotFoundError(message)
        elif abs(process_info["start-time"] - start_time) > 2:
            # We don't check that the start time matches precisely because
            # the way we obtain boot times isn't very precise, and this may
            # cascade into having imprecise process start times.
            expected_time = datetime.utcfromtimestamp(start_time)
            actual_time = datetime.utcfromtimestamp(process_info["start-time"])
            message = ("The process %s with PID %d that started at "
                       "%s UTC was not found.  A process with the same "
                       "PID that started at %s UTC was found and not "
                       "sent the %s signal") % (name, pid, expected_time,
                                                actual_time, signame)
            raise ProcessMismatchError(message)

        signum = getattr(signal, "SIG%s" % (signame,))
        try:
            os.kill(pid, signum)
        except Exception:
            # XXX Nothing is indicating what the problem was.
            message = ("Attempting to send the %s signal to the process "
                       "%s with PID %d failed") % (signame, name, pid)
            raise SignalProcessError(message)
