import json
import subprocess
from datetime import datetime
from datetime import timedelta
from datetime import timezone
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

    If we are running on Ubuntu Core, Pro does not exist.  Include a mocked
    message to allow us to register under an Ubuntu Pro license on Server.
    """
    if IS_CORE:
        effective_datetime = datetime.now(tz=timezone.utc)

        # expiration_datetime affects how long a computer could remain pending
        # and still pass the licensing expiration check.  30 days is ample.
        expiration_datetime = effective_datetime + timedelta(30)
        return _get_core_ubuntu_pro_info(
            effective_datetime,
            expiration_datetime,
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


def _get_core_ubuntu_pro_info(
    effective_datetime: datetime,
    expiration_datetime: datetime,
):
    """Mock Ubuntu Pro info for a Core distribution.

    Datetime parameters need to be timezone-aware to be understood by Server.
    See https://docs.python.org/3/library/datetime.html#aware-and-naive-objects.  # noqa
    """
    return {
        "_doc": (
            "Content provided in json response is currently considered "
            "Experimental and may change"
        ),
        "_schema_version": "0.1",
        "account": {
            "created_at": "",
            "external_account_ids": [],
            "id": "",
            "name": "",
        },
        "attached": False,
        "config": {
            "contract_url": "https://contracts.canonical.com",
            "data_dir": "/var/lib/ubuntu-advantage",
            "log_file": "/var/log/ubuntu-advantage.log",
            "log_level": "debug",
            "security_url": "https://ubuntu.com/security",
            "ua_config": {
                "apt_news": False,
                "apt_news_url": "https://motd.ubuntu.com/aptnews.json",
                "global_apt_http_proxy": None,
                "global_apt_https_proxy": None,
                "http_proxy": None,
                "https_proxy": None,
                "metering_timer": 14400,
                "ua_apt_http_proxy": None,
                "ua_apt_https_proxy": None,
                "update_messaging_timer": 21600,
            },
        },
        "config_path": "/etc/ubuntu-advantage/uaclient.conf",
        "contract": {
            "created_at": "",
            "id": "",
            "name": "",
            "products": ["landscape"],
            "tech_support_level": "n/a",
        },
        "effective": effective_datetime.isoformat(),
        "environment_vars": [],
        "errors": [],
        "execution_details": "No Ubuntu Pro operations are running",
        "execution_status": "inactive",
        "expires": expiration_datetime.isoformat(),
        "features": {},
        "machine_id": None,
        "notices": [],
        "result": "success",
        "services": [
            {
                "available": "yes",
                "description": "Management and administration tool for Ubuntu",
                "description_override": None,
                "name": "landscape",
            },
        ],
        "simulated": False,
        "version": "31.1",
        "warnings": [],
    }
