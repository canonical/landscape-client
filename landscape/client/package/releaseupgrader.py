import grp
import io
import logging
import os
import pwd
import shutil
import tarfile

from twisted.internet.defer import succeed

from landscape.lib.config import get_bindir
from landscape.lib.fetch import url_to_filename, fetch_to_files
from landscape.lib.lsb_release import parse_lsb_release, LSB_RELEASE_FILENAME
from landscape.lib.gpg import gpg_verify
from landscape.lib.fs import read_text_file
from landscape.client.package.taskhandler import (
    PackageTaskHandlerConfiguration, PackageTaskHandler, run_task_handler)
from landscape.lib.twisted_util import spawn_process
from landscape.client.manager.manager import SUCCEEDED, FAILED
from landscape.client.package.reporter import find_reporter_command


class ReleaseUpgraderConfiguration(PackageTaskHandlerConfiguration):
    """Specialized configuration for the Landscape release-upgrader."""

    @property
    def upgrade_tool_directory(self):
        """
        The directory where the upgrade-tool files get stored and extracted.
        """
        return os.path.join(self.package_directory, "upgrade-tool")


class ReleaseUpgrader(PackageTaskHandler):
    """Perform release upgrades.

    @cvar config_factory: The configuration class to use to build configuration
        objects to be passed to our constructor.
    @cvar queue_name: The queue we pick tasks from.
    @cvar lsb_release_filename: The path to the LSB data on the file system.
    @cvar landscape_ppa_url: The URL of the Landscape PPA, if it is present
        in the computer's sources.list it won't be commented out.
    @cvar logs_directory: Path to the directory holding the upgrade-tool logs.
    @cvar logs_limit: When reporting upgrade-tool logs to the server, only the
        last C{logs_limit} characters will be sent.
    """

    config_factory = ReleaseUpgraderConfiguration
    queue_name = "release-upgrader"
    lsb_release_filename = LSB_RELEASE_FILENAME
    landscape_ppa_url = "http://ppa.launchpad.net/landscape/trunk/ubuntu/"
    logs_directory = "/var/log/dist-upgrade"
    logs_limit = 100000  # characters

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
        target_code_name = message["code-name"]
        operation_id = message["operation-id"]
        lsb_release_info = parse_lsb_release(self.lsb_release_filename)
        current_code_name = lsb_release_info["code-name"]

        if target_code_name == current_code_name:
            message = self.make_operation_result_message(
                operation_id, FAILED,
                "The system is already running %s." % target_code_name, 1)
            logging.info("Queuing message with release upgrade failure to "
                         "exchange urgently.")
            return self._send_message(message)

        tarball_url = message["upgrade-tool-tarball-url"]
        signature_url = message["upgrade-tool-signature-url"]
        allow_third_party = message.get("allow-third-party", False)
        debug = message.get("debug", False)
        directory = self._config.upgrade_tool_directory
        tarball_filename = url_to_filename(tarball_url,
                                           directory=directory)
        signature_filename = url_to_filename(signature_url,
                                             directory=directory)

        result = self.fetch(tarball_url, signature_url)
        result.addCallback(lambda x: self.verify(tarball_filename,
                                                 signature_filename))
        result.addCallback(lambda x: self.extract(tarball_filename))
        result.addCallback(lambda x: self.tweak(current_code_name))
        result.addCallback(lambda x: self.upgrade(
            target_code_name, operation_id,
            allow_third_party=allow_third_party, debug=debug))
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
        for member in tf.getmembers():
            tf.extract(member, path=self._config.upgrade_tool_directory)
        return succeed(None)

    def tweak(self, current_code_name):
        """Tweak the files of the extracted tarballs to workaround known bugs.

        @param current_code_name: The code-name of the current release.
        """
        upgrade_tool_directory = self._config.upgrade_tool_directory

        # On some releases the upgrade-tool doesn't support the allow third
        # party environment variable, so this trick is needed to make it
        # possible to upgrade against testing client packages from the
        # Landscape PPA
        mirrors_filename = os.path.join(upgrade_tool_directory,
                                        "mirrors.cfg")
        fd = open(mirrors_filename, "a")
        fd.write(self.landscape_ppa_url + "\n")
        fd.close()

        return succeed(None)

    def make_operation_result_text(self, out, err):
        """Return the operation result text to be sent to the server.

        @param out: The standard output of the upgrade-tool process.
        @param err: The standard error of the upgrade-tool process.
        @return: A text aggregating the process output, error and log files.
        """
        buf = io.StringIO()

        for label, content in [("output", out), ("error", err)]:
            if content:
                buf.write(u"=== Standard %s ===\n\n%s\n\n" % (label, content))

        for basename in sorted(os.listdir(self.logs_directory)):
            if not basename.endswith(".log"):
                continue
            filename = os.path.join(self.logs_directory, basename)
            content = read_text_file(filename, -self.logs_limit)
            buf.write(u"=== %s ===\n\n%s\n\n" % (basename, content))

        return buf.getvalue()

    def upgrade(self, code_name, operation_id, allow_third_party=False,
                debug=False):
        """Run the upgrade-tool command and send a report of the results.

        @param code_name: The code-name of the release to upgrade to.
        @param operation_id: The activity id for this task.
        @param allow_third_party: Whether to enable non-official APT repo.
        @param debug: Whether to turn on debug level logging.
        """
        # This bizarre (and apparently unused) import is a workaround for
        # LP: #1670291 -- see comments in that ticket for an explanation
        import twisted.internet.unix  # noqa: F401
        upgrade_tool_directory = self._config.upgrade_tool_directory
        upgrade_tool_filename = os.path.join(upgrade_tool_directory, code_name)
        args = ["--frontend", "DistUpgradeViewNonInteractive"]
        env = os.environ.copy()
        if allow_third_party:
            env["RELEASE_UPRADER_ALLOW_THIRD_PARTY"] = "True"
        if debug:
            env["DEBUG_UPDATE_MANAGER"] = "True"

        result = spawn_process(upgrade_tool_filename, args=args, env=env,
                               path=upgrade_tool_directory, wait_pipes=False)

        def send_operation_result(args):
            out, err, code = args
            out = out.decode("utf-8")
            err = err.decode("utf-8")

            if code == 0:
                status = SUCCEEDED
            else:
                status = FAILED
            text = self.make_operation_result_text(out, err)
            message = self.make_operation_result_message(operation_id, status,
                                                         text, code)
            logging.info("Queuing message with release upgrade results to "
                         "exchange urgently.")
            return self._send_message(message)

        result.addCallback(send_operation_result)
        return result

    def finish(self):
        """Clean-up the upgrade-tool files and report about package changes."""
        shutil.rmtree(self._config.upgrade_tool_directory)

        if os.getuid() == 0:
            uid = pwd.getpwnam("landscape").pw_uid
            gid = grp.getgrnam("landscape").gr_gid
        else:
            uid = None
            gid = None

        reporter = find_reporter_command(self._config)

        # Force an apt-update run, because the sources.list has changed
        args = ["--force-apt-update"]

        if self._config.config is not None:
            args.append("--config=%s" % self._config.config)

        return spawn_process(reporter, args=args, uid=uid, gid=gid,
                             path=os.getcwd(), env=os.environ)

    def abort(self, failure, operation_id):
        """Abort the task reporting details about the failure."""

        message = self.make_operation_result_message(
            operation_id, FAILED, "%s" % str(failure.value), 1)

        logging.info("Queuing message with release upgrade failure to "
                     "exchange urgently.")

        return self._send_message(message)

    @classmethod
    def find_command(cls, config=None):
        """Return the path to the landscape-release-upgrader script."""
        bindir = get_bindir(config)
        return os.path.join(bindir, "landscape-release-upgrader")

    def _send_message(self, message):
        """Acquire a session ID and send the given message."""
        deferred = self.get_session_id()

        def send(_):
            self._broker.send_message(message, self._session_id, True)

        deferred.addCallback(send)
        return deferred


def main(args):
    if os.getpgrp() != os.getpid():
        os.setsid()
    return run_task_handler(ReleaseUpgrader, args)
