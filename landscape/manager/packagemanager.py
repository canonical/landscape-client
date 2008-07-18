import logging
import os

from twisted.internet.utils import getProcessOutput
from twisted.internet.defer import succeed

from landscape.package.store import PackageStore
from landscape.package.changer import find_changer_command
from landscape.manager.manager import ManagerPlugin


class PackageManager(ManagerPlugin):

    run_interval = 1800

    def __init__(self, package_store_filename=None):
        super(PackageManager, self).__init__()
        if package_store_filename:
            self._package_store = PackageStore(package_store_filename)
        else:
            self._package_store = None
        self._changer_command = find_changer_command()

    def register(self, registry):
        super(PackageManager, self).register(registry)
        self.config = registry.config

        if not self._package_store:
            filename = os.path.join(registry.config.data_path,
                                    "package/database")
            self._package_store = PackageStore(filename)

        registry.register_message("change-packages",
                                  self._enqueue_message_as_changer_task)

        self.run()

    def _enqueue_message_as_changer_task(self, message):
        self._package_store.add_task("changer", message)
        self.spawn_changer()

    def run(self):
        result = self.registry.broker.get_accepted_message_types()
        result.addCallback(self._got_message_types)
        return result

    def _got_message_types(self, message_types):
        if "change-packages-result" in message_types:
            self.spawn_changer()

    def spawn_changer(self):
        args = ["--quiet"]
        if self.config.config:
            args.extend(["-c", self.config.config])
        if self._package_store.get_next_task("changer"):
            # path is set to None so that getProcessOutput does not
            # chdir to "." see bug #211373
            result = getProcessOutput(self._changer_command,
                                      args=args, env=os.environ,
                                      errortoo=1,
                                      path=None)
            result.addCallback(self._got_changer_output)
        else:
            result = succeed(None)
        return result

    def _got_changer_output(self, output):
        if output:
            logging.warning("Package changer output:\n%s" % output)
