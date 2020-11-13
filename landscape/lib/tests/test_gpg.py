import mock
import os
import textwrap
import unittest

from twisted.internet import reactor
from twisted.internet.defer import Deferred, inlineCallbacks

from landscape.lib import testing
from landscape.lib.gpg import gpg_verify


class GPGTest(testing.FSTestCase, testing.TwistedTestCase, unittest.TestCase):

    def test_gpg_verify(self):
        """
        L{gpg_verify} runs the given gpg binary and returns C{True} if the
        provided signature is valid.
        """
        aptdir = self.makeDir()
        os.mknod("{}/trusted.gpg".format(aptdir))
        gpg_options = self.makeFile()
        gpg = self.makeFile("#!/bin/sh\n"
                            "touch $3/trustdb.gpg\n"
                            "echo -n $@ > %s\n" % gpg_options)
        os.chmod(gpg, 0o755)
        gpg_home = self.makeDir()
        deferred = Deferred()

        @mock.patch("tempfile.mkdtemp")
        def do_test(mkdtemp_mock):
            mkdtemp_mock.return_value = gpg_home
            result = gpg_verify(
                "/some/file", "/some/signature", gpg=gpg, apt_dir=aptdir)

            def check_result(ignored):
                self.assertEqual(
                    open(gpg_options).read(),
                    "--no-options --homedir %s --no-default-keyring "
                    "--ignore-time-conflict --keyring %s/trusted.gpg "
                    "--verify /some/signature /some/file" % (gpg_home, aptdir))
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
        os.chmod(gpg, 0o755)
        gpg_home = self.makeDir()
        deferred = Deferred()

        @mock.patch("tempfile.mkdtemp")
        def do_test(mkdtemp_mock):
            mkdtemp_mock.return_value = gpg_home
            result = gpg_verify("/some/file", "/some/signature", gpg=gpg)

            def check_failure(failure):
                self.assertEqual(str(failure.value),
                                 "%s failed (out='out\n', err='err\n', "
                                 "code='1')" % gpg)
                self.assertFalse(os.path.exists(gpg_home))

            result.addCallback(self.fail)
            result.addErrback(check_failure)
            result.chainDeferred(deferred)

        reactor.callWhenRunning(do_test)
        return deferred

    @inlineCallbacks
    def test_gpg_verify_trusted_dir(self):
        """
        gpg_verify uses keys from the trusted.gpg.d if such a folder exists.
        """
        apt_dir = self.makeDir()
        os.mkdir("{}/trusted.gpg.d".format(apt_dir))
        os.mknod("{}/trusted.gpg.d/foo.gpg".format(apt_dir))
        os.mknod("{}/trusted.gpg.d/baz.gpg".format(apt_dir))
        os.mknod("{}/trusted.gpg.d/bad.gpg~".format(apt_dir))

        gpg_call = self.makeFile()
        fake_gpg = self.makeFile(textwrap.dedent("""\
            #!/bin/sh
            touch $3/trustdb.gpg
            echo -n $@ > {}
        """).format(gpg_call))
        os.chmod(fake_gpg, 0o755)
        gpg_home = self.makeDir()

        with mock.patch("tempfile.mkdtemp", return_value=gpg_home):
            yield gpg_verify(
                "/some/file", "/some/signature", gpg=fake_gpg, apt_dir=apt_dir)

        expected = (
            "--no-options --homedir {gpg_home} --no-default-keyring "
            "--ignore-time-conflict "
            "--keyring {apt_dir}/trusted.gpg.d/baz.gpg "
            "--keyring {apt_dir}/trusted.gpg.d/foo.gpg "
            "--verify /some/signature /some/file"
        ).format(gpg_home=gpg_home, apt_dir=apt_dir)
        with open(gpg_call) as call:
            self.assertEqual(expected, call.read())
            self.assertFalse(os.path.exists(gpg_home))
