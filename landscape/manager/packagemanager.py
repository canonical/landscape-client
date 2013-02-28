import logging
import os

from twisted.internet.utils import getProcessOutput
from twisted.internet.defer import succeed

from landscape.package.store import PackageStore
from landscape.package.changer import PackageChanger
from landscape.package.releaseupgrader import ReleaseUpgrader
from landscape.manager.plugin import ManagerPlugin, SUCCEEDED, FAILED
from landscape.manager.shutdownmanager import ShutdownProcessProtocol


class PackageManager(ManagerPlugin):

    run_interval = 1800
    _package_store = None

    def register(self, registry):
        super(PackageManager, self).register(registry)
        self.config = registry.config

        if not self._package_store:
            filename = os.path.join(registry.config.data_path,
                                    "package/database")
            self._package_store = PackageStore(filename)

        registry.register_message("change-packages",
                                  self.handle_change_packages)
        registry.register_message("change-package-locks",
                                  self.handle_change_package_locks)
        registry.register_message("release-upgrade",
                                  self.handle_release_upgrade)

        # When the package reporter notifies us that something has changed,
        # we want to run again to see if we can now fulfill tasks that were
        # skipped before.
        registry.reactor.call_on("package-data-changed", self.run)

        self.run()

    def _handle(self, cls, message):
        """Queue C{message} as a task, and spawn the proper handler."""
        self._package_store.add_task(cls.queue_name, message)
        self.spawn_handler(cls)

    def handle_change_packages(self, message):
        result = self._handle(PackageChanger, message)
        if message.get("reboot-if-necessary"):
            result.addCallback(self._reboot_after_changing_packages, message)
        return result

    def _reboot_after_changing_packages(self, message):
        """Perform a reboot after changing the packages."""
        operation_id = message["operation-id"]
        protocol = ShutdownProcessProtocol()
        minutes = "+%d" % (protocol.delay // 60,)
        args = ["/sbin/shutdown", "-r", minutes,
                "Landscape is rebooting the system"]
        protocol.set_timeout(self.registry.reactor)
        protocol.result.addCallback(self._respond_success, operation_id)
        protocol.result.addErrback(self._respond_failure, operation_id)
        command, args = self._get_command_and_args(protocol, True)
        self._process_factory.spawnProcess(protocol, command, args=args)

    def _respond_success(self, data, operation_id):
        logging.info("Shutdown request succeeded.")
        return self._respond(SUCCEEDED, data, operation_id)

    def _respond_failure(self, failure, operation_id):
        logging.info("Shutdown request failed.")
        return self._respond(FAILED, failure.value.data, operation_id)

    def handle_change_package_locks(self, message):
        return self._handle(PackageChanger, message)

    def handle_release_upgrade(self, message):
        return self._handle(ReleaseUpgrader, message)

    def run(self):
        result = self.registry.broker.get_accepted_message_types()
        result.addCallback(self._got_message_types)
        return result

    def _got_message_types(self, message_types):
        if "change-packages-result" in message_types:
            self.spawn_handler(PackageChanger)
        if "operation-result" in message_types:
            self.spawn_handler(ReleaseUpgrader)

    def spawn_handler(self, cls):
        args = ["--quiet"]
        if self.config.config:
            args.extend(["-c", self.config.config])
        if self._package_store.get_next_task(cls.queue_name):
            # path is set to None so that getProcessOutput does not
            # chdir to "." see bug #211373
            result = getProcessOutput(cls.find_command(),
                                      args=args, env=os.environ,
                                      errortoo=1,
                                      path=None)
            result.addCallback(self._got_output, cls)
        else:
            result = succeed(None)
        return result

    def _got_output(self, output, cls):
        if output:
            logging.warning("Package %s output:\n%s" %
                            (cls.queue_name, output))
