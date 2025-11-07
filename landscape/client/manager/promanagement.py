import json

from twisted.internet.threads import deferToThread

from landscape.client.manager.plugin import (
    FAILED,
    SUCCEEDED,
    ManagerPlugin,
)
from landscape.client.manager.ubuntuproinfo import get_ubuntu_pro_info
from landscape.lib.uaclient import (
    ProManagementError,
    attach_pro,
    detach_pro,
)


class ProManagement(ManagerPlugin):
    """A plugin which allows for users to attach pro tokens."""

    def register(self, registry):
        super().register(registry)
        registry.register_message(
            "attach-pro",
            self._handle_attach_pro,
        )
        registry.register_message(
            "detach-pro",
            self._handle_detach_pro,
        )

    def _handle_attach_pro(self, message: dict):
        """
        Extract data from message and create deferred for
        attaching a pro token.
        """
        opid = message["operation-id"]
        token = message["token"]
        d = deferToThread(attach_pro, token)
        d.addCallback(self._respond_success_attach, opid)
        d.addErrback(self._respond_failure, opid)
        return d

    def _handle_detach_pro(self, message: dict):
        """
        Extract data from message and create deferred for
        detaching a pro token.
        """
        opid = message["operation-id"]
        d = deferToThread(detach_pro)
        d.addCallback(self._respond_success_detach, opid)
        d.addErrback(self._respond_failure, opid)
        return d

    def _respond_success_attach(self, data, opid):
        return self._respond(SUCCEEDED, json.dumps(get_ubuntu_pro_info()), opid)

    def _respond_success_detach(self, data, opid):
        return self._respond(SUCCEEDED, "Succeeded in detaching pro token.", opid)

    def _respond_failure(self, failure, opid):
        try:
            failure.raiseException()
        except ProManagementError as e:
            return self._respond(FAILED, str(e), opid)
        except Exception:
            return self._respond(FAILED, str(failure), opid)

    def _respond(self, status, data, opid, result_code=None):
        message = {
            "type": "operation-result",
            "status": status,
            "result-text": data,
            "operation-id": opid,
        }
        if result_code:
            message["result-code"] = result_code

        return self.registry.broker.send_message(
            message,
            self._session_id,
            True,
        )
