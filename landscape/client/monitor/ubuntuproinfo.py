import json
import subprocess

from landscape.client import IS_CORE
from landscape.client.monitor.plugin import DataWatcher


class UbuntuProInfo(DataWatcher):
    """
    Plugin that captures and reports Ubuntu Pro registration
    information.

    We use the `ua` CLI with output formatted as JSON. This is sent
    as-is and parsed by Landscape Server because the JSON content is
    considered "Experimental" and we don't want to have to change in
    both Client and Server in the event that the format changes.
    """

    run_interval = 900  # 15 minutes
    message_type = "ubuntu-pro-info"
    message_key = message_type
    persist_name = message_type
    scope = "ubuntu-pro"
    run_immediately = True

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
