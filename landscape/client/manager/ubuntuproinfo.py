import json
import subprocess
from datetime import datetime
from datetime import timedelta
from datetime import timezone

from landscape.client import IS_CORE
from landscape.client import IS_SNAP
from landscape.client.manager.plugin import DataWatcherManager
from landscape.client import UA_DATA_DIR


class UbuntuProInfo(DataWatcherManager):
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

    def get_data(self):
        ubuntu_pro_info = get_ubuntu_pro_info()
        return json.dumps(ubuntu_pro_info, separators=(",", ":"),
                          sort_keys=True)


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

    if IS_SNAP:
        # By default, Ubuntu Advantage / Pro stores the status information
        # in /var/lib/ubuntu-advantage/status.json (we have a `system-files`
        # plug for this).
        # This `data_dir` can however be changed in
        # /etc/ubuntu-advantage/uaclient.conf which would lead to
        # permission errors since we don't have a plug for arbitrary
        # folders on the host fs.

        try:
            with open(f"{UA_DATA_DIR}/status.json") as fp:
                pro_info = json.load(fp)
        except (FileNotFoundError, PermissionError):
            # Happens if the Ubuntu Pro client isn't installed, or
            #  if the `data_dir` folder setting was changed from the default
            return {}

        # The status file has more information than `pro status`
        keys_to_keep = [
            "_doc",
            "_schema_version",
            "account",
            "attached",
            "config",
            "config_path",
            "contract",
            "effective",
            "environment_vars",
            "errors",
            "execution_details",
            "execution_status",
            "expires",
            "features",
            "machine_id",
            "notices",
            "result",
            "services",
            "simulated",
            "version",
            "warnings",
        ]
        return {k: pro_info[k] for k in keys_to_keep if k in pro_info}

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
