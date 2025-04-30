import glob
import grp
import os
import pwd
import shutil
import tempfile
import uuid

from twisted.internet.defer import succeed

from landscape.client import GROUP
from landscape.client import USER
from landscape.client.manager.plugin import ManagerPlugin
from landscape.client.package.reporter import find_reporter_command
from landscape.constants import FALSE_VALUES
from landscape.lib.twisted_util import spawn_process


class ProcessError(Exception):
    """Exception raised when running a process fails."""


class AptSources(ManagerPlugin):
    """A plugin managing sources.list content."""

    SOURCES_LIST = "/etc/apt/sources.list"
    SOURCES_LIST_D = "/etc/apt/sources.list.d"
    TRUSTED_GPG_D = "/etc/apt/trusted.gpg.d"

    """
    Valid file patterns for one-line and Deb822-style sources, respectively.
    """
    SOURCES_LIST_D_FILE_PATTERNS = ["*.list", "*.sources"]

    def register(self, registry):
        super().register(registry)
        registry.register_message(
            "apt-sources-replace",
            self._handle_repositories,
        )

    def _run_process(self, command, args, uid=None, gid=None):
        """
        Run the process in an asynchronous fashion, to be overriden in tests.
        """
        return spawn_process(command, args, uid=uid, gid=gid)

    def _handle_process_error(self, result):
        """
        Turn a failed process command (code != 0) to a C{ProcessError}.
        """
        out, err, code = result
        if code:
            raise ProcessError(f"{out}\n{err}")

    def _handle_process_failure(self, failure):
        """
        Turn a signaled process command to a C{ProcessError}.
        """
        if not failure.check(ProcessError):
            out, err, signal = failure.value.args
            raise ProcessError(f"{out}\n{err}")
        else:
            return failure

    def _remove_and_continue(self, passthrough, path):
        """
        Remove the temporary file created for the process, and forward the
        result.
        """
        os.unlink(path)
        return passthrough

    def _handle_repositories(self, message):
        """
        Handle a list of repositories to set on the machine.

        The format is the following:

        {"sources": [
          {"name": "repository-name",
           "content":
              b"deb http://archive.ubuntu.com/ubuntu/ maverick main\n"
              b"deb-src http://archive.ubuntu.com/ubuntu/ maverick main"}
          {"name": "repository-name-dev",
           "content":
              b"deb http://archive.ubuntu.com/ubuntu/ maverick universe\n"
              b"deb-src http://archive.ubuntu.com/ubuntu/ maverick universe"}],
         "gpg-keys": ["-----BEGIN PGP PUBLIC KEY BLOCK-----\n"
                      "XXXX"
                      "-----END PGP PUBLIC KEY BLOCK-----",
                      "-----BEGIN PGP PUBLIC KEY BLOCK-----\n"
                      "YYY"
                      "-----END PGP PUBLIC KEY BLOCK-----"]}
        """
        deferred = succeed(None)
        prefix = "landscape-server-mirror"
        for key in message["gpg-keys"]:
            filename = prefix + str(uuid.uuid4()) + ".asc"
            key_path = os.path.join(self.TRUSTED_GPG_D, filename)
            with open(key_path, "w") as key_file:
                key_file.write(key)
        deferred.addErrback(self._handle_process_failure)
        deferred.addCallback(self._handle_sources, message["sources"])
        return self.call_with_operation_result(message, lambda: deferred)

    def _handle_sources(self, ignored, sources):
        """
        Replaces `SOURCES_LIST` with a Landscape-managed version and moves the
        original to a ".save" file.

        Configurably does the same with files in `SOURCES_LIST_D`.
        """

        saved_sources = f"{self.SOURCES_LIST}.save"

        if sources:
            fd, path = tempfile.mkstemp()
            os.close(fd)

            with open(path, "w") as new_sources:
                new_sources.write(
                    "# Landscape manages repositories for this computer\n"
                    "# Original content of sources.list can be found in "
                    "sources.list.save\n",
                )

            original_stat = os.stat(self.SOURCES_LIST)
            if not os.path.isfile(saved_sources):
                shutil.move(self.SOURCES_LIST, saved_sources)
            shutil.move(path, self.SOURCES_LIST)
            os.chmod(self.SOURCES_LIST, original_stat.st_mode)
            os.chown(
                self.SOURCES_LIST,
                original_stat.st_uid,
                original_stat.st_gid,
            )
        else:
            # Re-instate original sources
            if os.path.isfile(saved_sources):
                shutil.move(saved_sources, self.SOURCES_LIST)

        manage_sources_list_d = getattr(
            self.registry.config,
            "manage_sources_list_d",
            True,
        )

        if manage_sources_list_d not in FALSE_VALUES:
            for pattern in self.SOURCES_LIST_D_FILE_PATTERNS:
                filenames = glob.glob(
                    os.path.join(self.SOURCES_LIST_D, pattern)
                )
                for filename in filenames:
                    shutil.move(filename, f"{filename}.save")

        for source in sources:
            filename = os.path.join(
                self.SOURCES_LIST_D,
                f"landscape-{source['name']}.list",
            )
            # Servers send unicode, but an upgrade from python2 can get bytes
            # from stored messages, so we need to handle both.
            is_unicode = isinstance(source["content"], type(""))
            with open(filename, ("w" if is_unicode else "wb")) as sources_file:
                sources_file.write(source["content"])
            os.chmod(filename, 0o644)
        return self._run_reporter().addCallback(lambda ignored: None)

    def _run_reporter(self):
        """Once the repositories are modified, trigger a reporter run."""
        reporter = find_reporter_command(self.registry.config)

        # Force an apt-update run, because the sources.list has changed
        args = ["--force-apt-update"]

        if self.registry.config.config is not None:
            args.append(f"--config={self.registry.config.config}")

        if os.getuid() == 0:
            uid = pwd.getpwnam(USER).pw_uid
            gid = grp.getgrnam(GROUP).gr_gid
        else:
            uid = None
            gid = None
        return self._run_process(reporter, args, uid=uid, gid=gid)
