import logging
import time
import os
import pwd
import grp

from twisted.internet.defer import maybeDeferred, succeed
from twisted.internet import reactor

from landscape.constants import (
    SUCCESS_RESULT, ERROR_RESULT, DEPENDENCY_ERROR_RESULT,
    POLICY_STRICT, POLICY_ALLOW_INSTALLS, POLICY_ALLOW_ALL_CHANGES,
    UNKNOWN_PACKAGE_DATA_TIMEOUT)

from landscape.lib.config import get_bindir
from landscape.lib import base64
from landscape.lib.fs import create_binary_file
from landscape.lib.log import log_failure
from landscape.client.package.reporter import find_reporter_command
from landscape.client.package.taskhandler import (
    PackageTaskHandler, PackageTaskHandlerConfiguration, PackageTaskError,
    run_task_handler)
from landscape.client.manager.manager import FAILED
from landscape.client.manager.shutdownmanager import ShutdownProcessProtocol
from landscape.client.monitor.rebootrequired import REBOOT_REQUIRED_FILENAME


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
    @ivar text: The output from Apt.
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

    def __init__(self, store, facade, remote, config, process_factory=reactor,
                 landscape_reactor=None,
                 reboot_required_filename=REBOOT_REQUIRED_FILENAME):
        super(PackageChanger, self).__init__(
            store, facade, remote, config, landscape_reactor)
        self._process_factory = process_factory
        if landscape_reactor is None:  # For testing purposes.
            from landscape.client.reactor import LandscapeReactor
            self._landscape_reactor = LandscapeReactor()
        else:
            self._landscape_reactor = landscape_reactor
        self.reboot_required_filename = reboot_required_filename

    def run(self):
        """
        Handle our tasks and spawn the reporter if package data has changed.
        """
        if not self.update_stamp_exists():
            logging.warning("The package-reporter hasn't run yet, exiting.")
            return succeed(None)

        result = self.use_hash_id_db()
        result.addCallback(lambda x: self.get_session_id())
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

        if os.getuid() == 0:
            os.setgid(grp.getgrnam("landscape").gr_gid)
            os.setuid(pwd.getpwnam("landscape").pw_uid)
        command = find_reporter_command(self._config)
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
            return self._broker.send_message(message, self._session_id)
        else:
            raise PackageTaskError()

    def update_stamp_exists(self):
        """
        Return a boolean indicating if the update-stamp stamp file exists.
        """
        return (os.path.exists(self._config.update_stamp_filename) or
                os.path.exists(self.update_notifier_stamp))

    def _clear_binaries(self):
        """Remove any binaries and its associated channel."""
        binaries_path = self._config.binaries_path

        for existing_deb_path in os.listdir(binaries_path):
            # Clean up the binaries we wrote in former runs
            os.remove(os.path.join(binaries_path, existing_deb_path))
        self._facade.clear_channels()

    def init_channels(self, binaries=()):
        """Initialize the Apt channels as needed.

        @param binaries: A possibly empty list of 3-tuples of the form
            (hash, id, deb), holding the hash, the id and the content of
            additional Debian packages that should be loaded in the channels.
        """
        binaries_path = self._config.binaries_path

        # Clean up the binaries we wrote in former runs
        self._clear_binaries()

        if binaries:
            hash_ids = {}
            for hash, id, deb in binaries:
                create_binary_file(os.path.join(binaries_path, "%d.deb" % id),
                                   base64.decodebytes(deb))
                hash_ids[hash] = id
            self._store.set_hash_ids(hash_ids)
            self._facade.add_channel_deb_dir(binaries_path)
            self._facade.reload_channels(force_reload_binaries=True)

        self._facade.ensure_channels_reloaded()

    def mark_packages(self, upgrade=False, install=(), remove=(),
                      hold=(), remove_hold=(), reset=True):
        """Mark packages for upgrade, installation or removal.

        @param upgrade: If C{True} mark all installed packages for upgrade.
        @param install: A list of package ids to be marked for installation.
        @param remove: A list of package ids to be marked for removal.
        @param hold: A list of package ids to be marked for holding.
        @param remove_hold: A list of package ids to be marked to have a hold
                            removed.
        @param reset: If C{True} all existing marks will be reset.
        """
        if reset:
            self._facade.reset_marks()

        if upgrade:
            self._facade.mark_global_upgrade()

        for mark_function, mark_ids in [
                (self._facade.mark_install, install),
                (self._facade.mark_remove, remove),
                (self._facade.mark_hold, hold),
                (self._facade.mark_remove_hold, remove_hold)]:
            for mark_id in mark_ids:
                hash = self._store.get_id_hash(mark_id)
                if hash is None:
                    raise UnknownPackageData(mark_id)
                package = self._facade.get_package_by_hash(hash)
                if package is None:
                    raise UnknownPackageData(hash)
                mark_function(package)

    def change_packages(self, policy):
        """Perform the requested changes.

        @param policy: A value indicating what to do in case additional changes
            beside the ones explicitly requested are needed in order to fulfill
            the request (see L{complement_changes}).
        @return: A L{ChangePackagesResult} holding the details about the
            outcome of the requested changes.
        """
        # Delay importing these so that we don't import Apt unless
        # we really need to.
        from landscape.lib.apt.package.facade import (
                DependencyError, TransactionError)

        result = ChangePackagesResult()
        count = 0
        while result.code is None:
            count += 1
            try:
                result.text = self._facade.perform_changes()
            except TransactionError as exception:
                result.code = ERROR_RESULT
                result.text = exception.args[0]
            except DependencyError as exception:
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

        if result.code == SUCCESS_RESULT and result.text is None:
            result.text = 'No changes required; all changes already performed'
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
            # Note that package upgrades are one removal and one install, so
            # are not allowed here.
            if result.installs and not result.removals:
                return True
        return False

    def handle_change_packages(self, message):
        """Handle a C{change-packages} message."""

        self.init_channels(message.get("binaries", ()))
        self.mark_packages(upgrade=message.get("upgrade-all", False),
                           install=message.get("install", ()),
                           remove=message.get("remove", ()),
                           hold=message.get("hold", ()),
                           remove_hold=message.get("remove-hold", ()))
        result = self.change_packages(message.get("policy", POLICY_STRICT))
        self._clear_binaries()

        needs_reboot = (message.get("reboot-if-necessary") and
                        os.path.exists(self.reboot_required_filename))
        stop_exchanger = needs_reboot

        deferred = self._send_response(None, message, result,
                                       stop_exchanger=stop_exchanger)
        if needs_reboot:
            # Reboot the system after a short delay after the response has been
            # sent to the broker. This is to allow the broker time to save the
            # message to its on-disk queue before starting the reboot, which
            # will stop the landscape-client process.

            # It would be nice if the Deferred returned from
            # broker.send_message guaranteed the message was saved to disk
            # before firing, but that's not the case, so we add an additional
            # delay.
            deferred.addCallback(self._reboot_later)
        return deferred

    def _reboot_later(self, result):
        self._landscape_reactor.call_later(5, self._run_reboot)

    def _run_reboot(self):
        """
        Create a C{ShutdownProcessProtocol} and return its result deferred.
        """
        protocol = ShutdownProcessProtocol()
        minutes = "now"
        protocol.set_timeout(self._landscape_reactor)
        protocol.result.addCallback(self._log_reboot, minutes)
        protocol.result.addErrback(log_failure, "Reboot failed.")
        args = ["/sbin/shutdown", "-r", minutes,
                "Landscape is rebooting the system"]
        self._process_factory.spawnProcess(
            protocol, "/sbin/shutdown", args=args)
        return protocol.result

    def _log_reboot(self, result, minutes):
        """Log the reboot."""
        logging.warning(
            "Landscape is rebooting the system in %s minutes" % minutes)

    def _send_response(self, reboot_result, message, package_change_result,
                       stop_exchanger=False):
        """
        Create a response and dispatch to the broker.
        """
        response = {"type": "change-packages-result",
                    "operation-id": message.get("operation-id")}

        response["result-code"] = package_change_result.code
        if package_change_result.text:
            response["result-text"] = package_change_result.text
        if package_change_result.installs:
            response["must-install"] = sorted(package_change_result.installs)
        if package_change_result.removals:
            response["must-remove"] = sorted(package_change_result.removals)

        logging.info("Queuing response with change package results to "
                     "exchange urgently.")

        deferred = self._broker.send_message(response, self._session_id, True)
        if stop_exchanger:
            logging.info("stopping exchanger due to imminent reboot.")
            deferred.addCallback(lambda _: self._broker.stop_exchanger())
        return deferred

    def handle_change_package_locks(self, message):
        """Handle a C{change-package-locks} message.

        Package locks aren't supported anymore.
        """

        response = {
            "type": "operation-result",
            "operation-id": message.get("operation-id"),
            "status": FAILED,
            "result-text": "This client doesn't support package locks.",
            "result-code": 1}
        return self._broker.send_message(response, self._session_id, True)

    @classmethod
    def find_command(cls, config=None):
        """Return the path to the package-changer script.

        The script's directory is derived from the provided config.
        If that is None or doesn't have a "bindir" then directory of
        sys.argv[0] is returned.
        """
        bindir = get_bindir(config)
        return os.path.join(bindir, "landscape-package-changer")


def main(args):
    if os.getpgrp() != os.getpid():
        os.setsid()
    return run_task_handler(PackageChanger, args)
