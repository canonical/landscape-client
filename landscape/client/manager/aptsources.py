import glob
import os
import pwd
import grp
import shutil
import tempfile

from twisted.internet.defer import succeed

from landscape.lib.twisted_util import spawn_process

from landscape.client.manager.plugin import ManagerPlugin
from landscape.client.package.reporter import find_reporter_command


class ProcessError(Exception):
    """Exception raised when running a process fails."""


class AptSources(ManagerPlugin):
    """A plugin managing sources.list content."""

    SOURCES_LIST = "/etc/apt/sources.list"
    SOURCES_LIST_D = "/etc/apt/sources.list.d"

    def register(self, registry):
        super(AptSources, self).register(registry)
        registry.register_message("apt-sources-replace",
                                  self._handle_repositories)

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
            raise ProcessError("%s\n%s" % (out, err))

    def _handle_process_failure(self, failure):
        """
        Turn a signaled process command to a C{ProcessError}.
        """
        if not failure.check(ProcessError):
            out, err, signal = failure.value.args
            raise ProcessError("%s\n%s" % (out, err))
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
        for key in message["gpg-keys"]:
            fd, path = tempfile.mkstemp()
            os.close(fd)
            with open(path, "w") as key_file:
                key_file.write(key)
            deferred.addCallback(
                lambda ignore, path=path:
                    self._run_process("/usr/bin/apt-key", ["add", path]))
            deferred.addCallback(self._handle_process_error)
            deferred.addBoth(self._remove_and_continue, path)
        deferred.addErrback(self._handle_process_failure)
        deferred.addCallback(self._handle_sources, message["sources"])
        return self.call_with_operation_result(message, lambda: deferred)

    def _handle_sources(self, ignored, sources):
        """Handle sources repositories."""
        saved_sources = "{}.save".format(self.SOURCES_LIST)
        if sources:
            fd, path = tempfile.mkstemp()
            os.close(fd)

            with open(path, "w") as new_sources:
                new_sources.write(
                    "# Landscape manages repositories for this computer\n"
                    "# Original content of sources.list can be found in "
                    "sources.list.save\n")

            original_stat = os.stat(self.SOURCES_LIST)
            if not os.path.isfile(saved_sources):
                shutil.move(self.SOURCES_LIST, saved_sources)
            shutil.move(path, self.SOURCES_LIST)
            os.chmod(self.SOURCES_LIST, original_stat.st_mode)
            os.chown(self.SOURCES_LIST, original_stat.st_uid,
                     original_stat.st_gid)
        else:
            # Re-instate original sources
            if os.path.isfile(saved_sources):
                shutil.move(saved_sources, self.SOURCES_LIST)

        for filename in glob.glob(os.path.join(self.SOURCES_LIST_D, "*.list")):
            shutil.move(filename, "%s.save" % filename)

        for source in sources:
            filename = os.path.join(self.SOURCES_LIST_D,
                                    "landscape-%s.list" % source["name"])
            # Servers send unicode, but an upgrade from python2 can get bytes
            # from stored messages, so we need to handle both.
            is_unicode = isinstance(source["content"], type(u""))
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
            args.append("--config=%s" % self.registry.config.config)

        if os.getuid() == 0:
            uid = pwd.getpwnam("landscape").pw_uid
            gid = grp.getgrnam("landscape").gr_gid
        else:
            uid = None
            gid = None
        return self._run_process(reporter, args, uid=uid, gid=gid)
