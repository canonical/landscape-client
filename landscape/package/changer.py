import logging
import base64
import time
import sys
import os
import pwd
import grp

from twisted.internet.defer import fail

from landscape.package.reporter import find_reporter_command
from landscape.package.taskhandler import (
    PackageTaskHandler, PackageTaskHandlerConfiguration, run_task_handler)


SUCCESS_RESULT = 1
ERROR_RESULT = 100
DEPENDENCY_ERROR_RESULT = 101


# The amount of time to wait while we have unknown package data before
# reporting an error to the server in response to an operation.
# The two common cases of this are:
# 1.  The server requested an operation that we've decided requires some
# dependencies, but we don't know the package ID of those dependencies.  It
# should only take a bit more than 10 minutes for that to be resolved by the
# package reporter.
# 2.  We lost some package data, for example by a deb archive becoming
# inaccessible for a while.  The earliest we can reasonably assume that to be
# resolved is in 60 minutes, when the smart cronjob runs again.

# So we'll give the problem one chance to resolve itself, by only waiting for
# one run of smart update.
UNKNOWN_PACKAGE_DATA_TIMEOUT = 70 * 60


class UnknownPackageData(Exception):
    """Raised when an ID or a hash isn't known."""


class PackageChangerConfiguration(PackageTaskHandlerConfiguration):
    """Specialized configuration for the Landscape package-changer."""

    @property
    def debs_path(self):
        """The path to the directory we store server-generated debs in."""
        return os.path.join(self.package_directory, "debs")


class PackageChanger(PackageTaskHandler):
    """Install, remove and upgrade packages."""

    config_factory = PackageChangerConfiguration

    queue_name = "changer"

    def run(self):
        task1 = self._store.get_next_task(self.queue_name)

        def finished(result):
            task2 = self._store.get_next_task(self.queue_name)
            if task1 and task1.id != (task2 and task2.id):
                # In order to let the reporter run smart-update cleanly,
                # we have to deinitialize Smart, so that the write lock
                # gets released
                self._facade.deinit()
                if os.getuid() == 0:
                    os.setgid(grp.getgrnam("landscape").gr_gid)
                    os.setuid(pwd.getpwnam("landscape").pw_uid)
                command = find_reporter_command()
                if self._config.config is not None:
                    command += " -c %s" % self._config.config
                os.system(command)

        result = self.use_hash_id_db()
        result.addCallback(lambda x: self.handle_tasks())
        result.addCallback(finished)

        return result

    def handle_tasks(self):
        result = super(PackageChanger, self).handle_tasks()
        return result.addErrback(self._warn_about_unknown_data)

    def handle_task(self, task):
        """
        @param task: A L{PackageTask} carrying a message of
            type C{"change-packages"}.
        """
        message = task.data
        if message["type"] == "change-packages":
            result = self._handle_change_packages(message)
            return result.addErrback(self._check_expired_unknown_data, task)

    def _warn_about_unknown_data(self, failure):
        failure.trap(UnknownPackageData)
        logging.warning("Package data not yet synchronized with server (%r)" %
                        failure.value.args[0])

    def _check_expired_unknown_data(self, failure, task):
        failure.trap(UnknownPackageData)
        if task.timestamp < time.time() - UNKNOWN_PACKAGE_DATA_TIMEOUT:
            self._warn_about_unknown_data(failure)
            message = {"type": "change-packages-result",
                       "operation-id": task.data["operation-id"],
                       "result-code": ERROR_RESULT,
                       "result-text": "Package data has changed. "
                                      "Please retry the operation."}
            return self._broker.send_message(message)
        else:
            return failure

    def _create_deb_dir_channel(self, debs):
        """Add a C{deb-dir} channel sporting the given C{debs}.

        @param debs: A list of 3-tuples of the form (hash, id, deb), containing
            the hash, the id and the content of a Debian package.
        """

        debs_path = self._config.debs_path

        for existing_deb_path in os.listdir(debs_path):
            # Clean up the debs we wrote in former runs
            os.remove(os.path.join(debs_path, existing_deb_path))

        for hash, id, deb in debs:

            # Write the deb to disk
            fd = open(os.path.join(debs_path, "%d.deb" % id), "w")
            fd.write(base64.decodestring(deb))
            fd.close()

            # Add the hash->id mapping for the package, so the packages can
            # be properly installed and reported.
            self._store.set_hash_ids({hash: id})

        self._facade.add_channel_deb_dir(debs_path)

    def _handle_change_packages(self, message):

        if message.get("debs"):
            self._create_deb_dir_channel(message["debs"])

        self.ensure_channels_reloaded()

        self._facade.reset_marks()

        if message.get("upgrade-all"):
            for package in self._facade.get_packages():
                if package.installed:
                    self._facade.mark_upgrade(package)

        for field, mark_func in [("install", self._facade.mark_install),
                                 ("remove", self._facade.mark_remove)]:
            for id in message.get(field, ()):
                hash = self._store.get_id_hash(id)
                if hash is None:
                    return fail(UnknownPackageData(id))
                package = self._facade.get_package_by_hash(hash)
                if package is None:
                    return fail(UnknownPackageData(hash))
                mark_func(package)

        message = {"type": "change-packages-result",
                   "operation-id": message.get("operation-id")}

        # Delay importing these so that we don't import Smart unless
        # we really need to.
        from landscape.package.facade import (
            DependencyError, TransactionError, SmartError)

        result = None
        try:
            result = self._facade.perform_changes()
        except (TransactionError, SmartError), exception:
            result_code = ERROR_RESULT
            result = exception.args[0]
        except DependencyError, exception:
            result_code = DEPENDENCY_ERROR_RESULT
            installs = []
            removals = []
            for package in exception.packages:
                hash = self._facade.get_package_hash(package)
                id = self._store.get_hash_id(hash)
                if id is None:
                    # Will have to wait until the server lets us know about
                    # this id.
                    return fail(UnknownPackageData(hash))
                if package.installed:
                    # Package currently installed. Must remove it.
                    removals.append(id)
                else:
                    # Package currently available. Must install it.
                    installs.append(id)
            if installs:
                installs.sort()
                message["must-install"] = installs
            if removals:
                removals.sort()
                message["must-remove"] = removals
        else:
            result_code = SUCCESS_RESULT

        message["result-code"] = result_code
        if result is not None:
            message["result-text"] = result

        logging.info("Queuing message with change package results to "
                     "exchange urgently.")
        return self._broker.send_message(message, True)

    @staticmethod
    def find_command():
        return find_changer_command()


def find_changer_command():
    dirname = os.path.dirname(os.path.abspath(sys.argv[0]))
    return os.path.join(dirname, "landscape-package-changer")


def main(args):
    if os.getpgrp() != os.getpid():
        os.setsid()
    return run_task_handler(PackageChanger, args)
