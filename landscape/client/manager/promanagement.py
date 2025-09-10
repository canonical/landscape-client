from twisted.internet.defer import ensureDeferred

from landscape.client.manager.plugin import (
    FAILED,
    ManagerPlugin,
    SUCCEEDED,
)
from landscape.client.manager.ubuntuproinfo import get_ubuntu_pro_info
from landscape.lib.uaclient import AttachProError, attach_pro

import json


ATTACH_PRO_FAILURE = 2


class ProManagement(ManagerPlugin):
    """A plugin which allows for users to attach pro tokens."""

    def __init__(self,):
        ManagerPlugin.__init__(self)

    def register(self, registry):
        super().register(registry)
        registry.register_message(
            "attach-pro",
            self._handle_attach_pro,
        )

    def _handle_attach_pro(self, message: dict):
        """
        Extract data from message and create deferred for
        attaching a pro token.
        """
        opid = message["operation-id"]
        token = message["token"]
        d = ensureDeferred(
            self._attach_pro(token)
        )
        d.addCallback(self._respond_success, opid)
        d.addErrback(self._respond_failure, opid)
        return d

    async def _attach_pro(self, token):
        attach_pro(token)

    def _respond_success(self, data, opid):
        return self._respond(
            SUCCEEDED,
            json.dumps(get_ubuntu_pro_info()),
            opid
        )

    def _respond_failure(self, failure, opid):
        try:
            failure.raiseException()
        except AttachProError as e:
            code = ATTACH_PRO_FAILURE
            return self._respond(FAILED, e.message, opid, code)
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
