from twisted.internet.utils import getProcessOutput

from landscape.manager.manager import ManagerPlugin


class ShutdownManager(ManagerPlugin):

    def register(self, registry):
        super(ShutdownManager, self).register(registry)
        registry.register_message("shutdown", self._shutdown)

    def _shutdown(self, message):
        if message["reboot"]:
            args = ["-r", "+5", "'Landscape is restarting down the system'"]
        else:
            args = ["-h", "+5", "'Landscape is shutting down the system'"]
        # path is set to None so that getProcessOutput does not
        # chdir to "." see bug #211373
        return getProcessOutput("shutdown", args=args, path=None, errortoo=1)
