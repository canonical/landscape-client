import itertools
import shutil
import tempfile

from glob import glob

from twisted.internet.utils import getProcessOutputAndValue


class InvalidGPGSignature(Exception):
    """Raised when the gpg signature for a given file is invalid."""


def gpg_verify(filename, signature, gpg="/usr/bin/gpg", apt_dir="/etc/apt"):
    """Verify the GPG signature of a file.

    @param filename: Path to the file to verify the signature against.
    @param signature: Path to signature to use.
    @param gpg: Optionally, path to the GPG binary to use.
    @param apt_dir: Optionally, path to apt trusted keyring.
    @return: a C{Deferred} resulting in C{True} if the signature is
             valid, C{False} otherwise.
        """

    def remove_gpg_home(ignored):
        shutil.rmtree(gpg_home)
        return ignored

    def check_gpg_exit_code(args):
        out, err, code = args
        # We want a nice error message with Python 3 as well, so decode the
        # bytes here.
        out, err = out.decode("ascii"), err.decode("ascii")
        if code != 0:
            raise InvalidGPGSignature("%s failed (out='%s', err='%s', "
                                      "code='%d')" % (gpg, out, err, code))

    gpg_home = tempfile.mkdtemp()
    keyrings = tuple(itertools.chain(*[
        ("--keyring", keyring)
        for keyring in sorted(
            glob("{}/trusted.gpg".format(apt_dir)) +
            glob("{}/trusted.gpg.d/*.gpg".format(apt_dir))
        )
    ]))
    args = (
        "--no-options", "--homedir", gpg_home, "--no-default-keyring",
        "--ignore-time-conflict"
    ) + keyrings + ("--verify", signature, filename)

    result = getProcessOutputAndValue(gpg, args=args)
    result.addBoth(remove_gpg_home)
    result.addCallback(check_gpg_exit_code)
    return result
