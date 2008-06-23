import os

from twisted.internet.defer import Deferred
from twisted.internet.utils import getProcessOutput

from landscape.manager.manager import ManagerPlugin


class RebootManager(ManagerPlugin):

    def register(self, registry):
        super(RebootManager, self).register(registry)
        registry.register_message("reboot", self._reboot)

    def _reboot(self, message):
        if message["shutdown"]:
            command = "shutdown -h +5 'Landscape is shutting down the system'"
        else:
            command = "shutdown -r +5 'Landscape is restarting the system'"
        # path is set to None so that getProcessOutput does not
        # chdir to "." see bug #211373
        return getProcessOutput(command, path=None, errortoo=1)
