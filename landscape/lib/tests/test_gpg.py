import os

from twisted.internet import reactor
from twisted.internet.defer import Deferred

from landscape.tests.helpers import LandscapeIsolatedTest
from landscape.lib.gpg import gpg_verify

class GpgTest(LandscapeIsolatedTest):

    def test_gpg_verify(self):
        """
        L{gpg_verify} runs the given gpg binary and returns C{True} if the
        provided signature is valid.
        """
        gpg_options = self.makeFile()
        gpg = self.makeFile("#!/bin/sh\n"
                            "touch $3/trustdb.gpg\n"
                            "echo -n $@ > %s\n" % gpg_options)
        os.chmod(gpg, 0755)
        gpg_home = self.makeDir()
        mkdtemp_mock = self.mocker.replace("tempfile.mkdtemp")
        mkdtemp_mock()
        self.mocker.result(gpg_home)
        self.mocker.replay()

        deferred = Deferred()

        def do_test():

            result = gpg_verify("/some/file", "/some/signature", gpg=gpg)

            def check_result(ignored):
                self.assertEquals(open(gpg_options).read(),
                    "--no-options --homedir %s --no-default-keyring "
                    "--ignore-time-conflict --keyring /etc/apt/trusted.gpg "
                    "--verify /some/signature /some/file" % gpg_home)
                self.assertFalse(os.path.exists(gpg_home))

            result.addCallback(check_result)
            result.chainDeferred(deferred)

        reactor.callWhenRunning(do_test)
        return deferred

    def test_gpg_verify_with_non_zero_gpg_exit_code(self):
        """
        L{gpg_verify} runs the given gpg binary and returns C{False} if the
        provided signature is not valid.
        """
        gpg = self.makeFile("#!/bin/sh\necho out; echo err >&2; exit 1\n")
        os.chmod(gpg, 0755)
        gpg_home = self.makeDir()
        mkdtemp_mock = self.mocker.replace("tempfile.mkdtemp")
        mkdtemp_mock()
        self.mocker.result(gpg_home)
        self.mocker.replay()

        deferred = Deferred()

        def do_test():

            result = gpg_verify("/some/file", "/some/signature", gpg=gpg)

            def check_failure(failure):
                self.assertEquals(str(failure.value),
                                  "%s failed (out='out\n', err='err\n', "
                                  "code='1')" % gpg)
                self.assertFalse(os.path.exists(gpg_home))

            result.addCallback(self.fail)
            result.addErrback(check_failure)
            result.chainDeferred(deferred)

        reactor.callWhenRunning(do_test)
        return deferred
