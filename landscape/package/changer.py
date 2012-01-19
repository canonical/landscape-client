import logging
import base64
import time
import sys
import os
import pwd
import grp

from twisted.internet.defer import maybeDeferred, succeed

from landscape.constants import (
    SUCCESS_RESULT, ERROR_RESULT, DEPENDENCY_ERROR_RESULT, POLICY_STRICT,
    POLICY_ALLOW_INSTALLS, POLICY_ALLOW_ALL_CHANGES,
    UNKNOWN_PACKAGE_DATA_TIMEOUT)

from landscape.lib.fs import create_file
from landscape.package.reporter import find_reporter_command
from landscape.package.taskhandler import (
    PackageTaskHandler, PackageTaskHandlerConfiguration, PackageTaskError,
    run_task_handler)
from landscape.manager.manager import FAILED, SUCCEEDED


class UnknownPackageData(Exception):
    """Raised when an ID or a hash isn't known."""


class PackageChangerConfiguration(PackageTaskHandlerConfiguration):
    """Specialized configuration for the Landscape package-changer."""

    @property
    def binaries_path(self):
        """The path to the directory we store server-generated packages in."""
        return os.path.join(self.package_directory, "binaries")


class ChangePackagesResult(object):
    """Value object to hold the results of change packages operation.

    @ivar code: The result code of the requested changes.
    @ivar text: The output from Smart.
    @ivar installs: Possible additional packages that need to be installed
        in order to fulfill the request.
    @ivar removals: Possible additional packages that need to be removed
        in order to fulfill the request.
    """

    def __init__(self):
        self.code = None
        self.text = None
        self.installs = []
        self.removals = []


class PackageChanger(PackageTaskHandler):
    """Install, remove and upgrade packages."""

    config_factory = PackageChangerConfiguration

    queue_name = "changer"

    def run(self):
        """
        Handle our tasks and spawn the reporter if package data has changed.
        """
        if not self.update_stamp_exists():
            logging.warning("The package-reporter hasn't run yet, exiting.")
            return succeed(None)

        result = self.use_hash_id_db()
        result.addCallback(lambda x: self.handle_tasks())
        result.addCallback(lambda x: self.run_package_reporter())
        return result

    def run_package_reporter(self):
        """
        Run the L{PackageReporter} if there were successfully completed tasks.
        """
        if self.handled_tasks_count == 0:
            # Nothing was done
            return

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

    def handle_task(self, task):
        """
        @param task: A L{PackageTask} carrying a message of
            type C{"change-packages"}.
        """
        message = task.data
        if message["type"] == "change-packages":
            result = maybeDeferred(self.handle_change_packages, message)
            return result.addErrback(self.unknown_package_data_error, task)
        if message["type"] == "change-package-locks":
            return self.handle_change_package_locks(message)
        if message["type"] == "change-package-holds":
            return self.handle_change_package_holds(message)

    def unknown_package_data_error(self, failure, task):
        """Handle L{UnknownPackageData} data errors.

        If the task is older than L{UNKNOWN_PACKAGE_DATA_TIMEOUT} seconds,
        a message is sent to the server to notify the failure of the associated
        activity and the task will be removed from the queue.

        Otherwise a L{PackageTaskError} is raised and the task will be picked
        up again at the next run.
        """
        failure.trap(UnknownPackageData)
        logging.warning("Package data not yet synchronized with server (%r)" %
                        failure.value.args[0])
        if task.timestamp < time.time() - UNKNOWN_PACKAGE_DATA_TIMEOUT:
            message = {"type": "change-packages-result",
                       "operation-id": task.data["operation-id"],
                       "result-code": ERROR_RESULT,
                       "result-text": "Package data has changed. "
                                      "Please retry the operation."}
            return self._broker.send_message(message)
        else:
            raise PackageTaskError()

    def update_stamp_exists(self):
        """
        Return a boolean indicating if the update-stamp stamp file exists.
        """
        return os.path.exists(self._config.update_stamp_filename)

    def init_channels(self, binaries=()):
        """Initialize the Smart channels as needed.

        @param binaries: A possibly empty list of 3-tuples of the form
            (hash, id, deb), holding the hash, the id and the content of
            additional Debian packages that should be loaded in the channels.
        """
        binaries_path = self._config.binaries_path

        for existing_deb_path in os.listdir(binaries_path):
            # Clean up the binaries we wrote in former runs
            os.remove(os.path.join(binaries_path, existing_deb_path))

        if binaries:
            hash_ids = {}
            for hash, id, deb in binaries:
                create_file(os.path.join(binaries_path, "%d.deb" % id),
                            base64.decodestring(deb))
                hash_ids[hash] = id
            self._store.set_hash_ids(hash_ids)
            self._facade.add_channel_deb_dir(binaries_path)

        self._facade.ensure_channels_reloaded()

    def mark_packages(self, upgrade=False, install=(), remove=(), reset=True):
        """Mark packages for upgrade, installation or removal.

        @param upgrade: If C{True} mark all installed packages for upgrade.
        @param install: A list of package ids to be marked for installation.
        @param remove: A list of package ids to be marked for removal.
        @param reset: If C{True} all existing marks will be reset.
        """
        if reset:
            self._facade.reset_marks()

        if upgrade:
            self._facade.mark_global_upgrade()

        for ids, mark_func in [(install, self._facade.mark_install),
                                 (remove, self._facade.mark_remove)]:
            for id in ids:
                hash = self._store.get_id_hash(id)
                if hash is None:
                    raise UnknownPackageData(id)
                package = self._facade.get_package_by_hash(hash)
                if package is None:
                    raise UnknownPackageData(hash)
                mark_func(package)

    def change_packages(self, policy):
        """Perform the requested changes.

        @param policy: A value indicating what to do in case additional changes
            beside the ones explicitly requested are needed in order to fulfill
            the request (see L{complement_changes}).
        @return: A L{ChangePackagesResult} holding the details about the
            outcome of the requested changes.
        """
        # Delay importing these so that we don't import Smart unless
        # we really need to.
        from landscape.package.facade import (
            DependencyError, TransactionError, SmartError)

        result = ChangePackagesResult()
        count = 0
        while result.code is None:
            count += 1
            try:
                result.text = self._facade.perform_changes()
            except (TransactionError, SmartError), exception:
                result.code = ERROR_RESULT
                result.text = exception.args[0]
            except DependencyError, exception:
                for package in exception.packages:
                    hash = self._facade.get_package_hash(package)
                    id = self._store.get_hash_id(hash)
                    if id is None:
                        # Will have to wait until the server lets us know about
                        # this id.
                        raise UnknownPackageData(hash)
                    if self._facade.is_package_installed(package):
                        # Package currently installed. Must remove it.
                        result.removals.append(id)
                    else:
                        # Package currently available. Must install it.
                        result.installs.append(id)
                if count == 1 and self.may_complement_changes(result, policy):
                    # Mark all missing packages and try one more iteration
                    self.mark_packages(install=result.installs,
                                       remove=result.removals, reset=False)
                else:
                    result.code = DEPENDENCY_ERROR_RESULT
            else:
                result.code = SUCCESS_RESULT

        return result

    def may_complement_changes(self, result, policy):
        """Decide whether or not we should complement the given changes.

        @param result: A L{PackagesResultObject} holding the details about the
            missing dependencies needed to complement the given changes.
        @param policy: It can be one of the following values:
            - L{POLICY_STRICT}, no additional packages will be marked.
            - L{POLICY_ALLOW_INSTALLS}, if only additional installs are missing
                they will be marked for installation.
        @return: A boolean indicating whether the given policy allows to
            complement the changes and retry.
        """
        if policy == POLICY_ALLOW_ALL_CHANGES:
            return True
        if policy == POLICY_ALLOW_INSTALLS:
            if result.installs and not result.removals:
                return True
        return False

    def handle_change_packages(self, message):
        """Handle a C{change-packages} message."""

        self.init_channels(message.get("binaries", ()))
        self.mark_packages(message.get("upgrade-all", False),
                           message.get("install", ()),
                           message.get("remove", ()))

        result = self.change_packages(message.get("policy", POLICY_STRICT))

        response = {"type": "change-packages-result",
                   "operation-id": message.get("operation-id")}

        response["result-code"] = result.code
        if result.text:
            response["result-text"] = result.text
        if result.installs:
            response["must-install"] = sorted(result.installs)
        if result.removals:
            response["must-remove"] = sorted(result.removals)

        logging.info("Queuing response with change package results to "
                     "exchange urgently.")
        return self._broker.send_message(response, True)

    def handle_change_package_locks(self, message):
        """Handle a C{change-package-locks} message.

        Create and delete package locks as requested by the given C{message}.
        """

        for lock in message.get("create", ()):
            self._facade.set_package_lock(*lock)
        for lock in message.get("delete", ()):
            self._facade.remove_package_lock(*lock)
        self._facade.save_config()

        response = {"type": "operation-result",
                    "operation-id": message.get("operation-id"),
                    "status": SUCCEEDED,
                    "result-text": "Package locks successfully changed.",
                    "result-code": 0}

        logging.info("Queuing message with change package locks results to "
                     "exchange urgently.")
        return self._broker.send_message(response, True)

    def handle_change_package_holds(self, message):
        """Handle a C{change-package-holds} message.

        Create and delete package holds as requested by the given C{message}.
        """
        not_installed = set()
        holds_to_create = message.get("create", [])
        for name in holds_to_create:
            versions = self._facade.get_packages_by_name(name)
            if not versions or not versions[0].package.installed:
                not_installed.add(name)
        if not_installed:
            response = {
                "type": "operation-result",
                "operation-id": message.get("operation-id"),
                "status": FAILED,
                "result-text": "Package holds not added, since the following" +
                               " packages are not installed: %s" % (
                                   ", ".join(sorted(not_installed))),
                "result-code": 1}
        else:
            for hold in holds_to_create:
                self._facade.set_package_hold(hold)
            self._facade.reload_channels()
            for hold in message.get("delete", []):
                self._facade.remove_package_hold(hold)
            self._facade.reload_channels()

            response = {"type": "operation-result",
                        "operation-id": message.get("operation-id"),
                        "status": SUCCEEDED,
                        "result-text": "Package holds successfully changed.",
                        "result-code": 0}

        logging.info("Queuing message with change package holds results to "
                     "exchange urgently.")
        return self._broker.send_message(response, True)

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
