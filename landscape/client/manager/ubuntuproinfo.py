import json
import subprocess

from landscape.client import IS_CORE
from landscape.client.manager.plugin import ManagerPlugin


class UbuntuProInfo(ManagerPlugin):
    """A plugin to retrieve Ubuntu Pro information."""

    message_type = "ubuntu-pro-info"
    run_interval = 900  # 15 minutes
    run_immediately = True

    def register(self, registry):
        super().register(registry)
        self.call_on_accepted(self.message_type, self.send_message)

    def run(self):
        return self.registry.broker.call_if_accepted(
            self.message_type,
            self.send_message,
        )

    def send_message(self):
        result = self.get_data()
        return result.addCallback(self._got_output)

    def _got_output(self, output):
        message = {"type": self.message_type, "data": output}
        return self.registry.broker.send_message(message, self._session_id)

    def get_data(self):
        ubuntu_pro_info = get_ubuntu_pro_info()

        return json.dumps(ubuntu_pro_info, separators=(",", ":"))


def get_ubuntu_pro_info() -> dict:
    """Query ua tools for Ubuntu Pro status as JSON, parsing it to a dict.

    If we are running on Ubuntu Core, Pro does not exist - returns a message
    indicating this.
    """
    if IS_CORE:
        return _ubuntu_pro_error_message(
            "Ubuntu Pro is not available on Ubuntu Core.",
            "core-unsupported",
        )

    try:
        completed_process = subprocess.run(
            ["ua", "status", "--format", "json"],
            encoding="utf8",
            stdout=subprocess.PIPE,
        )
    except FileNotFoundError:
        return _ubuntu_pro_error_message(
            "ubuntu pro tools not found.",
            "tools-error",
        )
    else:
        return json.loads(completed_process.stdout)


def _ubuntu_pro_error_message(message: str, code: str) -> dict:
    """Marshall `message` and `code` into a format matching that expected from
    an error from ua tools.
    """
    return {
        "errors": [
            {
                "message": message,
                "message_code": code,
                "service": None,
                "type": "system",
            },
        ],
        "result": "failure",
    }
