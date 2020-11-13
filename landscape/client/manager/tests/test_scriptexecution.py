import pwd
import os
import sys
import tempfile
import stat

import mock

from twisted.internet.defer import gatherResults, succeed, fail
from twisted.internet.error import ProcessDone
from twisted.python.failure import Failure

from landscape import VERSION
from landscape.lib.fetch import HTTPCodeError
from landscape.lib.persist import Persist
from landscape.lib.testing import StubProcessFactory, DummyProcess
from landscape.lib.user import get_user_info, UnknownUserError
from landscape.client.manager.scriptexecution import (
    ScriptExecutionPlugin, ProcessTimeLimitReachedError, PROCESS_FAILED_RESULT,
    UBUNTU_PATH, UnknownInterpreterError, FETCH_ATTACHMENTS_FAILED_RESULT)
from landscape.client.manager.manager import SUCCEEDED, FAILED
from landscape.client.tests.helpers import LandscapeTest, ManagerHelper


def get_default_environment():
    username = pwd.getpwuid(os.getuid())[0]
    uid, gid, home = get_user_info(username)
    env = {
        "PATH": UBUNTU_PATH,
        "USER": username,
        "HOME": home,
    }
    for var in {"LANG", "LC_ALL", "LC_CTYPE"}:
        if var in os.environ:
            env[var] = os.environ[var]
    return env


def encoded_default_environment():
    return {
        key: value.encode('ascii', 'replace')
        for key, value in get_default_environment().items()
    }


class RunScriptTests(LandscapeTest):

    helpers = [ManagerHelper]

    def setUp(self):
        super(RunScriptTests, self).setUp()
        self.plugin = ScriptExecutionPlugin()
        self.manager.add(self.plugin)

    def test_basic_run(self):
        """
        The plugin returns a Deferred resulting in the output of basic
        commands.
        """
        result = self.plugin.run_script("/bin/sh", "echo hi")
        result.addCallback(self.assertEqual, "hi\n")
        return result

    def test_snap_path(self):
        """The bin path for snaps is included in the PATH."""
        deferred = self.plugin.run_script("/bin/sh", "echo $PATH")
        deferred.addCallback(
            lambda result: self.assertIn("/snap/bin", result))
        return deferred

    def test_other_interpreter(self):
        """Non-shell interpreters can be specified."""
        result = self.plugin.run_script("/usr/bin/python3", "print('hi')")
        result.addCallback(self.assertEqual, "hi\n")
        return result

    def test_other_interpreter_env(self):
        """
        Non-shell interpreters don't have their paths set by the shell, so we
        need to check that other interpreters have environment variables set.
        """
        result = self.plugin.run_script(
            sys.executable,
            "import os\nprint(os.environ)")

        def check_environment(results):
            for string in get_default_environment():
                self.assertIn(string, results)

        result.addCallback(check_environment)
        return result

    def test_server_supplied_env(self):
        """
        Server-supplied environment variables are merged with default
        variables then passed to script.
        """
        server_supplied_env = {"DOG": "Woof", "CAT": "Meow"}
        result = self.plugin.run_script(
            sys.executable,
            "import os\nprint(os.environ)",
            server_supplied_env=server_supplied_env)

        def check_environment(results):
            for string in get_default_environment():
                self.assertIn(string, results)
            for name, value in server_supplied_env.items():
                self.assertIn(name, results)
                self.assertIn(value, results)

        result.addCallback(check_environment)
        return result

    def test_server_supplied_env_with_funky_chars(self):
        """
        Server-supplied environment variables can be unicode strings; client
        should pass these to the script's environment encoded appropriately
        (encoding from Python's sys.getfilesystemencoding).
        """
        patch_fs_encoding = mock.patch(
            'sys.getfilesystemencoding', return_value='UTF-8'
        )
        patch_fs_encoding.start()

        server_supplied_env = {
            "LEMMY": u"Mot\N{LATIN SMALL LETTER O WITH DIAERESIS}rhead",
            # Somehow it's just not as cool...
        }
        result = self.plugin.run_script(
            "/bin/sh", "echo $LEMMY",
            server_supplied_env=server_supplied_env)

        def check_environment(results):
            self.assertEqual(server_supplied_env["LEMMY"] + u'\n', results)

        def cleanup(result):
            patch_fs_encoding.stop()
            return result

        result.addCallback(check_environment).addBoth(cleanup)
        return result

    def test_server_supplied_env_overrides_client(self):
        """
        Server-supplied environment variables override client default
        values if the server provides them.
        """
        server_supplied_env = {"PATH": "server-path", "USER": "server-user",
                               "HOME": "server-home"}
        result = self.plugin.run_script(
            sys.executable,
            "import os\nprint(os.environ)",
            server_supplied_env=server_supplied_env)

        def check_environment(results):
            for name, value in server_supplied_env.items():
                self.assertIn(name, results)
                self.assertIn(value, results)

        result.addCallback(check_environment)
        return result

    def test_concurrent(self):
        """
        Scripts run with the ScriptExecutionPlugin plugin are run concurrently.
        """
        fifo = self.makeFile()
        os.mkfifo(fifo)
        self.addCleanup(os.remove, fifo)
        # If the first process is blocking on a fifo, and the second process
        # wants to write to the fifo, the only way this will complete is if
        # run_script is truly async
        d1 = self.plugin.run_script("/bin/sh", "cat " + fifo)
        d2 = self.plugin.run_script("/bin/sh", "echo hi > " + fifo)
        d1.addCallback(self.assertEqual, "hi\n")
        d2.addCallback(self.assertEqual, "")
        return gatherResults([d1, d2])

    def test_accented_run_in_code(self):
        """
        Scripts can contain accented data both in the code and in the
        result.
        """
        accented_content = u"\N{LATIN SMALL LETTER E WITH ACUTE}"
        result = self.plugin.run_script(
            u"/bin/sh", u"echo %s" % (accented_content,))
        # self.assertEqual gets the result as first argument and that's what we
        # compare against.
        result.addCallback(
            self.assertEqual, "%s\n" % (accented_content,))
        return result

    def test_accented_run_in_interpreter(self):
        """
        Scripts can also contain accents in the interpreter.
        """
        accented_content = u"\N{LATIN SMALL LETTER E WITH ACUTE}"
        result = self.plugin.run_script(
            u"/bin/echo %s" % (accented_content,), u"")

        def check(result):
            self.assertTrue(
                "%s " % (accented_content,) in result)

        result.addCallback(check)
        return result

    def test_set_umask_appropriately(self):
        """
        We should be setting the umask to 0o022 before executing a script, and
        restoring it to the previous value when finishing.
        """
        # Get original umask.
        old_umask = os.umask(0)
        os.umask(old_umask)

        patch_umask = mock.patch("os.umask")
        mock_umask = patch_umask.start()
        mock_umask.return_value = old_umask
        result = self.plugin.run_script("/bin/sh", "umask")

        def check(result):
            self.assertEqual("%04o\n" % old_umask, result)
            mock_umask.assert_has_calls(
                [mock.call(0o22), mock.call(old_umask)])

        result.addCallback(check)
        return result.addCallback(lambda _: patch_umask.stop())

    def test_restore_umask_in_event_of_error(self):
        """
        We set the umask before executing the script, in the event that there's
        an error setting up the script, we want to restore the umask.
        """
        patch_umask = mock.patch("os.umask", return_value=0o077)
        mock_umask = patch_umask.start()

        patch_mkdtemp = mock.patch(
            "tempfile.mkdtemp", side_effect=OSError("Fail!"))
        mock_mkdtemp = patch_mkdtemp.start()

        result = self.plugin.run_script(
            "/bin/sh", "umask", attachments={u"file1": "some data"})

        def check(error):
            self.assertIsInstance(error.value, OSError)
            self.assertEqual("Fail!", str(error.value))
            mock_umask.assert_has_calls([mock.call(0o022)])
            mock_mkdtemp.assert_called_with()

        def cleanup(result):
            patch_umask.stop()
            patch_mkdtemp.stop()
            return result

        return result.addErrback(check).addBoth(cleanup)

    def test_run_with_attachments(self):
        result = self.plugin.run_script(
            u"/bin/sh",
            u"ls $LANDSCAPE_ATTACHMENTS && cat $LANDSCAPE_ATTACHMENTS/file1",
            attachments={u"file1": "some data"})

        def check(result):
            self.assertEqual(result, "file1\nsome data")

        result.addCallback(check)
        return result

    def test_run_with_attachment_ids(self):
        """
        The most recent protocol for script message doesn't include the
        attachment body inside the message itself, but instead gives an
        attachment ID, and the plugin fetches the files separately.
        """
        self.manager.config.url = "https://localhost/message-system"
        persist = Persist(
            filename=os.path.join(self.config.data_path, "broker.bpickle"))
        registration_persist = persist.root_at("registration")
        registration_persist.set("secure-id", "secure_id")
        persist.save()

        patch_fetch = mock.patch(
            "landscape.client.manager.scriptexecution.fetch_async")
        mock_fetch = patch_fetch.start()
        mock_fetch.return_value = succeed(b"some other data")

        headers = {"User-Agent": "landscape-client/%s" % VERSION,
                   "Content-Type": "application/octet-stream",
                   "X-Computer-ID": "secure_id"}

        result = self.plugin.run_script(
            u"/bin/sh",
            u"ls $LANDSCAPE_ATTACHMENTS && cat $LANDSCAPE_ATTACHMENTS/file1",
            attachments={u"file1": 14})

        def check(result):
            self.assertEqual(result, "file1\nsome other data")
            mock_fetch.assert_called_with(
                "https://localhost/attachment/14", headers=headers,
                cainfo=None)

        def cleanup(result):
            patch_fetch.stop()
            # We have to return the Failure or result to get a working test.
            return result

        return result.addCallback(check).addBoth(cleanup)

    def test_run_with_attachment_ids_and_ssl(self):
        """
        When fetching attachments, L{ScriptExecution} passes the optional ssl
        certificate file if the configuration specifies it.
        """
        self.manager.config.url = "https://localhost/message-system"
        self.manager.config.ssl_public_key = "/some/key"
        persist = Persist(
            filename=os.path.join(self.config.data_path, "broker.bpickle"))
        registration_persist = persist.root_at("registration")
        registration_persist.set("secure-id", b"secure_id")
        persist.save()

        patch_fetch = mock.patch(
            "landscape.client.manager.scriptexecution.fetch_async")
        mock_fetch = patch_fetch.start()
        mock_fetch.return_value = succeed(b"some other data")

        headers = {"User-Agent": "landscape-client/%s" % VERSION,
                   "Content-Type": "application/octet-stream",
                   "X-Computer-ID": "secure_id"}

        result = self.plugin.run_script(
            u"/bin/sh",
            u"ls $LANDSCAPE_ATTACHMENTS && cat $LANDSCAPE_ATTACHMENTS/file1",
            attachments={u"file1": 14})

        def check(result):
            self.assertEqual(result, "file1\nsome other data")
            mock_fetch.assert_called_with(
                "https://localhost/attachment/14", headers=headers,
                cainfo="/some/key")

        def cleanup(result):
            patch_fetch.stop()
            return result

        return result.addCallback(check).addBoth(cleanup)

    def test_self_remove_script(self):
        """
        If a script removes itself, it doesn't create an error when the script
        execution plugin tries to remove the script file.
        """
        result = self.plugin.run_script("/bin/sh", "echo hi && rm $0")
        result.addCallback(self.assertEqual, "hi\n")
        return result

    def test_self_remove_attachments(self):
        """
        If a script removes its attachments, it doesn't create an error when
        the script execution plugin tries to remove the attachments directory.
        """
        result = self.plugin.run_script(
            u"/bin/sh",
            u"ls $LANDSCAPE_ATTACHMENTS && rm -r $LANDSCAPE_ATTACHMENTS",
            attachments={u"file1": "some data"})

        def check(result):
            self.assertEqual(result, "file1\n")

        result.addCallback(check)
        return result

    def _run_script(self, username, uid, gid, path):
        expected_uid = uid if uid != os.getuid() else None
        expected_gid = gid if gid != os.getgid() else None

        factory = StubProcessFactory()
        self.plugin.process_factory = factory

        # ignore the call to chown!
        patch_chown = mock.patch("os.chown")
        mock_chown = patch_chown.start()

        result = self.plugin.run_script("/bin/sh", "echo hi", user=username)

        self.assertEqual(len(factory.spawns), 1)
        spawn = factory.spawns[0]
        self.assertEqual(spawn[4], path)
        self.assertEqual(spawn[5], expected_uid)
        self.assertEqual(spawn[6], expected_gid)

        protocol = spawn[0]
        protocol.childDataReceived(1, b"foobar")
        for fd in (0, 1, 2):
            protocol.childConnectionLost(fd)
        protocol.processEnded(Failure(ProcessDone(0)))

        def check(result):
            mock_chown.assert_called_with()
            self.assertEqual(result, "foobar")

        def cleanup(result):
            patch_chown.stop()
            return result

        return result.addErrback(check).addBoth(cleanup)

    def test_user(self):
        """
        Running a script as a particular user calls
        C{IReactorProcess.spawnProcess} with an appropriate C{uid} argument,
        with the user's primary group as the C{gid} argument and with the user
        home as C{path} argument.
        """
        uid = os.getuid()
        info = pwd.getpwuid(uid)
        username = info.pw_name
        gid = info.pw_gid
        path = info.pw_dir

        return self._run_script(username, uid, gid, path)

    def test_user_no_home(self):
        """
        When the user specified to C{run_script} doesn't have a home, the
        script executes in '/'.
        """
        patch_getpwnam = mock.patch("pwd.getpwnam")
        mock_getpwnam = patch_getpwnam.start()

        class pwnam(object):
            pw_uid = 1234
            pw_gid = 5678
            pw_dir = self.makeFile()

        mock_getpwnam.return_value = pwnam

        result = self._run_script("user", 1234, 5678, "/")

        def check(result):
            mock_getpwnam.assert_called_with("user")

        def cleanup(result):
            patch_getpwnam.stop()
            return result

        return result.addCallback(check).addBoth(cleanup)

    def test_user_with_attachments(self):
        uid = os.getuid()
        info = pwd.getpwuid(uid)
        username = info.pw_name
        gid = info.pw_gid

        patch_chown = mock.patch("os.chown")
        mock_chown = patch_chown.start()

        factory = StubProcessFactory()
        self.plugin.process_factory = factory

        result = self.plugin.run_script("/bin/sh", "echo hi", user=username,
                                        attachments={u"file 1": "some data"})

        self.assertEqual(len(factory.spawns), 1)
        spawn = factory.spawns[0]
        self.assertIn("LANDSCAPE_ATTACHMENTS", spawn[3])
        attachment_dir = spawn[3]["LANDSCAPE_ATTACHMENTS"].decode('ascii')
        self.assertEqual(stat.S_IMODE(os.stat(attachment_dir).st_mode), 0o700)
        filename = os.path.join(attachment_dir, "file 1")
        self.assertEqual(stat.S_IMODE(os.stat(filename).st_mode), 0o600)

        protocol = spawn[0]
        protocol.childDataReceived(1, b"foobar")
        for fd in (0, 1, 2):
            protocol.childConnectionLost(fd)
        protocol.processEnded(Failure(ProcessDone(0)))

        def check(data):
            self.assertEqual(data, "foobar")
            self.assertFalse(os.path.exists(attachment_dir))
            mock_chown.assert_has_calls(
                [mock.call(mock.ANY, uid, gid) for x in range(3)])

        def cleanup(result):
            patch_chown.stop()
            return result

        return result.addCallback(check).addBoth(cleanup)

    def test_limit_size(self):
        """Data returned from the command is limited."""
        factory = StubProcessFactory()
        self.plugin.process_factory = factory
        self.manager.config.script_output_limit = 1
        result = self.plugin.run_script("/bin/sh", "")

        # Ultimately we assert that the resulting output is limited to
        # 1024 bytes and indicates its truncation.
        result.addCallback(self.assertEqual,
                           ("x" * (1024 - 21)) + "\n**OUTPUT TRUNCATED**")

        protocol = factory.spawns[0][0]

        # Push 2kB of output, so we trigger truncation.
        protocol.childDataReceived(1, b"x" * (2*1024))

        for fd in (0, 1, 2):
            protocol.childConnectionLost(fd)
        protocol.processEnded(Failure(ProcessDone(0)))

        return result

    def test_command_output_ends_with_truncation(self):
        """After truncation, no further output is recorded."""
        factory = StubProcessFactory()
        self.plugin.process_factory = factory
        self.manager.config.script_output_limit = 1
        result = self.plugin.run_script("/bin/sh", "")

        # Ultimately we assert that the resulting output is limited to
        # 1024 bytes and indicates its truncation.
        result.addCallback(self.assertEqual,
                           ("x" * (1024 - 21)) + "\n**OUTPUT TRUNCATED**")
        protocol = factory.spawns[0][0]

        # Push 1024 bytes of output, so we trigger truncation.
        protocol.childDataReceived(1, b"x" * 1024)
        # Push 1024 bytes more
        protocol.childDataReceived(1, b"x" * 1024)

        for fd in (0, 1, 2):
            protocol.childConnectionLost(fd)
        protocol.processEnded(Failure(ProcessDone(0)))

        return result

    def test_limit_time(self):
        """
        The process only lasts for a certain number of seconds.
        """
        result = self.plugin.run_script("/bin/sh", "cat", time_limit=500)
        self.manager.reactor.advance(501)
        self.assertFailure(result, ProcessTimeLimitReachedError)
        return result

    def test_limit_time_accumulates_data(self):
        """
        Data from processes that time out should still be accumulated and
        available from the exception object that is raised.
        """
        factory = StubProcessFactory()
        self.plugin.process_factory = factory
        result = self.plugin.run_script("/bin/sh", "", time_limit=500)
        protocol = factory.spawns[0][0]
        protocol.makeConnection(DummyProcess())
        protocol.childDataReceived(1, b"hi\n")
        self.manager.reactor.advance(501)
        protocol.processEnded(Failure(ProcessDone(0)))

        def got_error(f):
            self.assertTrue(f.check(ProcessTimeLimitReachedError))
            self.assertEqual(f.value.data, "hi\n")

        result.addErrback(got_error)
        return result

    def test_time_limit_canceled_after_success(self):
        """
        The timeout call is cancelled after the script terminates.
        """
        factory = StubProcessFactory()
        self.plugin.process_factory = factory
        self.plugin.run_script("/bin/sh", "", time_limit=500)
        protocol = factory.spawns[0][0]
        transport = DummyProcess()
        protocol.makeConnection(transport)
        protocol.childDataReceived(1, b"hi\n")
        protocol.processEnded(Failure(ProcessDone(0)))
        self.manager.reactor.advance(501)
        self.assertEqual(transport.signals, [])

    def test_cancel_doesnt_blow_after_success(self):
        """
        When the process ends successfully and is immediately followed by the
        timeout, the output should still be in the failure and nothing bad will
        happen!
        [regression test: killing of the already-dead process would blow up.]
        """
        factory = StubProcessFactory()
        self.plugin.process_factory = factory
        result = self.plugin.run_script("/bin/sh", "", time_limit=500)
        protocol = factory.spawns[0][0]
        protocol.makeConnection(DummyProcess())
        protocol.childDataReceived(1, b"hi")
        protocol.processEnded(Failure(ProcessDone(0)))
        self.manager.reactor.advance(501)

        def got_result(output):
            self.assertEqual(output, "hi")

        result.addCallback(got_result)
        return result

    @mock.patch("os.chown")
    @mock.patch("os.chmod")
    @mock.patch("tempfile.mkstemp")
    @mock.patch("os.fdopen")
    def test_script_is_owned_by_user(self, mock_fdopen, mock_mkstemp,
                                     mock_chmod, mock_chown):
        """
        This is a very white-box test. When a script is generated, it must be
        created such that data NEVER gets into it before the file has the
        correct permissions. Therefore os.chmod and os.chown must be called
        before data is written.
        """
        username = pwd.getpwuid(os.getuid())[0]
        uid, gid, home = get_user_info(username)

        called_mocks = []

        mock_chown.side_effect = lambda *_: called_mocks.append(mock_chown)
        mock_chmod.side_effect = lambda *_: called_mocks.append(mock_chmod)

        def mock_mkstemp_side_effect(*_):
            called_mocks.append(mock_mkstemp)
            return (99, "tempo!")

        mock_mkstemp.side_effect = mock_mkstemp_side_effect

        script_file = mock.Mock()

        def mock_fdopen_side_effect(*_):
            called_mocks.append(mock_fdopen)
            return script_file

        mock_fdopen.side_effect = mock_fdopen_side_effect

        def spawnProcess(protocol, filename, args, env, path, uid, gid):
            self.assertIsNone(uid)
            self.assertIsNone(gid)
            self.assertEqual(encoded_default_environment(), env)
            protocol.result_deferred.callback(None)

        process_factory = mock.Mock()
        process_factory.spawnProcess = spawnProcess
        self.plugin.process_factory = process_factory

        result = self.plugin.run_script("/bin/sh", "code",
                                        user=pwd.getpwuid(uid)[0])

        def check(_):
            mock_fdopen.assert_called_with(99, "wb")
            mock_chmod.assert_called_with("tempo!", 0o700)
            mock_chown.assert_called_with("tempo!", uid, gid)
            script_file.write.assert_called_with(b"#!/bin/sh\ncode")
            script_file.close.assert_called_with()
            self.assertEqual(
                [mock_mkstemp, mock_fdopen, mock_chmod, mock_chown],
                called_mocks)

        return result.addCallback(check)

    def test_script_removed(self):
        """
        The script is removed after it is finished.
        """
        fd, filename = tempfile.mkstemp()

        with mock.patch("tempfile.mkstemp") as mock_mkstemp:
            mock_mkstemp.return_value = (fd, filename)
            d = self.plugin.run_script("/bin/sh", "true")
            return d.addCallback(
                lambda _: self.assertFalse(os.path.exists(filename)))

    def test_unknown_interpreter(self):
        """
        If the script is run with an unknown interpreter, it raises a
        meaningful error instead of crashing in execvpe.
        """
        d = self.plugin.run_script("/bin/cantpossiblyexist", "stuff")

        def cb(ignore):
            self.fail("Should not be there")

        def eb(failure):
            failure.trap(UnknownInterpreterError)
            self.assertEqual(
                failure.value.interpreter,
                "/bin/cantpossiblyexist")
        return d.addCallback(cb).addErrback(eb)


class ScriptExecutionMessageTests(LandscapeTest):
    helpers = [ManagerHelper]

    def setUp(self):
        super(ScriptExecutionMessageTests, self).setUp()
        self.broker_service.message_store.set_accepted_types(
            ["operation-result"])
        self.manager.config.script_users = "ALL"

    def _verify_script(self, executable, interp, code):
        """
        Given spawnProcess arguments, check to make sure that the temporary
        script has the correct content.
        """
        data = open(executable, "r").read()
        self.assertEqual(data, "#!%s\n%s" % (interp, code))

    def _send_script(self, interpreter, code, operation_id=123,
                     user=pwd.getpwuid(os.getuid())[0],
                     time_limit=None, attachments={},
                     server_supplied_env=None):
        message = {"type": "execute-script",
                   "interpreter": interpreter,
                   "code": code,
                   "operation-id": operation_id,
                   "username": user,
                   "time-limit": time_limit,
                   "attachments": dict(attachments)}
        if server_supplied_env:
            message["env"] = server_supplied_env
        return self.manager.dispatch_message(message)

    def test_success(self):
        """
        When a C{execute-script} message is received from the server, the
        specified script will be run and an operation-result will be sent back
        to the server.
        """
        # Let's use a stub process factory, because otherwise we don't have
        # access to the deferred.
        factory = StubProcessFactory()

        self.manager.add(ScriptExecutionPlugin(process_factory=factory))

        result = self._send_script(sys.executable, "print 'hi'")

        self._verify_script(factory.spawns[0][1], sys.executable, "print 'hi'")
        self.assertMessages(
            self.broker_service.message_store.get_pending_messages(), [])

        # Now let's simulate the completion of the process
        factory.spawns[0][0].childDataReceived(1, b"hi!\n")
        factory.spawns[0][0].processEnded(Failure(ProcessDone(0)))

        def got_result(r):
            self.assertMessages(
                self.broker_service.message_store.get_pending_messages(),
                [{"type": "operation-result",
                  "operation-id": 123,
                  "status": SUCCEEDED,
                  "result-text": u"hi!\n"}])

        result.addCallback(got_result)
        return result

    def test_success_with_server_supplied_env(self):
        """
        When a C{execute-script} message is received from the server, the
        specified script will be run with the supplied environment and an
        operation-result will be sent back to the server.
        """
        # Let's use a stub process factory, because otherwise we don't have
        # access to the deferred.
        factory = StubProcessFactory()

        self.manager.add(ScriptExecutionPlugin(process_factory=factory))

        result = self._send_script(sys.executable, "print 'hi'",
                                   server_supplied_env={"Dog": "Woof"})

        self._verify_script(
            factory.spawns[0][1], sys.executable, "print 'hi'")
        # Verify environment was passed
        self.assertIn("HOME", factory.spawns[0][3])
        self.assertIn("USER", factory.spawns[0][3])
        self.assertIn("PATH", factory.spawns[0][3])
        self.assertIn("Dog", factory.spawns[0][3])
        self.assertEqual(b"Woof", factory.spawns[0][3]["Dog"])

        self.assertMessages(
            self.broker_service.message_store.get_pending_messages(), [])

        # Now let's simulate the completion of the process
        factory.spawns[0][0].childDataReceived(1, b"Woof\n")
        factory.spawns[0][0].processEnded(Failure(ProcessDone(0)))

        def got_result(r):
            self.assertMessages(
                self.broker_service.message_store.get_pending_messages(),
                [{"type": "operation-result",
                  "operation-id": 123,
                  "status": SUCCEEDED,
                  "result-text": u"Woof\n"}])

        result.addCallback(got_result)
        return result

    def test_user(self):
        """A user can be specified in the message."""
        username = pwd.getpwuid(os.getuid())[0]
        uid, gid, home = get_user_info(username)

        def spawnProcess(protocol, filename, args, env, path, uid, gid):
            protocol.childDataReceived(1, "hi!\n")
            protocol.processEnded(Failure(ProcessDone(0)))
            self._verify_script(filename, sys.executable, "print 'hi'")

        process_factory = mock.Mock()
        process_factory.spawnProcess = mock.Mock(side_effect=spawnProcess)
        self.manager.add(
            ScriptExecutionPlugin(process_factory=process_factory))

        result = self._send_script(sys.executable, "print 'hi'", user=username)

        def check(_):
            process_factory.spawnProcess.assert_called_with(
                mock.ANY, mock.ANY, args=mock.ANY, uid=None, gid=None,
                path=mock.ANY, env=encoded_default_environment())

        return result.addCallback(check)

    def test_unknown_user_with_unicode(self):
        """
        If an error happens because an unknow user is selected, and that this
        user name happens to contain unicode characters, the error message is
        correctly encoded and reported.

        This test mainly ensures that unicode error message works, using
        unknown user as an easy way to test it.
        """
        self.log_helper.ignore_errors(UnknownUserError)
        username = u"non-existent-f\N{LATIN SMALL LETTER E WITH ACUTE}e"
        self.manager.add(
            ScriptExecutionPlugin())

        self._send_script(sys.executable, "print 'hi'", user=username)
        self.assertMessages(
            self.broker_service.message_store.get_pending_messages(),
            [{"type": "operation-result",
              "operation-id": 123,
              "result-text": u"UnknownUserError: Unknown user '%s'" % username,
              "status": FAILED}])

    def test_timeout(self):
        """
        If a L{ProcessTimeLimitReachedError} is fired back, the
        operation-result should have a failed status.
        """
        factory = StubProcessFactory()
        self.manager.add(ScriptExecutionPlugin(process_factory=factory))

        result = self._send_script(sys.executable, "bar", time_limit=30)
        self._verify_script(factory.spawns[0][1], sys.executable, "bar")

        protocol = factory.spawns[0][0]
        protocol.makeConnection(DummyProcess())
        protocol.childDataReceived(2, b"ONOEZ")
        self.manager.reactor.advance(31)
        protocol.processEnded(Failure(ProcessDone(0)))

        def got_result(r):
            self.assertMessages(
                self.broker_service.message_store.get_pending_messages(),
                [{"type": "operation-result",
                  "operation-id": 123,
                  "status": FAILED,
                  "result-text": u"ONOEZ",
                  "result-code": 102}])

        result.addCallback(got_result)
        return result

    def test_configured_users(self):
        """
        Messages which try to run a script as a user that is not allowed should
        be rejected.
        """
        self.manager.add(ScriptExecutionPlugin())
        self.manager.config.script_users = "landscape, nobody"
        result = self._send_script(sys.executable, "bar", user="whatever")

        def got_result(r):
            self.assertMessages(
                self.broker_service.message_store.get_pending_messages(),
                [{"type": "operation-result",
                  "operation-id": 123,
                  "status": FAILED,
                  "result-text": u"Scripts cannot be run as user whatever."}])

        result.addCallback(got_result)
        return result

    def test_urgent_response(self):
        """Responses to script execution messages are urgent."""

        def spawnProcess(protocol, filename, args, env, path, uid, gid):
            protocol.childDataReceived(1, b"hi!\n")
            protocol.processEnded(Failure(ProcessDone(0)))
            self._verify_script(filename, sys.executable, "print 'hi'")

        process_factory = mock.Mock()
        process_factory.spawnProcess = mock.Mock(side_effect=spawnProcess)

        self.manager.add(
            ScriptExecutionPlugin(process_factory=process_factory))

        def got_result(r):
            self.assertTrue(self.broker_service.exchanger.is_urgent())
            self.assertMessages(
                self.broker_service.message_store.get_pending_messages(),
                [{"type": "operation-result",
                  "operation-id": 123,
                  "result-text": u"hi!\n",
                  "status": SUCCEEDED}])
            process_factory.spawnProcess.assert_called_with(
                mock.ANY, mock.ANY, args=mock.ANY, uid=None, gid=None,
                path=mock.ANY, env=encoded_default_environment())

        result = self._send_script(sys.executable, "print 'hi'")
        return result.addCallback(got_result)

    def test_binary_output(self):
        """
        If a script outputs non-printable characters not handled by utf-8, they
        are replaced during the encoding phase but the script succeeds.
        """
        def spawnProcess(protocol, filename, args, env, path, uid, gid):
            protocol.childDataReceived(
                1, b"\x7fELF\x01\x01\x01\x00\x00\x00\x95\x01")
            protocol.processEnded(Failure(ProcessDone(0)))
            self._verify_script(filename, sys.executable, "print 'hi'")

        process_factory = mock.Mock()
        process_factory.spawnProcess = mock.Mock(side_effect=spawnProcess)

        self.manager.add(
            ScriptExecutionPlugin(process_factory=process_factory))

        def got_result(r):
            self.assertTrue(self.broker_service.exchanger.is_urgent())
            [message] = (
                self.broker_service.message_store.get_pending_messages())
            self.assertEqual(
                message["result-text"],
                u"\x7fELF\x01\x01\x01\x00\x00\x00\ufffd\x01")
            process_factory.spawnProcess.assert_called_with(
                mock.ANY, mock.ANY, args=mock.ANY, uid=None, gid=None,
                path=mock.ANY, env=encoded_default_environment())

        result = self._send_script(sys.executable, "print 'hi'")
        return result.addCallback(got_result)

    def test_parse_error_causes_operation_failure(self):
        """
        If there is an error parsing the message, an operation-result will be
        sent (assuming operation-id *is* successfully parsed).
        """
        self.log_helper.ignore_errors(KeyError)
        self.manager.add(ScriptExecutionPlugin())

        self.manager.dispatch_message(
            {"type": "execute-script", "operation-id": 444})

        expected_message = [{"type": "operation-result",
                             "operation-id": 444,
                             "result-text": u"KeyError: username",
                             "status": FAILED}]

        self.assertMessages(
            self.broker_service.message_store.get_pending_messages(),
            expected_message)

        self.assertTrue("KeyError: 'username'" in self.logfile.getvalue())

    def test_non_zero_exit_fails_operation(self):
        """
        If a script exits with a nen-zero exit code, the operation associated
        with it should fail, but the data collected should still be sent.
        """
        self.manager.add(ScriptExecutionPlugin())
        result = self._send_script("/bin/sh", "echo hi; exit 1")

        def got_result(ignored):
            self.assertMessages(
                self.broker_service.message_store.get_pending_messages(),
                [{"type": "operation-result",
                  "operation-id": 123,
                  "result-text": "hi\n",
                  "result-code": PROCESS_FAILED_RESULT,
                  "status": FAILED}])

        return result.addCallback(got_result)

    def test_unknown_error(self):
        """
        When a completely unknown error comes back from the process protocol,
        the operation fails and the formatted failure is included in the
        response message.
        """
        factory = StubProcessFactory()

        self.manager.add(ScriptExecutionPlugin(process_factory=factory))

        result = self._send_script(sys.executable, "print 'hi'")

        self._verify_script(factory.spawns[0][1], sys.executable, "print 'hi'")
        self.assertMessages(
            self.broker_service.message_store.get_pending_messages(), [])

        failure = Failure(RuntimeError("Oh noes!"))
        factory.spawns[0][0].result_deferred.errback(failure)

        def got_result(r):
            self.assertMessages(
                self.broker_service.message_store.get_pending_messages(),
                [{"type": "operation-result",
                  "operation-id": 123,
                  "status": FAILED,
                  "result-text": str(failure)}])

        result.addCallback(got_result)
        return result

    @mock.patch("landscape.client.manager.scriptexecution.fetch_async")
    def test_fetch_attachment_failure(self, mock_fetch):
        """
        If the plugin fails to retrieve the attachments with a
        L{HTTPCodeError}, a specific error code is shown.
        """
        self.manager.config.url = "https://localhost/message-system"
        persist = Persist(
            filename=os.path.join(self.config.data_path, "broker.bpickle"))
        registration_persist = persist.root_at("registration")
        registration_persist.set("secure-id", "secure_id")
        persist.save()
        headers = {"User-Agent": "landscape-client/%s" % VERSION,
                   "Content-Type": "application/octet-stream",
                   "X-Computer-ID": "secure_id"}

        mock_fetch.return_value = fail(HTTPCodeError(404, "Not found"))

        self.manager.add(ScriptExecutionPlugin())
        result = self._send_script(
            "/bin/sh", "echo hi", attachments={u"file1": 14})

        def got_result(ignored):
            self.assertMessages(
                self.broker_service.message_store.get_pending_messages(),
                [{"type": "operation-result",
                  "operation-id": 123,
                  "result-text": "Server returned HTTP code 404",
                  "result-code": FETCH_ATTACHMENTS_FAILED_RESULT,
                  "status": FAILED}])
            mock_fetch.assert_called_with(
                "https://localhost/attachment/14", headers=headers,
                cainfo=None)

        return result.addCallback(got_result)
