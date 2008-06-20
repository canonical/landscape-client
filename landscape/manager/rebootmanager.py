import os

from twisted.internet.defer import Deferred

from landscape.manager.manager import ManagerPlugin


class RebootError(Exception):
    """Called when an L{os.system} call to C{shutdown} fails."""


class RebootManager(ManagerPlugin):

    def register(self, registry):
        super(RebootManager, self).register(registry)
        registry.register_message("reboot", self._reboot)

    def _reboot(self, message):
        if message["shutdown"]:
            command = "shutdown -h +5 'Landscape is shutting down the system'"
        else:
            command = "shutdown -r +5 'Landscape is restarting the system'"
        if os.system(command) != 0:
            raise RebootError("'shutdown' returned a non-zero exit value.")
