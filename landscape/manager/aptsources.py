import glob
import os
import shutil
import tempfile

from twisted.internet.defer import succeed
from twisted.internet.utils import getProcessOutputAndValue

from landscape.manager.plugin import ManagerPlugin, SUCCEEDED, FAILED
from landscape.package.reporter import find_reporter_command


class ProcessError(Exception):
    """Exception raised when running a process fails."""


class AptSources(ManagerPlugin):
    """A plugin managing sources.list content."""

    SOURCES_LIST = "/etc/apt/sources.list"
    SOURCES_LIST_D = "/etc/apt/sources.list.d"

    def register(self, registry):
        super(AptSources, self).register(registry)
        registry.register_message(
            "apt-sources-replace", self._wrap_handle_repositories)

    def run_process(self, command, args):
        """
        Run the process in an asynchronous fashion, to be overriden in tests.
        """
        return getProcessOutputAndValue(command, args)

    def _wrap_handle_repositories(self, message):
        """
        Wrap C{_handle_repositories} to generate an activity result based on
        the returned value.
        """
        deferred = self._handle_repositories(message)

        operation_result = {"type": "operation-result",
                            "operation-id": message["operation-id"]}

        def success(ignored):
            operation_result["status"] = SUCCEEDED
            return operation_result

        def fail(failure):
            operation_result["status"] = FAILED
            text = "%s: %s" % (failure.type.__name__, failure.value)
            operation_result["result-text"] = text
            return operation_result

        deferred.addCallbacks(success, fail)
        deferred.addBoth(lambda result:
                         self.manager.broker.send_message(result, urgent=True))

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
            out, err, signal = failure.value
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
              "deb http://archive.ubuntu.com/ubuntu/ maverick main\n\
              "deb-src http://archive.ubuntu.com/ubuntu/ maverick main"}
          {"name": "repository-name-dev",
           "content":
              "deb http://archive.ubuntu.com/ubuntu/ maverick universe\n\
              "deb-src http://archive.ubuntu.com/ubuntu/ maverick universe"}],
         "gpg-keys": ["-----BEGIN PGP PUBLIC KEY BLOCK-----\n\
                      XXXX
                      -----END PGP PUBLIC KEY BLOCK-----",
                      "-----BEGIN PGP PUBLIC KEY BLOCK-----\n\
                      YYY
                      -----END PGP PUBLIC KEY BLOCK-----"]}
        """
        deferred = succeed(None)
        for key in message["gpg-keys"]:
            fd, path = tempfile.mkstemp()
            os.close(fd)
            key_file = file(path, "w")
            key_file.write(key)
            key_file.close()
            deferred.addCallback(
                lambda ignore, path=path:
                    self.run_process("/usr/bin/apt-key", ["add", path]))
            deferred.addCallback(self._handle_process_error)
            deferred.addBoth(self._remove_and_continue, path)
        deferred.addErrback(self._handle_process_failure)
        return deferred.addCallback(
            self._handle_sources, message["sources"])

    def _handle_sources(self, ignored, sources):
        """Handle sources repositories."""
        fd, path = tempfile.mkstemp()
        os.close(fd)
        new_sources = file(path, "w")
        for line in file(self.SOURCES_LIST):
            stripped_line = line.strip()
            if not stripped_line or stripped_line.startswith("#"):
                new_sources.write(line)
            else:
                new_sources.write("#%s" % line)
        new_sources.close()

        stat = os.stat(self.SOURCES_LIST)
        os.chmod(path, stat.st_mode)

        shutil.move(path, self.SOURCES_LIST)

        for filename in glob.glob(os.path.join(self.SOURCES_LIST_D, "*.list")):
            os.rename(filename, "%s.save" % filename)

        for source in sources:
            filename = os.path.join(self.SOURCES_LIST_D,
                                    "landscape-%s.list" % source["name"])
            sources_file = file(filename, "w")
            sources_file.write(source["content"])
            sources_file.close()
        return self._run_reporter()

    def _run_reporter(self):
        """Once the repositories are modified, trigger a reporter run."""
        reporter = find_reporter_command()

        # Force a smart-update run, because the sources.list has changed
        args = ["--force-smart-update"]

        if self.registry.config.config is not None:
            args.append("--config=%s" % self.registry.config.config)
        return self.run_process(reporter, args)
