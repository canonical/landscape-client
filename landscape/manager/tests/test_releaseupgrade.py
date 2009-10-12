import os
import base64

from twisted.internet import reactor
from twisted.internet.defer import succeed, fail, Deferred

from landscape.lib.gpg import InvalidGpgSignature
from landscape.lib.fetch import HTTPCodeError
from landscape.manager.releaseupgrade import ReleaseUpgrade
from landscape.tests.helpers import (
    LandscapeIsolatedTest, ManagerHelper, LogKeeperHelper)


SAMPLE_TARBALL = "H4sIAKoz00oAA+3RQQrCMBCF4Vl7ipygnbQzyXkCtlDoqtb72yKCbioIQc" \
                 "T/2wxMsnjDa1qpTjfZ\nfZ8xuz7PB4mxS5b6mHrb9jmZS/D60USul7UsIc" \
                 "i4DMPRv3fvP6ppx2mufNhecDI76N9f+4/q2knQ\nurHu/rz/c1nL6dshAA" \
                 "AAAAAAAAAAAAAAAHzkBrUGOrYAKAAA\n"


class ReleaseUpgradeTest(LandscapeIsolatedTest):

    helpers = [ManagerHelper, LogKeeperHelper]

    def setUp(self):
        super(ReleaseUpgradeTest, self).setUp()
        self.broker_service.message_store.set_accepted_types(
            ["release-upgrade"])
        self.plugin = ReleaseUpgrade()
        self.manager.add(self.plugin)

    def test_upgrade_tool_directory(self):
        """
        L{ReleaseUpgrade.upgrade_tool_directory} returns the path to
        the directory holding the fetched upgrade-tool files.
        """
        directory = self.plugin.upgrade_tool_directory
        self.assertEquals(self.plugin.upgrade_tool_directory,
                          os.path.join(self.manager.config.data_path,
                                       "upgrade-tool"))
        self.assertTrue(os.path.exists(self.plugin.upgrade_tool_directory))

    def test_fetch(self):
        """
        L{ReleaseUpgrade.fetch} fetches the upgrade tool tarball and signature
        from the given URLs.
        """
        tarball_url = "http://some/where/karmic.tar.gz"
        signature_url = "http://some/where/karmic.tar.gz.gpg"

        fetch_mock = self.mocker.replace("landscape.lib.fetch.fetch_async")
        fetch_mock(tarball_url)
        self.mocker.result(succeed("tarball"))
        fetch_mock(signature_url)
        self.mocker.result(succeed("signature"))

        self.mocker.replay()
        result = self.plugin.fetch(tarball_url, signature_url)

        def check_result(ignored):
            directory = self.plugin.upgrade_tool_directory
            self.assertFileContent(os.path.join(directory, "karmic.tar.gz"),
                                   "tarball")
            self.assertFileContent(os.path.join(directory, "karmic.tar.gz.gpg"),
                                   "signature")
            self.assertIn("INFO: Successfully fetched upgrade-tool files",
                          self.logfile.getvalue())

        result.addCallback(check_result)
        return result

    def test_fetch_with_errors(self):
        """
        L{ReleaseUpgrade.fetch} logs a warning in case any of the upgrade tool
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

        result = self.plugin.fetch(tarball_url, signature_url)

        def check_failure(failure):
            self.assertIn("WARNING: Couldn't fetch file from %s (Server returned HTTP "
                          "code 404)" % signature_url,
                          self.logfile.getvalue())
            self.assertIn("WARNING: Couldn't fetch all upgrade-tool files",
                          self.logfile.getvalue())

        result.addCallback(self.fail)
        result.addErrback(check_failure)
        return result

    def test_verify(self):
        """
        L{ReleaseUpgrade.verify} verifies the upgrade tool tarball against
        its signature.
        """
        tarball = "/some/tarball"
        signature = "/some/signature"

        gpg_verify_mock = self.mocker.replace("landscape.lib.gpg.gpg_verify")
        gpg_verify_mock(tarball, signature)
        self.mocker.result(succeed(True))
        self.mocker.replay()

        result = self.plugin.verify(tarball, signature)

        def check_result(ignored):
            self.assertIn("INFO: Successfully verified upgrade-tool tarball",
                          self.logfile.getvalue())

        result.addCallback(check_result)
        return result

    def test_verify_invalid_signature(self):
        """
        L{ReleaseUpgrade.verify} logs a warning in case the tarball signature
        is not valid.
        """
        tarball = "/some/tarball"
        signature = "/some/signature"

        gpg_verify_mock = self.mocker.replace("landscape.lib.gpg.gpg_verify")
        gpg_verify_mock(tarball, signature)
        self.mocker.result(fail(InvalidGpgSignature("gpg error")))
        self.mocker.replay()

        result = self.plugin.verify(tarball, signature)

        def check_failure(failure):
            self.assertIn("WARNING: Invalid signature for upgrade-tool "
                          "tarball: gpg error", self.logfile.getvalue())

        result.addCallback(self.fail)
        result.addErrback(check_failure)
        return result

    def test_extract(self):
        """
        The L{ReleaseUpgrade.extract} method extracts the upgrade-tool tarball
        in the proper directory.
        """        
        tarball = self.makeFile(base64.decodestring(SAMPLE_TARBALL))
        result = self.plugin.extract(tarball)

        def check_result(ignored):
            filename = os.path.join(self.plugin.upgrade_tool_directory, "file")
            self.assertTrue(os.path.exists(filename))
            self.assertFileContent(filename, "data\n")

        result.addCallback(check_result)
        return result

    def test_upgrade(self):
        """
        The L{ReleaseUpgrade.upgrade} method spawns the release-upgrader script
        with the proper arguments.
        """
        options = self.makeFile()
        upgrader = self.makeFile("#!/bin/sh\necho -n $@ > %s\n" % options)
        os.chmod(upgrader, 0755)
        find_release_upgrader_command_mock = self.mocker.replace(
            "landscape.manager.releaseupgrade.find_release_upgrader_command")
        find_release_upgrader_command_mock()
        self.mocker.result(upgrader)
        self.mocker.replay()

        deferred = Deferred()

        def do_test():

            result = self.plugin.upgrade("karmic", 100)

            def check_result(ignored):
                config = self.manager.config.config
                self.assertEquals(open(options).read(),
                                  "--release=karmic "
                                  "--operation-id=100")

            result.addCallback(check_result)
            result.chainDeferred(deferred)

        reactor.callWhenRunning(do_test)
        return deferred

    def test_upgrade_with_config(self):
        """
        The L{ReleaseUpgrade.upgrade} hands the config file over to the
        release-upgrader script.
        """
        options = self.makeFile()
        upgrader = self.makeFile("#!/bin/sh\necho -n $@ > %s\n" % options)
        self.manager.config.config = "/some/config"
        os.chmod(upgrader, 0755)
        find_release_upgrader_command_mock = self.mocker.replace(
            "landscape.manager.releaseupgrade.find_release_upgrader_command")
        find_release_upgrader_command_mock()
        self.mocker.result(upgrader)
        self.mocker.replay()

        deferred = Deferred()

        def do_test():

            result = self.plugin.upgrade("karmic", 100)

            def check_result(ignored):
                config = self.manager.config.config
                self.assertEquals(open(options).read(),
                                  "--release=karmic "
                                  "--operation-id=100 "
                                  "--config=/some/config")

            result.addCallback(check_result)
            result.chainDeferred(deferred)

        reactor.callWhenRunning(do_test)
        return deferred

    def test_handle_release_upgrade(self):
        """
        The L{ReleaseUpgrade.handle_release_upgrade} method calls the other
        helper methods in the right order and with the right arguments.
        """
        message = {"operation-id": "100",
                   "tarball-url": "http://some/tarball",
                   "signature-url": "http://some/signature",
                   "release": "karmic"}

        calls = []

        def fetch(tarball_url, signature_url):
            self.assertEquals(tarball_url, "http://some/tarball")
            self.assertEquals(signature_url, "http://some/signature")
            calls.append("fetch")
            return succeed(None)

        def verify(tarball, signature):
            self.assertEquals(tarball, "tarball")
            self.assertEquals(signature, "signature")
            calls.append("verify")

        def extract(tarball):
            self.assertEquals(tarball, "tarball")
            calls.append("extract")

        def upgrade(release, operation_id):
            self.assertEquals(release, "karmic")
            self.assertEquals(operation_id, 100)
            calls.append("upgrade")

        self.plugin.fetch = fetch
        self.plugin.verify = verify
        self.plugin.extract = extract
        self.plugin.upgrade = upgrade

        result = self.plugin.handle_release_upgrade(message)

        def check_result(ignored):
            self.assertEquals(calls, ["fetch", "verify", "extract", "upgrade"])

        result.addCallback(check_result)
        return result
