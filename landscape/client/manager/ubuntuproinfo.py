import json
import subprocess
from pathlib import Path

from landscape.client import IS_CORE
from landscape.client.manager.plugin import ManagerPlugin
from landscape.lib.persist import Persist


class UbuntuProInfo(ManagerPlugin):
    """
    Plugin that captures and reports Ubuntu Pro registration
    information.

    We use the `pro` CLI with output formatted as JSON. This is sent
    as-is and parsed by Landscape Server because the JSON content is
    considered "Experimental" and we don't want to have to change in
    both Client and Server in the event that the format changes.
    """

    message_type = "ubuntu-pro-info"
    run_interval = 900  # 15 minutes

    def register(self, registry):
        super().register(registry)
        self._persist_filename = Path(
            self.registry.config.data_path,
            "ubuntu-pro-info.bpickle",
        )
        self._persist = Persist(filename=self._persist_filename)
        self.call_on_accepted(self.message_type, self.send_message)

    def run(self):
        return self.registry.broker.call_if_accepted(
            self.message_type,
            self.send_message,
        )

    def send_message(self):
        """Send a message to the broker if the data has changed since the last
        call"""
        result = self.get_data()
        if not result:
            return
        message = {"type": self.message_type, "ubuntu-pro-info": result}
        return self.registry.broker.send_message(message, self._session_id)

    def get_data(self):
        """Persist data to avoid sending messages if result hasn't changed"""
        ubuntu_pro_info = get_ubuntu_pro_info()

        if self._persist.get("data") != ubuntu_pro_info:
            self._persist.set("data", ubuntu_pro_info)
            return json.dumps(ubuntu_pro_info, separators=(",", ":"))

    def _reset(self):
        """Reset the persist."""
        self._persist.remove("data")


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
            ["pro", "status", "--format", "json"],
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
