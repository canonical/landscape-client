import json
import subprocess

from landscape.client.monitor.plugin import DataWatcher


class UaInfo(DataWatcher):
    """Plugin that captures and reports UA registration information."""

    message_type = "ua-info"
    scope = "ua"

    def __init__(self):
        super(UaInfo, self).__init__()

        self._persist_ua_info = {}

    def register(self, registry):
        super(UaInfo, self).register(registry)
        self.call_on_accepted(self.message_type, self.exchange, True)

    def get_message(self):
        ua_status = get_ua_status()

        if ua_status == self._persist_ua_info:
            return None

        return {
            "type": "ua-info",
            "ua-status": json.dumps(ua_status, separators=(",", ":")),
        }


def get_ua_status():
    try:
        ua_status_call = subprocess.run(
            ["ua", "status", "--format", "json"],
            encoding="utf8", stdout=subprocess.PIPE)
    except FileNotFoundError:
        return {
            "errors": [{
                "message": "ubuntu-advantage-tools not found.",
                "message_code": "tools-error",
                "service": None,
                "type": "system",
            }],
            "result": "failure",
        }
    else:
        return json.loads(ua_status_call.stdout)
