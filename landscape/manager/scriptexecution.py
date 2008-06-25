"""
Functionality for running arbitrary shell scripts.

@var ALL_USERS: A token indicating all users should be allowed.
"""
import os
import pwd
import tempfile
import operator
import traceback

from twisted.internet.utils import getProcessOutput
from twisted.internet.protocol import ProcessProtocol
from twisted.internet.defer import Deferred
from twisted.python.failure import Failure

from landscape.manager.manager import ManagerPlugin, SUCCEEDED, FAILED


ALL_USERS = object()


class ProcessTimeLimitReachedError(Exception):
    """
    Raised when a process has been running for too long.

    @ivar: The data that the process printed before reaching the time limit.
    """

    def __init__(self, data):
        self.data = data


class ScriptExecution(ManagerPlugin):
    """A plugin which allows execution of arbitrary shell scripts.

    @ivar size_limit: The number of bytes at which to truncate process output.
    """

    size_limit = 500000

    def __init__(self, process_factory=None):
        """
        @param process_factory: The L{IReactorProcess} provider to run the
            process with.
        """
        if process_factory is None:
            from twisted.internet import reactor as process_factory
        self.process_factory = process_factory
        self._scheduled_cancel = None

    def register(self, registry):
        super(ScriptExecution, self).register(registry)
        registry.register_message("execute-script", self._handle_execute_script)

    def _respond(self, status, data, opid, result_code=None):
        message =  {"type": "operation-result",
                    "status": status,
                    "result-text": data,
                    "operation-id": opid}
        if result_code:
            message["result-code"] = result_code
        return self.registry.broker.send_message(message, True)

    def _handle_execute_script(self, message):
        opid = message["operation-id"]
        try:
            user = message["username"]
            allowed_users = self.registry.config.get_allowed_script_users()
            if allowed_users != ALL_USERS and user not in allowed_users:
                return self._respond(
                    FAILED,
                    u"Scripts cannot be run as user %s." % (user,),
                    opid)

            d = self.run_script(message["interpreter"], message["code"],
                                time_limit=message["time-limit"],
                                user=user)
            d.addCallback(self._respond_success, opid)
            d.addErrback(self._respond_timeout, opid)
            return d
        except Exception, e:
            self._respond(FAILED, self._format_exception(e), opid)
            raise

    def _format_exception(self, e):
        return u"%s: %s" % (type(e).__name__, e)

    def _respond_success(self, data, opid):
        return self._respond(SUCCEEDED, data, opid)

    def _respond_timeout(self, failure, opid):
        failure.trap(ProcessTimeLimitReachedError)
        return self._respond(FAILED, failure.value.data, opid, 101)

    def run_script(self, shell, code, user=None, time_limit=None):
        """
        Run a script based on a shell and the code.

        A file will be written with #!<shell> as the first line, as executable,
        and run as the given user.

        XXX: Handle the 'reboot' and 'killall landscape-client' commands
        gracefully.

        @param shell: The interpreter to use.
        @param code: The code to run.
        @param user: The username to run the process as.
        @param time_limit: The number of seconds to allow the process to run
            before killing it and failing the returned Deferred with a
            L{ProcessTimeLimitReachedError}.

        @return: A deferred that will fire with the data printed by the process
            or fail with a L{ProcessTimeLimitReachedError}.
        """
        uid = None
        gid = None
        path = None
        if user is not None:
            info = pwd.getpwnam(user)
            uid = info.pw_uid
            gid = info.pw_gid
            path = info.pw_dir
            if not os.path.exists(path):
                path = "/"

        fd, filename = tempfile.mkstemp()
        script_file = os.fdopen(fd, "w")
        # Chown and chmod it before we write the data in it - the script may
        # have sensitive content
        # It would be nice to use fchown(2) and fchmod(2), but they're not
        # available in python and using it with ctypes is pretty tedious, not
        # to mention we can't get errno.
        os.chmod(filename, 0700)
        if uid is not None:
            os.chown(filename, uid, 0)
        script_file.write("#!%s\n%s" % (shell, code))
        script_file.close()
        pp = ProcessAccumulationProtocol(self.size_limit)
        self.process_factory.spawnProcess(pp, filename, uid=uid, gid=gid,
                                          path=path)
        if time_limit is not None:
            self._scheduled_cancel = self.registry.reactor.call_later(
                time_limit, pp.cancel)
        result = pp.result_deferred
        result.addCallback(self._cancel_timeout)
        return result.addBoth(self._remove_script, filename)

    def _cancel_timeout(self, ignored):
        if self._scheduled_cancel is not None:
            self.registry.reactor.cancel_call(self._scheduled_cancel)
        return ignored

    def _remove_script(self, result, filename):
        os.unlink(filename)
        return result


class ProcessAccumulationProtocol(ProcessProtocol):
    """A ProcessProtocol which accumulates output.

    @ivar size_limit: The number of bytes at which to truncate output.
    """

    def __init__(self, size_limit):
        self.data = []
        self.result_deferred = Deferred()
        self._error = False
        self.size_limit = size_limit

    def childDataReceived(self, fd, data):
        """Some data was received from the child.

        Add it to our buffer, as long as it doesn't go over L{size_limit}
        bytes.
        """
        current_size = reduce(operator.add, map(len, self.data), 0)
        self.data.append(data[:self.size_limit - current_size])

    def processEnded(self, reason):
        """Fire back the deferred.

        The deferred will be fired with the string of data received from the
        subprocess, or if the subprocess was cancelled, a
        L{ProcessTimeLimitReachedError} will be fired with data accumulated so
        far.
        """
        data = ''.join(self.data)
        if self._error:
            self.result_deferred.errback(ProcessTimeLimitReachedError(data))
        else:
            self.result_deferred.callback(data)

    def cancel(self):
        """
        Close filedescriptors, kill the process, and indicate that a
        L{ProcessTimeLimitReachedError} should be fired on the deferred.
        """
        # Sometimes children of the shell we're killing won't die unless their
        # file descriptors are closed! For example, if /bin/sh -c "cat" is the
        # process, "cat" won't die when we kill its shell. I'm not sure if this
        # is really sufficient: maybe there's a way we can walk over all
        # children of the process we started and kill them all.
        for i in (0,1,2):
            self.transport.closeChildFD(i)
        self.transport.signalProcess("KILL")
        self._error = True
