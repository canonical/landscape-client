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
            command = "shutdown -h now"
        else:
            command = "shutdown -r now"
        if os.system(command) != 0:
            raise RebootError("'%s' had a non-zero exit value." % command)
