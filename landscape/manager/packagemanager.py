import logging
import os

from twisted.internet.utils import getProcessOutput
from twisted.internet.defer import succeed

from landscape.package.store import PackageStore
from landscape.package.changer import PackageChanger, find_changer_command
from landscape.package.releaseupgrader import (
    ReleaseUpgrader, find_release_upgrader_command)
from landscape.manager.manager import ManagerPlugin


class PackageManager(ManagerPlugin):

    run_interval = 1800

    def __init__(self):
        self._package_store = None

    def register(self, registry):
        super(PackageManager, self).register(registry)
        self.config = registry.config

        if not self._package_store:
            filename = os.path.join(registry.config.data_path,
                                          "package/database")
            self._package_store = PackageStore(filename)

        registry.register_message("change-packages", self.handle_message)
        registry.register_message("release-upgrade", self.handle_message)

        self.run()

    def handle_message(self, message):
        """Queue C{message} as a task, and spawn the proper handler."""
        if message["type"] == "change-packages":
            cls = PackageChanger
        if message["type"] == "release-upgrade":
            cls = ReleaseUpgrader
        self._package_store.add_task(cls.queue_name, message)
        self.spawn_handler(cls)

    def run(self):
        result = self.registry.broker.get_accepted_message_types()
        result.addCallback(self._got_message_types)
        return result

    def _got_message_types(self, message_types):
        if "change-packages-result" in message_types:
            self.spawn_handler(PackageChanger)

    def find_handler_command(self, cls):
        if cls == PackageChanger:
            return find_changer_command()
        if cls == ReleaseUpgrader:
            return find_release_upgrader_command()

    def spawn_handler(self, cls):
        args = ["--quiet"]
        if self.config.config:
            args.extend(["-c", self.config.config])
        if self._package_store.get_next_task(cls.queue_name):
            # path is set to None so that getProcessOutput does not
            # chdir to "." see bug #211373
            result = getProcessOutput(self.find_handler_command(cls),
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
