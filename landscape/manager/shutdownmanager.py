from twisted.internet.utils import getProcessOutput

from landscape.manager.manager import ManagerPlugin, SUCCEEDED, FAILED


class ShutdownManager(ManagerPlugin):

    def register(self, registry):
        super(ShutdownManager, self).register(registry)
        registry.register_message("shutdown", self._shutdown)

    def _shutdown(self, message):
        if message["reboot"]:
            args = ["-r", "+5", "'Landscape is restarting down the system'"]
        else:
            args = ["-h", "+5", "'Landscape is shutting down the system'"]

        operation_id = message["operation-id"]
        # path is set to None so that getProcessOutput does not
        # chdir to "." see bug #211373
        completed = getProcessOutput("shutdown", args=args, path=None,
                                     errortoo=1)
        completed.addCallback(self._respond_success, operation_id)
        completed.addErrback(self._respond_failure, operation_id)
        return completed

    def _respond_success(self, data, operation_id):
        return self._respond(SUCCEEDED, data, operation_id)

    def _respond_failure(self, failure, operation_id):
        return self._respond(FAILED, str(failure.value), operation_id)

    def _respond(self, status, data, operation_id):
        message = {"type": "operation-result",
                   "status": status,
                   "result-text": data,
                   "operation-id": operation_id}
        return self.registry.broker.send_message(message, True)
