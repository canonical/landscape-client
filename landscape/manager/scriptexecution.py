"""
Functionality for running arbitrary shell scripts.

@var ALL_USERS: A token indicating all users should be allowed.
"""
import os
import pwd
import tempfile
import operator
import shutil

from twisted.internet.protocol import ProcessProtocol
from twisted.internet.defer import Deferred, fail
from twisted.internet.error import ProcessDone

from landscape.lib.scriptcontent import build_script
from landscape.manager.manager import ManagerPlugin, SUCCEEDED, FAILED


ALL_USERS = object()

TIMEOUT_RESULT = 102
PROCESS_FAILED_RESULT = 103


class ProcessTimeLimitReachedError(Exception):
    """
    Raised when a process has been running for too long.

    @ivar data: The data that the process printed before reaching the time
        limit.
    """

    def __init__(self, data):
        self.data = data


class ProcessFailedError(Exception):
    """Raised when a process exits with a non-0 exit code.

    @ivar data: The data that the process printed before reaching the time
        limit.
    """

    def __init__(self, data):
        self.data = data


class ScriptRunnerMixin(object):

    def __init__(self, process_factory=None):
        """
        @param process_factory: The L{IReactorProcess} provider to run the
            process with.
        """
        if process_factory is None:
            from twisted.internet import reactor as process_factory
        self.process_factory = process_factory

    def is_user_allowed(self, user):
        allowed_users = self.registry.config.get_allowed_script_users()
        return allowed_users == ALL_USERS or user in allowed_users

    def get_pwd_infos(self, user):
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
        return uid, gid, path

    def write_script_file(self, script_file, filename, shell, code, uid, gid):
        # Chown and chmod it before we write the data in it - the script may
        # have sensitive content
        # It would be nice to use fchown(2) and fchmod(2), but they're not
        # available in python and using it with ctypes is pretty tedious, not
        # to mention we can't get errno.
        os.chmod(filename, 0700)
        if uid is not None:
            os.chown(filename, uid, gid)
        script_file.write(build_script(shell, code))
        script_file.close()

    def _run_script(self, filename, uid, gid, path, env, time_limit):
        pp = ProcessAccumulationProtocol(
            self.registry.reactor, self.size_limit)
        self.process_factory.spawnProcess(
            pp, filename, uid=uid, gid=gid, path=path, env=env)
        if time_limit is not None:
            pp.schedule_cancel(time_limit)
        return pp.result_deferred


class ScriptExecutionPlugin(ManagerPlugin, ScriptRunnerMixin):
    """A plugin which allows execution of arbitrary shell scripts.

    @ivar size_limit: The number of bytes at which to truncate process output.
    """

    size_limit = 500000

    def register(self, registry):
        super(ScriptExecutionPlugin, self).register(registry)
        registry.register_message(
            "execute-script", self._handle_execute_script)

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
            if not self.is_user_allowed(user):
                return self._respond(
                    FAILED,
                    u"Scripts cannot be run as user %s." % (user,),
                    opid)

            d = self.run_script(message["interpreter"], message["code"],
                                time_limit=message["time-limit"],
                                user=user, attachments=message["attachments"])
            d.addCallback(self._respond_success, opid)
            d.addErrback(self._respond_failure, opid)
            return d
        except Exception, e:
            self._respond(FAILED, self._format_exception(e), opid)
            raise

    def _format_exception(self, e):
        return u"%s: %s" % (e.__class__.__name__, e)

    def _respond_success(self, data, opid):
        return self._respond(SUCCEEDED, data, opid)

    def _respond_failure(self, failure, opid):
        code = None
        if failure.check(ProcessTimeLimitReachedError):
            code = TIMEOUT_RESULT
        elif failure.check(ProcessFailedError):
            code = PROCESS_FAILED_RESULT
        if code is not None:
            return self._respond(FAILED, failure.value.data, opid, code)
        else:
            return self._respond(FAILED, str(failure), opid)

    def run_script(self, shell, code, user=None, time_limit=None,
                   attachments=None):
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
        @param attachments: C{dict} of filename/data attached to the script.

        @return: A deferred that will fire with the data printed by the process
            or fail with a L{ProcessTimeLimitReachedError}.
        """
        if not os.path.exists(shell.split()[0]):
            return fail(
                ProcessFailedError("Unknown interpreter: '%s'" % shell))

        uid, gid, path = self.get_pwd_infos(user)

        fd, filename = tempfile.mkstemp()
        script_file = os.fdopen(fd, "w")
        self.write_script_file(script_file, filename, shell, code, uid, gid)

        env = {}
        attachment_dir = ""
        old_umask = os.umask(0022)
        try:
            if attachments:
                attachment_dir = tempfile.mkdtemp()
                env["LANDSCAPE_ATTACHMENTS"] = attachment_dir
                for attachment_filename, data in attachments.iteritems():
                    full_filename = os.path.join(
                        attachment_dir, attachment_filename)
                    attachment = file(full_filename, "wb")
                    os.chmod(full_filename, 0600)
                    if uid is not None:
                        os.chown(full_filename, uid, gid)
                    attachment.write(data)
                    attachment.close()
                os.chmod(attachment_dir, 0700)
                if uid is not None:
                    os.chown(attachment_dir, uid, gid)
            
            result = self._run_script(filename, uid, gid, path, env, time_limit)
            return result.addBoth(
                self._remove_script, filename, attachment_dir, old_umask)
        except:
            os.umask(old_umask)
            raise

    def _remove_script(self, result, filename, attachment_dir, old_umask):
        try:
            os.unlink(filename)
        except:
            pass
        if attachment_dir:
            try:
                shutil.rmtree(attachment_dir)
            except:
                pass
        os.umask(old_umask)
        return result


class ProcessAccumulationProtocol(ProcessProtocol):
    """A ProcessProtocol which accumulates output.

    @ivar size_limit: The number of bytes at which to truncate output.
    """

    def __init__(self, reactor, size_limit):
        self.data = []
        self.result_deferred = Deferred()
        self._cancelled = False
        self.size_limit = size_limit
        self.reactor = reactor
        self._scheduled_cancel = None

    def schedule_cancel(self, time_limit):
        self._scheduled_cancel = self.reactor.call_later(
            time_limit, self._cancel)

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
        data = "".join(self.data)
        if self._cancelled:
            self.result_deferred.errback(ProcessTimeLimitReachedError(data))
        else:
            if self._scheduled_cancel is not None:
                scheduled = self._scheduled_cancel
                self._scheduled_cancel = None
                self.reactor.cancel_call(scheduled)

            if reason.check(ProcessDone):
                self.result_deferred.callback(data)
            else:
                self.result_deferred.errback(ProcessFailedError(data))

    def _cancel(self):
        """
        Close filedescriptors, kill the process, and indicate that a
        L{ProcessTimeLimitReachedError} should be fired on the deferred.
        """
        # Sometimes children of the shell we're killing won't die unless their
        # file descriptors are closed! For example, if /bin/sh -c "cat" is the
        # process, "cat" won't die when we kill its shell. I'm not sure if this
        # is really sufficient: maybe there's a way we can walk over all
        # children of the process we started and kill them all.
        for i in (0, 1, 2):
            self.transport.closeChildFD(i)
        self.transport.signalProcess("KILL")
        self._cancelled = True


class ScriptExecution(ManagerPlugin):
    """
    Meta-plugin wrapping ScriptExecutionPlugin and CustomGraphPlugin.
    """

    def __init__(self):
        from landscape.manager.customgraph import CustomGraphPlugin
        self._script_execution = ScriptExecutionPlugin()
        self._custom_graph = CustomGraphPlugin()

    def register(self, registry):
        super(ScriptExecution, self).register(registry)
        self._script_execution.register(registry)
        self._custom_graph.register(registry)

    def exchange(self, urgent=False):
        self._custom_graph.exchange(urgent)
