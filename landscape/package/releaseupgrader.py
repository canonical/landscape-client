import os
import sys
import grp
import pwd
import shutil
import logging
import tarfile

from twisted.internet.defer import succeed
from twisted.internet.utils import getProcessOutputAndValue

from landscape.lib.fetch import url_to_filename, fetch_to_files
from landscape.lib.lsb_release import parse_lsb_release, LSB_RELEASE_FILENAME
from landscape.lib.gpg import gpg_verify
from landscape.package.taskhandler import (
    PackageTaskHandlerConfiguration, PackageTaskHandler, run_task_handler)
from landscape.manager.manager import SUCCEEDED, FAILED
from landscape.package.reporter import find_reporter_command


class ReleaseUpgraderConfiguration(PackageTaskHandlerConfiguration):
    """Specialized configuration for the Landscape package-reporter."""

    @property
    def upgrade_tool_directory(self):
        """
        The directory where the upgrade-tool files get stored and extracted.
        """
        return os.path.join(self.package_directory, "upgrade-tool")


class ReleaseUpgrader(PackageTaskHandler):
    """Perform release upgrades."""

    config_factory = ReleaseUpgraderConfiguration
    queue_name = "release-upgrader"
    lsb_release_filename = LSB_RELEASE_FILENAME

    def make_operation_result_message(self, operation_id, status, text, code):
        """Convenience to create messages of type C{"operation-result"}."""
        return {"type": "operation-result",
                "operation-id": operation_id,
                "status": status,
                "result-text": text,
                "result-code": code}

    def handle_task(self, task):
        """Call the proper handler for the given C{task}."""
        message = task.data
        if message["type"] == "release-upgrade":
            return self.handle_release_upgrade(message)

    def handle_release_upgrade(self, message):
        """Fetch the upgrade-tool, verify it and run it.

        @param message: A message of type C{"release-upgrade"}.
        """
        dist = message["dist"]
        operation_id = message["operation-id"]

        lsb_release_info = parse_lsb_release(self.lsb_release_filename)

        if dist == lsb_release_info["code-name"]:

            message = self.make_operation_result_message(
                operation_id, FAILED,
                "The system is already running %s." % dist, 1)

            logging.info("Queuing message with release upgrade failure to "
                         "exchange urgently.")

            return self._broker.send_message(message, True)

        tarball_url = message["upgrade-tool-tarball-url"]
        signature_url = message["upgrade-tool-signature-url"]
        directory = self._config.upgrade_tool_directory
        tarball_filename = url_to_filename(tarball_url,
                                           directory=directory)
        signature_filename = url_to_filename(signature_url,
                                             directory=directory)

        result = self.fetch(tarball_url, signature_url)
        result.addCallback(lambda x: self.verify(tarball_filename,
                                                 signature_filename))
        result.addCallback(lambda x: self.extract(tarball_filename))
        result.addCallback(lambda x: self.upgrade(dist, operation_id))
        result.addCallback(lambda x: self.finish())
        result.addErrback(self.abort, operation_id)
        return result

    def fetch(self, tarball_url, signature_url):
        """Fetch the upgrade-tool files.

        @param tarball_url: The upgrade-tool tarball URL.
        @param signature_url: The upgrade-tool signature URL.
        """
        if not os.path.exists(self._config.upgrade_tool_directory):
            os.mkdir(self._config.upgrade_tool_directory)

        result = fetch_to_files([tarball_url, signature_url],
                                self._config.upgrade_tool_directory,
                                logger=logging.warning)

        def log_success(ignored):
            logging.info("Successfully fetched upgrade-tool files")

        def log_failure(failure):
            logging.warning("Couldn't fetch all upgrade-tool files")
            return failure

        result.addCallback(log_success)
        result.addErrback(log_failure)
        return result

    def verify(self, tarball_filename, signature_filename):
        """Verify the upgrade-tool tarball against its signature.

        @param tarball_filename: The filename of the upgrade-tool tarball.
        @param signature_filename: The filename of the tarball signature.
        """
        result = gpg_verify(tarball_filename, signature_filename)

        def log_success(ignored):
            logging.info("Successfully verified upgrade-tool tarball")

        def log_failure(failure):
            logging.warning("Invalid signature for upgrade-tool tarball: %s"
                            % str(failure.value))
            return failure

        result.addCallback(log_success)
        result.addErrback(log_failure)
        return result

    def extract(self, tarball_filename):
        """Extract the upgrade-tool tarball.

        @param tarball_filename: The filename of the upgrade-tool tarball.
        """
        tf = tarfile.open(tarball_filename, "r:gz")
        tf.extractall(path=self._config.upgrade_tool_directory)
        return succeed(None)

    def upgrade(self, dist, operation_id):
        """Run the upgrade-tool command and send a report of the results.

        @param dist: The code-name of the release to upgrade to.
        @param operation_id: The activity id for this task.
        """
        upgrade_tool_directory = self._config.upgrade_tool_directory
        upgrade_tool_filename = os.path.join(upgrade_tool_directory, dist)
        args = ("--frontend", "DistUpgradeViewNonInteractive")
        result = getProcessOutputAndValue(upgrade_tool_filename, args=args,
                                          env=os.environ,
                                          path=upgrade_tool_directory)

        def send_operation_result((out, err, code)):
            if code == 0:
                status = SUCCEEDED
            else:
                status = FAILED
            message = self.make_operation_result_message(
                operation_id, status, "%s%s" % (out, err), code)
            logging.info("Queuing message with release upgrade results to "
                         "exchange urgently.")
            return self._broker.send_message(message, True)

        result.addCallback(send_operation_result)
        return result

    def finish(self):
        """Clean-up the upgrade-tool files and report about package changes."""
        shutil.rmtree(self._config.upgrade_tool_directory)

        if os.getuid() == 0:
            os.setgid(grp.getgrnam("landscape").gr_gid)
            os.setuid(pwd.getpwnam("landscape").pw_uid)

        reporter = find_reporter_command()

        # Force a smart-update run, because the sources.list has changed
        args = ["--force-smart-update"]

        if self._config.config is not None:
            args.append("--config=%s" % self._config.config)

        result = getProcessOutputAndValue(reporter, args=args, path=None)
        return result

    def abort(self, failure, operation_id):
        """Abort the task reporting details about the failure."""

        message = self.make_operation_result_message(
            operation_id, FAILED, "%s" % str(failure.value), 1)

        logging.info("Queuing message with release upgrade failure to "
                     "exchange urgently.")

        return self._broker.send_message(message, True)


def find_release_upgrader_command():
    """Return the path to the landscape-release-upgrader script."""
    dirname = os.path.dirname(os.path.abspath(sys.argv[0]))
    return os.path.join(dirname, "landscape-release-upgrader")


def main(args):
    if os.getpgrp() != os.getpid():
        os.setsid()
    return run_task_handler(ReleaseUpgrader, args)
