import os
import unittest
import signal
import tarfile
import ConfigParser

from twisted.internet import reactor
from twisted.internet.defer import succeed, fail, Deferred

from landscape.lib.gpg import InvalidGPGSignature
from landscape.lib.fetch import HTTPCodeError
from landscape.package.store import PackageStore
from landscape.package.releaseupgrader import (
    ReleaseUpgrader, ReleaseUpgraderConfiguration, main)
from landscape.tests.helpers import (
    LandscapeIsolatedTest, RemoteBrokerHelper, LogKeeperHelper,
    EnvironSaverHelper)
from landscape.package.tests.helpers import SmartFacadeHelper
from landscape.manager.manager import SUCCEEDED, FAILED


class ReleaseUpgraderConfigurationTest(unittest.TestCase):

    def test_upgrade_tool_directory(self):
        """
        L{ReleaseUpgraderConfiguration.upgrade_tool_directory} returns the
        path to the directory holding the fetched upgrade-tool files.
        """
        config = ReleaseUpgraderConfiguration()
        self.assertEquals(config.upgrade_tool_directory,
                          os.path.join(config.package_directory,
                                       "upgrade-tool"))


class ReleaseUpgraderTest(LandscapeIsolatedTest):

    helpers = [RemoteBrokerHelper, LogKeeperHelper, SmartFacadeHelper,
               EnvironSaverHelper]

    def setUp(self):
        super(ReleaseUpgraderTest, self).setUp()
        self.config = ReleaseUpgraderConfiguration()
        self.config.data_path = self.makeDir()
        os.mkdir(self.config.package_directory)
        os.mkdir(self.config.upgrade_tool_directory)
        self.store = PackageStore(self.makeFile())
        self.upgrader = ReleaseUpgrader(self.store, self.facade,
                                        self.remote, self.config)
        service = self.broker_service
        service.message_store.set_accepted_types(["operation-result"])

    def get_pending_messages(self):
        return self.broker_service.message_store.get_pending_messages()

    def test_fetch(self):
        """
        L{ReleaseUpgrader.fetch} fetches the upgrade tool tarball and signature
        from the given URLs.
        """
        tarball_url = "http://some/where/karmic.tar.gz"
        signature_url = "http://some/where/karmic.tar.gz.gpg"

        os.rmdir(self.config.upgrade_tool_directory)
        fetch_mock = self.mocker.replace("landscape.lib.fetch.fetch_async")
        fetch_mock(tarball_url)
        self.mocker.result(succeed("tarball"))
        fetch_mock(signature_url)
        self.mocker.result(succeed("signature"))

        self.mocker.replay()
        result = self.upgrader.fetch(tarball_url,
                                     signature_url)

        def check_result(ignored):
            directory = self.config.upgrade_tool_directory
            self.assertFileContent(
                os.path.join(directory, "karmic.tar.gz"), "tarball")
            self.assertFileContent(
                os.path.join(directory, "karmic.tar.gz.gpg"), "signature")
            self.assertIn("INFO: Successfully fetched upgrade-tool files",
                          self.logfile.getvalue())

        result.addCallback(check_result)
        return result

    def test_fetch_with_errors(self):
        """
        L{ReleaseUpgrader.fetch} logs a warning in case any of the upgrade tool
        files fails to be fetched.
        """
        tarball_url = "http://some/where/karmic.tar.gz"
        signature_url = "http://some/where/karmic.tar.gz.gpg"

        fetch_mock = self.mocker.replace("landscape.lib.fetch.fetch_async")
        fetch_mock(tarball_url)
        self.mocker.result(succeed("tarball"))
        fetch_mock(signature_url)
        self.mocker.result(fail(HTTPCodeError(404, "not found")))
        self.mocker.replay()

        result = self.upgrader.fetch(tarball_url,
                                     signature_url)

        def check_failure(failure):
            self.assertIn("WARNING: Couldn't fetch file from %s (Server return"
                          "ed HTTP code 404)" % signature_url,
                          self.logfile.getvalue())
            self.assertIn("WARNING: Couldn't fetch all upgrade-tool files",
                          self.logfile.getvalue())

        result.addCallback(self.fail)
        result.addErrback(check_failure)
        return result

    def test_verify(self):
        """
        L{ReleaseUpgrader.verify} verifies the upgrade tool tarball against
        its signature.
        """
        tarball_filename = "/some/tarball"
        signature_filename = "/some/signature"

        gpg_verify_mock = self.mocker.replace("landscape.lib.gpg.gpg_verify")
        gpg_verify_mock(tarball_filename, signature_filename)
        self.mocker.result(succeed(True))
        self.mocker.replay()

        result = self.upgrader.verify(tarball_filename, signature_filename)

        def check_result(ignored):
            self.assertIn("INFO: Successfully verified upgrade-tool tarball",
                          self.logfile.getvalue())

        result.addCallback(check_result)
        return result

    def test_verify_invalid_signature(self):
        """
        L{ReleaseUpgrader.verify} logs a warning in case the tarball signature
        is not valid.
        """
        tarball_filename = "/some/tarball"
        signature_filename = "/some/signature"

        gpg_verify_mock = self.mocker.replace("landscape.lib.gpg.gpg_verify")
        gpg_verify_mock(tarball_filename, signature_filename)
        self.mocker.result(fail(InvalidGPGSignature("gpg error")))
        self.mocker.replay()

        result = self.upgrader.verify(tarball_filename, signature_filename)

        def check_failure(failure):
            self.assertIn("WARNING: Invalid signature for upgrade-tool "
                          "tarball: gpg error", self.logfile.getvalue())

        result.addCallback(self.fail)
        result.addErrback(check_failure)
        return result

    def test_extract(self):
        """
        The L{ReleaseUpgrader.extract} method extracts the upgrade-tool tarball
        in the proper directory.
        """
        original_filename = self.makeFile("data\n")
        tarball_filename = self.makeFile()
        tarball = tarfile.open(tarball_filename, "w:gz")
        tarball.add(original_filename, arcname="file")
        tarball.close()

        result = self.upgrader.extract(tarball_filename)

        def check_result(ignored):
            filename = os.path.join(self.config.upgrade_tool_directory, "file")
            self.assertTrue(os.path.exists(filename))
            self.assertFileContent(filename, "data\n")

        result.addCallback(check_result)
        return result

    def test_tweak_fixes_broken_dapper_config(self):
        """
        The L{ReleaseUpgrader.tweak} method fixes a missing section in the
        dapper config files included in the upgrade tool tarball.
        """
        config_filename = os.path.join(self.config.upgrade_tool_directory,
                                       "DistUpgrade.cfg.dapper")
        self.makeFile(path=config_filename,
                      content="[Files]\n"
                              "BackupExt=distUpgrade\n"
                              "LogDir=/var/log/dist-upgrade\n")

        result = self.upgrader.tweak("dapper")

        def check_result(ignored):
            config = ConfigParser.ConfigParser()
            config.read(config_filename)
            self.assertFalse(config.getboolean("NonInteractive",
                                               "ForceOverwrite"))

        result.addCallback(check_result)
        return result

    def test_tweak_does_not_change_good_dapper_config(self):
        """
        The L{ReleaseUpgrader.tweak} method doesn't change the dapper config
        file if it's not broken.
        """
        config_filename = os.path.join(self.config.upgrade_tool_directory,
                                       "DistUpgrade.cfg.dapper")
        self.makeFile(path=config_filename,
                      content="[NonInteractive]\n"
                              "ForceOverwrite=No\n")

        result = self.upgrader.tweak("dapper")

        def check_result(ignored):
            config = ConfigParser.ConfigParser()
            config.read(config_filename)
            self.assertFalse(config.getboolean("NonInteractive",
                                               "ForceOverwrite"))

        result.addCallback(check_result)
        return result

    def test_tweak_includes_landscape_ppa_in_mirrors(self):
        """
        The L{ReleaseUpgrader.tweak} method adds the Landscape PPA repository
        to the list of available mirrors.
        """
        mirrors_filename = os.path.join(self.config.upgrade_tool_directory,
                                        "mirrors.cfg")
        self.makeFile(path=mirrors_filename,
                      content="ftp://ftp.lug.ro/ubuntu/\n")

        def check_result(ignored):
            self.assertFileContent(mirrors_filename,
                                   "ftp://ftp.lug.ro/ubuntu/\n"
                                   "http://ppa.launchpad.net/landscape/"
                                   "trunk/ubuntu/\n")

        result = self.upgrader.tweak("hardy")
        result.addCallback(check_result)
        return result

    def test_tweak_sets_dbus_start_script(self):
        """
        The L{ReleaseUpgrader.tweak} method adds to the upgrade-tool
        configuration a little script that starts dbus after the upgrade.
        """
        config_filename = os.path.join(self.config.upgrade_tool_directory,
                                       "DistUpgrade.cfg.dapper")
        self.makeFile(path=config_filename,
                      content="[Distro]\n"
                              "PostInstallScripts=/foo.sh\n")

        def check_result(ignored):
            config = ConfigParser.ConfigParser()
            config.read(config_filename)
            self.assertEquals(config.get("Distro", "PostInstallScripts"),
                              "/foo.sh, ./dbus.sh")
            dbus_sh = os.path.join(self.config.upgrade_tool_directory,
                                   "dbus.sh")
            self.assertFileContent(dbus_sh,
                                   "#!/bin/sh\n"
                                   "/etc/init.d/dbus start\n"
                                   "sleep 10\n")

        result = self.upgrader.tweak("dapper")
        result.addCallback(check_result)
        return result

    def test_default_logs_directory(self):
        """
        The default directory for the upgrade-tool logs is the system one.
        """
        self.assertEquals(self.upgrader.logs_directory,
                          "/var/log/dist-upgrade")

    def test_default_logs_limit(self):
        """
        The default read limit for the upgrade-tool logs is 100000 bytes.
        """
        self.assertEquals(self.upgrader.logs_limit, 100000)

    def test_make_operation_result_text(self):
        """
        L{ReleaseUpgrade.make_operation_result_text} aggregates the contents of
        the process standard output, error and log files.
        """
        self.upgrader.logs_directory = self.makeDir()
        self.makeFile(basename="main.log",
                      dirname=self.upgrader.logs_directory,
                      content="main log")
        self.makeFile(basename="apt.log",
                      dirname=self.upgrader.logs_directory,
                      content="apt log")
        text = self.upgrader.make_operation_result_text("stdout", "stderr")
        self.assertEquals(text,
                          "=== Standard output ===\n\n"
                          "stdout\n\n"
                          "=== Standard error ===\n\n"
                          "stderr\n\n"
                          "=== apt.log ===\n\n"
                          "apt log\n\n"
                          "=== main.log ===\n\n"
                          "main log\n\n")

    def test_make_operation_result_text_with_no_stderr(self):
        """
        L{ReleaseUpgrade.make_operation_result_text} skips the standard error
        if it's empty.
        """
        self.upgrader.logs_directory = self.makeDir()
        text = self.upgrader.make_operation_result_text("stdout", "")
        self.assertEquals(text,
                          "=== Standard output ===\n\n"
                          "stdout\n\n")

    def test_make_operation_result_text_only_considers_log_files(self):
        """
        L{ReleaseUpgrade.make_operation_result_text} only considers log files
        from the last upgrade-tool run, directories containing log files from
        an older run are skipped.
        """
        self.upgrader.logs_directory = self.makeDir()
        self.makeDir(dirname=self.upgrader.logs_directory)
        text = self.upgrader.make_operation_result_text("stdout", "stderr")
        self.assertEquals(text,
                          "=== Standard output ===\n\n"
                          "stdout\n\n"
                          "=== Standard error ===\n\n"
                          "stderr\n\n")

    def test_make_operation_result_text_trims_long_files(self):
        """
        L{ReleaseUpgrade.make_operation_result_text} only reads the last
        L{logs_limit} lines of a log file.
        """
        self.upgrader.logs_directory = self.makeDir()
        self.upgrader.logs_limit = 8
        self.makeFile(basename="main.log",
                      dirname=self.upgrader.logs_directory,
                      content="very long log")
        text = self.upgrader.make_operation_result_text("stdout", "stderr")
        self.assertEquals(text,
                          "=== Standard output ===\n\n"
                          "stdout\n\n"
                          "=== Standard error ===\n\n"
                          "stderr\n\n"
                          "=== main.log ===\n\n"
                          "long log\n\n")

    def test_upgrade(self):
        """
        The L{ReleaseUpgrader.upgrade} method spawns the appropropriate
        upgrade-tool script and reports the result.
        """
        self.upgrader.logs_directory = self.makeDir()
        upgrade_tool_directory = self.config.upgrade_tool_directory
        upgrade_tool_filename = os.path.join(upgrade_tool_directory, "karmic")
        fd = open(upgrade_tool_filename, "w")
        fd.write("#!/bin/sh\n"
                 "echo $@\n"
                 "echo FOO=$FOO\n"
                 "echo PWD=$PWD\n"
                 "echo out\n")
        fd.close()
        os.chmod(upgrade_tool_filename, 0755)
        env_backup = os.environ.copy()
        os.environ.clear()
        os.environ.update({"FOO": "bar"})
        deferred = Deferred()

        def do_test():

            result = self.upgrader.upgrade("karmic", 100)

            def check_result(ignored):
                self.assertIn("INFO: Queuing message with release upgrade "
                              "results to exchange urgently.",
                              self.logfile.getvalue())
                result_text = (u"=== Standard output ===\n\n"
                               "--frontend DistUpgradeViewNonInteractive\n"
                               "FOO=bar\n"
                               "PWD=%s\nout\n\n\n" % upgrade_tool_directory)
                self.assertMessages(self.get_pending_messages(),
                                    [{"type": "operation-result",
                                      "operation-id": 100,
                                      "status": SUCCEEDED,
                                      "result-text": result_text,
                                      "result-code": 0}])

            result.addCallback(check_result)
            result.chainDeferred(deferred)

        reactor.callWhenRunning(do_test)

        def cleanup(ignored):
            os.environ = env_backup
            return ignored

        return deferred.addBoth(cleanup)

    def test_upgrade_with_server_mode(self):
        """
        The L{ReleaseUpgrader.upgrade} accepts an optional C{mode} parameter
        which gets passed to the upgrade-tool script as argument for the
        C{--mode} command line option.
        """
        self.upgrader.logs_directory = self.makeDir()
        upgrade_tool_directory = self.config.upgrade_tool_directory
        upgrade_tool_filename = os.path.join(upgrade_tool_directory, "hardy")
        self.makeFile(path=upgrade_tool_filename,
                      content="#!/bin/sh\n"
                                "echo $@\n")
        os.chmod(upgrade_tool_filename, 0755)
        deferred = Deferred()

        def do_test():

            result = self.upgrader.upgrade("hardy", 100, mode="server")

            def check_result(ignored):
                result_text = (u"=== Standard output ===\n\n"
                               "--frontend DistUpgradeViewNonInteractive "
                               "--mode server\n\n\n")
                self.assertMessages(self.get_pending_messages(),
                                    [{"type": "operation-result",
                                      "operation-id": 100,
                                      "status": SUCCEEDED,
                                      "result-text": result_text,
                                      "result-code": 0}])

            result.addCallback(check_result)
            result.chainDeferred(deferred)

        reactor.callWhenRunning(do_test)
        return deferred

    def test_upgrade_with_env_variables(self):
        """
        The L{ReleaseUpgrader.upgrade} method optionally sets environment
        variables to be passed to the upgrade-tool process.
        """
        self.upgrader.logs_directory = self.makeDir()
        upgrade_tool_directory = self.config.upgrade_tool_directory
        upgrade_tool_filename = os.path.join(upgrade_tool_directory, "karmic")
        fd = open(upgrade_tool_filename, "w")
        fd.write("#!/bin/sh\n"
                 "echo DEBUG_UPDATE_MANAGER=$DEBUG_UPDATE_MANAGER\n"
                 "echo RELEASE_UPRADER_ALLOW_THIRD_PARTY="
                 "$RELEASE_UPRADER_ALLOW_THIRD_PARTY\n")
        fd.close()
        os.chmod(upgrade_tool_filename, 0755)
        env_backup = os.environ.copy()
        os.environ.clear()
        deferred = Deferred()

        def do_test():

            result = self.upgrader.upgrade("karmic", 100,
                                           allow_third_party=True,
                                           debug=True)

            def check_result(ignored):
                result_text = (u"=== Standard output ===\n\n"
                               "DEBUG_UPDATE_MANAGER=True\n"
                               "RELEASE_UPRADER_ALLOW_THIRD_PARTY=True\n\n\n")
                self.assertMessages(self.get_pending_messages(),
                                    [{"type": "operation-result",
                                      "operation-id": 100,
                                      "status": SUCCEEDED,
                                      "result-text": result_text,
                                      "result-code": 0}])

            result.addCallback(check_result)
            result.chainDeferred(deferred)

        reactor.callWhenRunning(do_test)

        def cleanup(ignored):
            os.environ = env_backup
            return ignored

        return deferred.addBoth(cleanup)

    def test_upgrade_with_failure(self):
        """
        The L{ReleaseUpgrader.upgrade} sends a message with failed status
        field if the upgrade-tool exits with non-zero code.
        """
        self.upgrader.logs_directory = self.makeDir()
        upgrade_tool_directory = self.config.upgrade_tool_directory
        upgrade_tool_filename = os.path.join(upgrade_tool_directory, "karmic")
        fd = open(upgrade_tool_filename, "w")
        fd.write("#!/bin/sh\n"
                 "echo out\n"
                 "echo err >&2\n"
                 "exit 3")
        fd.close()
        os.chmod(upgrade_tool_filename, 0755)

        deferred = Deferred()

        def do_test():

            result = self.upgrader.upgrade("karmic", 100)

            def check_result(ignored):
                result_text = (u"=== Standard output ===\n\nout\n\n\n"
                               "=== Standard error ===\n\nerr\n\n\n")
                self.assertMessages(self.get_pending_messages(),
                                    [{"type": "operation-result",
                                      "operation-id": 100,
                                      "status": FAILED,
                                      "result-text": result_text,
                                      "result-code": 3}])

            result.addCallback(check_result)
            result.chainDeferred(deferred)

        reactor.callWhenRunning(do_test)
        return deferred

    def test_upgrade_with_open_child_fds(self):
        """
        The deferred returned by the L{ReleaseUpgrader.upgrade} method
        callbacks correctly even if the spawned upgrade-tool process forks
        and passes its files descriptors over to child processes we don't know
        about.
        """
        self.upgrader.logs_directory = self.makeDir()
        upgrade_tool_directory = self.config.upgrade_tool_directory
        upgrade_tool_filename = os.path.join(upgrade_tool_directory, "karmic")
        child_pid_filename = self.makeFile()
        fd = open(upgrade_tool_filename, "w")
        fd.write("#!/usr/bin/env python\n"
                 "import os\n"
                 "import time\n"
                 "import sys\n"
                 "if __name__ == '__main__':\n"
                 "    print 'First parent'\n"
                 "    pid = os.fork()\n"
                 "    if pid > 0:\n"
                 "        time.sleep(0.5)\n"
                 "        sys.exit(0)\n"
                 "    pid = os.fork()\n"
                 "    if pid > 0:\n"
                 "        fd = open('%s', 'w')\n"
                 "        fd.write(str(pid))\n"
                 "        fd.close()\n"
                 "        sys.exit(0)\n"
                 "    while True:\n"
                 "        time.sleep(2)\n" % child_pid_filename)
        fd.close()
        os.chmod(upgrade_tool_filename, 0755)
        os.environ.clear()
        os.environ.update({"FOO": "bar"})
        deferred = Deferred()

        def do_test():

            result = self.upgrader.upgrade("karmic", 100)

            def kill_child(how):
                fd = open(child_pid_filename, "r")
                child_pid = int(fd.read())
                fd.close()
                os.remove(child_pid_filename)
                try:
                    os.kill(child_pid, signal.SIGKILL)
                    self.assertEquals(how, "cleanly")
                    return child_pid
                except OSError:
                    pass

            force_kill_child = reactor.callLater(2, kill_child, "brutally")

            def check_result(ignored):
                force_kill_child.cancel()
                self.assertIn("INFO: Queuing message with release upgrade "
                              "results to exchange urgently.",
                              self.logfile.getvalue())
                child_pid = kill_child("cleanly")
                result_text = self.get_pending_messages()[0]["result-text"]
                self.assertIn("First parent\n", result_text)

            result.addCallback(check_result)
            result.chainDeferred(deferred)

        reactor.callWhenRunning(do_test)

        def cleanup(ignored):
            self.assertFalse(os.path.exists(child_pid_filename))
            return ignored

        return deferred.addBoth(cleanup)

    def test_finish(self):
        """
        The L{ReleaseUpgrader.finish} method wipes the upgrade-tool directory
        and spawn the package-reporter, to inform the server of the changed
        packages.
        """
        upgrade_tool_directory = self.config.upgrade_tool_directory
        open(os.path.join(upgrade_tool_directory, "somefile"), "w").close()
        os.mkdir(os.path.join(upgrade_tool_directory, "somedir"))

        reporter_filename = self.makeFile("#!/bin/sh\n"
                                          "echo $@\n"
                                          "echo $(pwd)\n")
        os.chmod(reporter_filename, 0755)

        find_reporter_mock = self.mocker.replace("landscape.package.reporter."
                                                 "find_reporter_command")
        find_reporter_mock()
        self.mocker.result(reporter_filename)
        self.mocker.replay()

        deferred = Deferred()

        def do_test():

            result = self.upgrader.finish()

            def check_result((out, err, code)):
                self.assertFalse(os.path.exists(upgrade_tool_directory))
                self.assertEquals(out, "--force-smart-update\n%s\n"
                                  % os.getcwd())
                self.assertEquals(err, "")
                self.assertEquals(code, 0)

            result.addCallback(check_result)
            result.chainDeferred(deferred)

        reactor.callWhenRunning(do_test)
        return deferred

    def test_finish_as_root(self):
        """
        If the release-upgrader process is run as root, as it alwyas should,
        the L{ReleaseUpgrader.finish} method spawns the package-reporter with
        the landscape uid and gid.
        """

        find_reporter_mock = self.mocker.replace("landscape.package.reporter."
                                                 "find_reporter_command")
        find_reporter_mock()
        self.mocker.result("reporter")

        getuid_mock = self.mocker.replace("os.getuid")
        getuid_mock()
        self.mocker.result(0)

        getpwnam_mock = self.mocker.replace("pwd.getpwnam")
        getpwnam_mock("landscape")

        class FakePwNam(object):
            pw_uid = 1234

        self.mocker.result(FakePwNam())

        getgrnam_mock = self.mocker.replace("grp.getgrnam")
        getgrnam_mock("landscape")

        class FakeGrNam(object):
            gr_gid = 5678

        self.mocker.result(FakeGrNam())

        spawn_process_calls = []

        def spawn_process(pp, reporter, args=None, uid=None, gid=None,
                          path=None, env=None):
            self.assertEquals(uid, 1234)
            self.assertEquals(gid, 5678)
            spawn_process_calls.append(True)

        saved_spawn_process = reactor.spawnProcess
        reactor.spawnProcess = spawn_process

        self.mocker.replay()

        try:
            self.upgrader.finish()
        finally:
            reactor.spawnProcess = saved_spawn_process
        self.assertEquals(spawn_process_calls, [True])

    def test_finish_with_config_file(self):
        """
        The L{ReleaseUpgrader.finish} method passes over to the reporter the
        configuration file the release-upgrader was called with.
        """
        reporter_filename = self.makeFile("#!/bin/sh\necho $@\n")
        os.chmod(reporter_filename, 0755)
        self.config.config = "/some/config"
        find_reporter_mock = self.mocker.replace("landscape.package.reporter."
                                                 "find_reporter_command")
        find_reporter_mock()
        self.mocker.result(reporter_filename)
        self.mocker.replay()

        deferred = Deferred()

        def do_test():

            result = self.upgrader.finish()

            def check_result((out, err, code)):
                self.assertEquals(out, "--force-smart-update "
                                       "--config=/some/config\n")
                self.assertEquals(err, "")
                self.assertEquals(code, 0)

            result.addCallback(check_result)
            result.chainDeferred(deferred)

        reactor.callWhenRunning(do_test)
        return deferred

    def test_handle_release_upgrade(self):
        """
        The L{ReleaseUpgrader.handle_release_upgrade} method calls the other
        helper methods in the right order and with the right arguments.
        """
        calls = []
        upgrade_tool_directory = self.config.upgrade_tool_directory

        def fetch(tarball_url, signature_url):
            self.assertEquals(tarball_url, "http://some/tarball")
            self.assertEquals(signature_url, "http://some/sign")
            calls.append("fetch")
            return succeed(None)

        def verify(tarball_filename, signature_filename):
            self.assertEquals(tarball_filename,
                              os.path.join(upgrade_tool_directory, "tarball"))
            self.assertEquals(signature_filename,
                              os.path.join(upgrade_tool_directory, "sign"))
            calls.append("verify")

        def extract(filename_tarball):
            self.assertEquals(filename_tarball,
                              os.path.join(upgrade_tool_directory, "tarball"))
            calls.append("extract")

        def tweak(current_code_name):
            self.assertEquals(current_code_name, "jaunty")
            calls.append("tweak")

        def upgrade(code_name, operation_id, allow_third_party=False,
                    debug=False, mode=None):
            self.assertEquals(operation_id, 100)
            self.assertEquals(code_name, "karmic")
            self.assertTrue(allow_third_party)
            self.assertFalse(debug)
            self.assertIdentical(mode, None)
            calls.append("upgrade")

        def finish():
            calls.append("finish")

        self.upgrader.fetch = fetch
        self.upgrader.verify = verify
        self.upgrader.extract = extract
        self.upgrader.tweak = tweak
        self.upgrader.upgrade = upgrade
        self.upgrader.finish = finish

        self.upgrader.lsb_release_filename = self.makeFile(
            "DISTRIB_CODENAME=jaunty\n")

        message = {"type": "release-upgrade",
                   "code-name": "karmic",
                   "upgrade-tool-tarball-url": "http://some/tarball",
                   "upgrade-tool-signature-url": "http://some/sign",
                   "allow-third-party": True,
                   "operation-id": 100}

        result = self.upgrader.handle_release_upgrade(message)

        def check_result(ignored):
            self.assertEquals(calls, ["fetch", "verify", "extract", "tweak",
                                      "upgrade", "finish"])

        result.addCallback(check_result)
        return result

    def test_handle_release_upgrade_on_dapper_server(self):
        """
        On Dapper server, the L{ReleaseUpgrader.handle_release_upgrade}
        method calls sets the upgrade-tool running mode to "server".
        """
        calls = []

        def upgrade(code_name, operation_id, allow_third_party=False,
                    debug=False, mode=None):
            self.assertEquals(mode, "server")
            calls.append("upgrade")

        self.upgrader.fetch = lambda x, y: succeed(None)
        self.upgrader.verify = lambda x, y: None
        self.upgrader.extract = lambda x: None
        self.upgrader.tweak = lambda x: None
        self.upgrader.upgrade = upgrade
        self.upgrader.finish = lambda: None

        self.upgrader.lsb_release_filename = self.makeFile(
            "DISTRIB_CODENAME=dapper\n")

        message = {"type": "release-upgrade",
                   "code-name": "hardy",
                   "upgrade-tool-tarball-url": "http://some/tarball",
                   "upgrade-tool-signature-url": "http://some/sign",
                   "operation-id": 100}

        result = self.upgrader.handle_release_upgrade(message)

        def check_result(ignored):
            self.assertEquals(calls, ["upgrade"])

        result.addCallback(check_result)
        return result

    def test_handle_release_upgrade_with_already_upgraded_system(self):
        """
        The L{ReleaseUpgrader.handle_release_upgrade} method reports a
        failure if the system is already running the desired release.
        """
        self.upgrader.lsb_release_filename = self.makeFile(
            "DISTRIB_CODENAME=karmic\n")

        message = {"type": "release-upgrade",
                   "code-name": "karmic",
                   "operation-id": 100}

        result = self.upgrader.handle_release_upgrade(message)

        def check_result(ignored):
            self.assertIn("INFO: Queuing message with release upgrade "
                          "failure to exchange urgently.",
                          self.logfile.getvalue())
            self.assertMessages(self.get_pending_messages(),
                                [{"type": "operation-result",
                                  "operation-id": 100,
                                  "status": FAILED,
                                  "result-text": "The system is already "
                                                 "running karmic.",
                                  "result-code": 1}])

        result.addCallback(check_result)
        return result

    def test_handle_release_upgrade_with_abort(self):
        """
        The L{ReleaseUpgrader.handle_release_upgrade} method reports a
        failure if any of the helper method errbacks.
        """
        self.upgrader.lsb_release_filename = self.makeFile(
            "DISTRIB_CODENAME=jaunty\n")

        calls = []

        def fetch(tarball_url, signature_url):
            calls.append("fetch")
            return succeed(None)

        def verify(tarball_filename, signature_filename):
            calls.append("verify")
            raise Exception("failure")

        def extract(tarball_filename):
            calls.append("extract")

        def tweak(current_code_name):
            calls.append("extract")

        def upgrade(code_name, operation_id):
            calls.append("upgrade")

        def finish():
            calls.append("finish")

        self.upgrader.fetch = fetch
        self.upgrader.verify = verify
        self.upgrader.extract = extract
        self.upgrader.tweak = tweak
        self.upgrader.upgrade = upgrade
        self.upgrader.finish = finish

        message = {"type": "release-upgrade",
                   "code-name": "karmic",
                   "operation-id": 100,
                   "upgrade-tool-tarball-url": "http://some/tarball",
                   "upgrade-tool-signature-url": "http://some/signature"}

        result = self.upgrader.handle_release_upgrade(message)

        def check_result(ignored):
            self.assertIn("INFO: Queuing message with release upgrade "
                          "failure to exchange urgently.",
                          self.logfile.getvalue())
            self.assertMessages(self.get_pending_messages(),
                                [{"type": "operation-result",
                                  "operation-id": 100,
                                  "status": FAILED,
                                  "result-text": "failure",
                                  "result-code": 1}])
            self.assertEquals(calls, ["fetch", "verify"])

        result.addCallback(check_result)
        return result

    def test_handle_task(self):
        """
        The L{ReleaseUpgrader.handle_task} method invokes the correct
        handler for tasks carrying messages of type C{release-upgrade}.
        """
        self.upgrader.handle_release_upgrade = lambda message: message

        message = {"type": "release-upgrade"}

        class FakeTask(object):
            data = message

        task = FakeTask()
        self.assertEquals(self.upgrader.handle_task(task), task.data)

    def test_handle_task_with_wrong_type(self):
        """
        The L{ReleaseUpgrader.handle_task} method doesn't take any action
        if the message carried by task is not known.
        """
        message = {"type": "foo"}

        class FakeTask(object):
            data = message

        self.assertEquals(self.upgrader.handle_task(FakeTask()), None)

    def test_main(self):
        """
        The L{main} function creates a new session if the process is not
        running in its own process group.
        """
        self.mocker.order()

        run_task_handler = self.mocker.replace("landscape.package.taskhandler"
                                               ".run_task_handler",
                                               passthrough=False)
        setsid = self.mocker.replace("os.setsid")
        setsid()

        run_task_handler(ReleaseUpgrader, ["ARGS"])
        self.mocker.result("RESULT")

        self.mocker.replay()

        self.assertEquals(main(["ARGS"]), "RESULT")
