"""
Functionality for running arbitrary shell scripts.

@var ALL_USERS: A token indicating all users should be allowed.
"""
import os
import sys
import os.path
import tempfile
import shutil

from twisted.internet.protocol import ProcessProtocol
from twisted.internet.defer import (
    Deferred, fail, inlineCallbacks, returnValue, succeed)
from twisted.internet.error import ProcessDone
from twisted.python.compat import unicode

from landscape import VERSION
from landscape.constants import UBUNTU_PATH
from landscape.lib.fetch import fetch_async, HTTPCodeError
from landscape.lib.persist import Persist
from landscape.lib.scriptcontent import build_script
from landscape.lib.user import get_user_info
from landscape.client.manager.plugin import ManagerPlugin, SUCCEEDED, FAILED


ALL_USERS = object()
TIMEOUT_RESULT = 102
PROCESS_FAILED_RESULT = 103
FETCH_ATTACHMENTS_FAILED_RESULT = 104


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

    def __init__(self, data, exit_code):
        self.data = data
        self.exit_code = exit_code


class UnknownInterpreterError(Exception):
    """Raised when the interpreter specified to run a script is invalid.

    @ivar interpreter: the interpreter specified for the script.
    """

    def __init__(self, interpreter):
        self.interpreter = interpreter
        Exception.__init__(self, self._get_message())

    def _get_message(self):
        return "Unknown interpreter: '%s'" % self.interpreter


class ScriptRunnerMixin(object):
    """
    @param process_factory: The L{IReactorProcess} provider to run the
        process with.
    """

    truncation_indicator = "\n**OUTPUT TRUNCATED**"

    def __init__(self, process_factory=None):
        if process_factory is None:
            from twisted.internet import reactor as process_factory
        self.process_factory = process_factory

    def is_user_allowed(self, user):
        allowed_users = self.registry.config.get_allowed_script_users()
        return allowed_users == ALL_USERS or user in allowed_users

    def write_script_file(self, script_file, filename, shell, code, uid, gid):
        # Chown and chmod it before we write the data in it - the script may
        # have sensitive content
        # It would be nice to use fchown(2) and fchmod(2), but they're not
        # available in python and using it with ctypes is pretty tedious, not
        # to mention we can't get errno.
        os.chmod(filename, 0o700)
        if uid is not None:
            os.chown(filename, uid, gid)

        script = build_script(shell, code)
        script = script.encode("utf-8")
        script_file.write(script)
        script_file.close()

    def _run_script(self, filename, uid, gid, path, env, time_limit):

        if uid == os.getuid():
            uid = None
        if gid == os.getgid():
            gid = None
        env = {
            key: (
                value.encode(sys.getfilesystemencoding(), errors='replace')
                if isinstance(value, unicode) else value
            )
            for key, value in env.items()
        }

        pp = ProcessAccumulationProtocol(
            self.registry.reactor, self.registry.config.script_output_limit,
            self.truncation_indicator)
        args = (filename,)
        self.process_factory.spawnProcess(
            pp, filename, args=args, uid=uid, gid=gid, path=path, env=env)
        if time_limit is not None:
            pp.schedule_cancel(time_limit)
        return pp.result_deferred


class ScriptExecutionPlugin(ManagerPlugin, ScriptRunnerMixin):
    """A plugin which allows execution of arbitrary shell scripts.

    """

    def register(self, registry):
        super(ScriptExecutionPlugin, self).register(registry)
        registry.register_message(
            "execute-script", self._handle_execute_script)

    def _respond(self, status, data, opid, result_code=None):
        if not isinstance(data, unicode):
            # Let's decode result-text, replacing non-printable
            # characters
            data = data.decode("utf-8", "replace")
        message = {"type": "operation-result",
                   "status": status,
                   "result-text": data,
                   "operation-id": opid}
        if result_code:
            message["result-code"] = result_code
        return self.registry.broker.send_message(
            message, self._session_id, True)

    def _handle_execute_script(self, message):
        opid = message["operation-id"]
        try:
            user = message["username"]
            if not self.is_user_allowed(user):
                return self._respond(
                    FAILED,
                    u"Scripts cannot be run as user %s." % (user,),
                    opid)
            server_supplied_env = message.get("env", None)

            d = self.run_script(message["interpreter"], message["code"],
                                time_limit=message["time-limit"], user=user,
                                attachments=message["attachments"],
                                server_supplied_env=server_supplied_env)
            d.addCallback(self._respond_success, opid)
            d.addErrback(self._respond_failure, opid)
            return d
        except Exception as e:
            self._respond(FAILED, self._format_exception(e), opid)
            raise

    def _format_exception(self, e):
        return u"%s: %s" % (e.__class__.__name__, e.args[0])

    def _respond_success(self, data, opid):
        return self._respond(SUCCEEDED, data, opid)

    def _respond_failure(self, failure, opid):
        code = None
        if failure.check(ProcessTimeLimitReachedError):
            code = TIMEOUT_RESULT
        elif failure.check(ProcessFailedError):
            code = PROCESS_FAILED_RESULT
        elif failure.check(HTTPCodeError):
            code = FETCH_ATTACHMENTS_FAILED_RESULT
            return self._respond(
                FAILED, str(failure.value), opid,
                FETCH_ATTACHMENTS_FAILED_RESULT)

        if code is not None:
            return self._respond(FAILED, failure.value.data, opid, code)
        else:
            return self._respond(FAILED, str(failure), opid)

    @inlineCallbacks
    def _save_attachments(self, attachments, uid, gid, computer_id, env):
        root_path = self.registry.config.url.rsplit("/", 1)[0] + "/attachment/"
        env["LANDSCAPE_ATTACHMENTS"] = attachment_dir = tempfile.mkdtemp()
        headers = {"User-Agent": "landscape-client/%s" % VERSION,
                   "Content-Type": "application/octet-stream",
                   "X-Computer-ID": computer_id}
        for filename, attachment_id in attachments.items():
            if isinstance(attachment_id, str):
                # Backward compatible behavior
                data = attachment_id.encode("utf-8")
                yield succeed(None)
            else:
                data = yield fetch_async(
                    "%s%d" % (root_path, attachment_id),
                    cainfo=self.registry.config.ssl_public_key,
                    headers=headers)
            full_filename = os.path.join(attachment_dir, filename)
            with open(full_filename, "wb") as attachment:
                os.chmod(full_filename, 0o600)
                if uid is not None:
                    os.chown(full_filename, uid, gid)
                attachment.write(data)
        os.chmod(attachment_dir, 0o700)
        if uid is not None:
            os.chown(attachment_dir, uid, gid)
        returnValue(attachment_dir)

    def run_script(self, shell, code, user=None, time_limit=None,
                   attachments=None, server_supplied_env=None):
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
                UnknownInterpreterError(shell))

        uid, gid, path = get_user_info(user)

        fd, filename = tempfile.mkstemp()
        script_file = os.fdopen(fd, "wb")
        self.write_script_file(
            script_file, filename, shell, code, uid, gid)

        env = {
            "PATH": UBUNTU_PATH,
            "USER": user or "",
            "HOME": path or "",
        }
        for locale_var in ("LANG", "LC_ALL", "LC_CTYPE"):
            if locale_var in os.environ:
                env[locale_var] = os.environ[locale_var]
        if server_supplied_env:
            env.update(server_supplied_env)
        old_umask = os.umask(0o022)

        if attachments:
            persist = Persist(
                filename=os.path.join(self.registry.config.data_path,
                                      "broker.bpickle"))
            persist = persist.root_at("registration")
            computer_id = persist.get("secure-id")
            try:
                computer_id = computer_id.decode("ascii")
            except AttributeError:
                pass
            d = self._save_attachments(attachments, uid, gid, computer_id, env)
        else:
            d = succeed(None)

        def prepare_script(attachment_dir):

            return self._run_script(
                filename, uid, gid, path, env, time_limit)

        d.addCallback(prepare_script)
        return d.addBoth(self._cleanup, filename, env, old_umask)

    def _cleanup(self, result, filename, env, old_umask):
        try:
            os.unlink(filename)
        except Exception:
            pass
        if "LANDSCAPE_ATTACHMENTS" in env:
            try:
                shutil.rmtree(env["LANDSCAPE_ATTACHMENTS"])
            except Exception:
                pass
        os.umask(old_umask)
        return result


class ProcessAccumulationProtocol(ProcessProtocol):
    """A ProcessProtocol which accumulates output.

    @ivar size_limit: The number of bytes at which to truncate output.
    """

    def __init__(self, reactor, size_limit, truncation_indicator=""):
        self.data = []
        self._size = 0
        self.result_deferred = Deferred()
        self._cancelled = False
        self.size_limit = size_limit * 1024
        self._truncation_indicator = truncation_indicator.encode("utf-8")
        self._truncation_offset = len(self._truncation_indicator)
        self._truncated_size_limit = self.size_limit - self._truncation_offset
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
        if self._size < self.size_limit:
            data_length = len(data)
            if (self._size + data_length) >= self._truncated_size_limit:
                extent = (self._truncated_size_limit - self._size)
                self.data.append(data[:extent] + self._truncation_indicator)
                self._size = self.size_limit
            else:
                self.data.append(data)
                self._size += data_length

    def processEnded(self, reason):
        """Fire back the deferred.

        The deferred will be fired with the string of data received from the
        subprocess, or if the subprocess was cancelled, a
        L{ProcessTimeLimitReachedError} will be fired with data accumulated so
        far.
        """
        exit_code = reason.value.exitCode
        # We get bytes with self.data, but want unicode with replace
        # characters. This is again attempted in
        # ScriptExecutionPlugin._respond, but it is not called in all cases.
        data = b"".join(self.data).decode("utf-8", "replace")
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
                self.result_deferred.errback(
                    ProcessFailedError(data, exit_code))

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
        from landscape.client.manager.customgraph import CustomGraphPlugin
        self._script_execution = ScriptExecutionPlugin()
        self._custom_graph = CustomGraphPlugin()

    def register(self, registry):
        super(ScriptExecution, self).register(registry)
        self._script_execution.register(registry)
        self._custom_graph.register(registry)

    def exchange(self, urgent=False):
        self._custom_graph.exchange(urgent)
