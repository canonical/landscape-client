import os
import logging
import tarfile
import sys

from twisted.internet.defer import succeed
from twisted.internet.utils import getProcessOutputAndValue

from landscape.lib.fetch import fetch_to_files
from landscape.lib.gpg import gpg_verify
from landscape.manager.manager import ManagerPlugin


class ReleaseUpgrade(ManagerPlugin):
    """Upgrade the system to a greater release."""

    def register(self, registry):
        """Add this plugin to C{registry}.

        The release upgrade plugin handles C{release-upgrade} activity messages
        broadcast from the server.
        """
        super(ReleaseUpgrade, self).register(registry)
        registry.register_message("release-upgrade",
                                  self.handle_release_upgrade)

    @property
    def upgrade_tool_directory(self):
        """
        The directory where the upgrade-tool files get stored and extracted.
        """
        return os.path.join(self.registry.config.data_path, "upgrade-tool")

    def handle_release_upgrade(self, message):
        """Fetch the upgrade-tool, verify it and run it.

        @param message: A message of type C{"release-upgrade"}.
        """
        operation_id = int(message["operation-id"])
        tarball_url = message["tarball-url"]
        signature_url = message["signature-url"]
        tarball = tarball_url.split("/")[-1]
        signature = signature_url.split("/")[-1]
        release = message["release"]

        result = self.fetch(tarball_url, signature_url)
        result.addCallback(lambda x: self.verify(tarball, signature))
        result.addCallback(lambda x: self.extract(tarball))
        result.addCallback(lambda x: self.upgrade(release, operation_id))
        return result

    def fetch(self, tarball_url, signature_url):
        """Fetch the upgrade-tool files.

        @param tarball_url: The upgrade-tool tarball URL.
        @param signature_url: The upgrade-tool signature URL.
        """
        result = fetch_to_files([tarball_url, signature_url],
                                self.upgrade_tool_directory,
                                logger=logging.warning)

        def log_success(ignored):
            logging.info("Successfully fetched upgrade-tool files")

        def log_failure(failure):
            logging.warning("Couldn't fetch all upgrade-tool files")
            return failure

        result.addCallback(log_success)
        result.addErrback(log_failure)
        return result

    def verify(self, tarball, signature):
        """Verify the upgrade-tool tarball against its signature.

        @param tarball: The filename of the fetched upgrade-tool tarball.
        @param signature: The filename of the fetched upgrade-tool signature.
        """
        result = gpg_verify(tarball, signature)

        def log_success(ignored):
            logging.info("Successfully verified upgrade-tool tarball")

        def log_failure(failure):
            logging.warning("Invalid signature for upgrade-tool tarball: %s"
                            % str(failure.value))
            return failure

        result.addCallback(log_success)
        result.addErrback(log_failure)
        return result

    def extract(self, tarball):
        """Extract the upgrade-tool tarball.

        @param tarball: The filename of the fetched upgrade-tool tarball.
        """
        tf = tarfile.open(tarball, "r:gz")
        tf.extractall(path=self.upgrade_tool_directory)
        return succeed(None)

    def upgrade(self, release, operation_id):
        """Run the landscape-release-upgrader command.

        @param release: The newer release to upgrade the system to.
        """
        upgrader = find_release_upgrader_command()
        args = ["--release=%s" % release, "--operation-id=%d" % operation_id]
        config = self.registry.config.config
        if config is not None:
            args.append(" --config=%s" % config)
        result = getProcessOutputAndValue(upgrader, args=args)
        return result


def find_release_upgrader_command():
    """Return the path to the landscape-release-upgrader script."""
    dirname = os.path.dirname(os.path.abspath(sys.argv[0]))
    return os.path.join(dirname, "landscape-release-upgrader")
