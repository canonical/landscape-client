from twisted.internet.utils import getProcessOutput

from landscape.manager.manager import ManagerPlugin


class RebootManager(ManagerPlugin):

    def register(self, registry):
        super(RebootManager, self).register(registry)
        registry.register_message("reboot", self._reboot)

    def _reboot(self, message):
        if message["shutdown"]:
            args = ["-h", "+5", "'Landscape is shutting down the system'"]
        else:
            args = ["-r", "+5", "'Landscape is restarting down the system'"]
        # path is set to None so that getProcessOutput does not
        # chdir to "." see bug #211373
        return getProcessOutput("shutdown", args=args, path=None, errortoo=1)
