import logging
import os

from twisted.internet.utils import getProcessOutput
from twisted.internet.defer import succeed

from landscape.lib.encoding import encode_values
from landscape.lib.apt.package.store import PackageStore
from landscape.client.package.changer import PackageChanger
from landscape.client.package.releaseupgrader import ReleaseUpgrader
from landscape.client.manager.plugin import ManagerPlugin


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
        return self._handle(PackageChanger, message)

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
            command = cls.find_command(self.config)
            environ = encode_values(os.environ)
            # path is set to None so that getProcessOutput does not
            # chdir to "." see bug #211373
            result = getProcessOutput(
                command, args=args, env=environ, errortoo=1, path=None)
            result.addCallback(self._got_output, cls)
        else:
            result = succeed(None)
        return result

    def _got_output(self, output, cls):
        if output:
            logging.warning("Package %s output:\n%s" %
                            (cls.queue_name, output))
