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

    def __init__(
        self,
        process_factory=None,
        script_tempdir: str | None = None,
    ):
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
        try:
            token = message["token"]
            d = ensureDeferred(
                attach_pro(token)
            )
            d.addCallback(self._respond_success, opid)
            d.addErrback(self._respond_failure, opid)
            return d
        except Exception as e:
            self._respond(FAILED, self._format_exception(e), opid)

    def _format_exception(self, e):
        return "{}: {}".format(e.__class__.__name__, e.args[0])

    def _respond_success(self, data, opid):
        return self._respond(
            SUCCEEDED,
            json.dumps(get_ubuntu_pro_info()),
            opid
        )

    def _respond_failure(self, failure, opid):
        code = None
        if failure.check(AttachProError):
            code = ATTACH_PRO_FAILURE

        return self._respond(FAILED, str(failure), opid, code)

    def _respond(self, status, data, opid, result_code=None):
        if not isinstance(data, str):
            data = data.decode("utf-8", "replace")
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
