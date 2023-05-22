from uaclient.api.u.pro.security.status.reboot_required.v1 import (
    reboot_required,
)

from landscape.client.monitor.plugin import DataWatcher


class UbuntuProRebootRequired(DataWatcher):
    """
    Plugin that captures and reports from Ubuntu Pro API if the system needs to
    be rebooted. The `uaclient` Python API should be installed by default.
    """

    message_type = "ubuntu-pro-reboot-required"
    message_key = message_type
    persist_name = message_type
    scope = "ubuntu-pro"
    run_immediately = True
    run_interval = 900  # 15 minutes

    def get_data(self):
        """
        Return the JSON formatted output of "reboot-required" from Ubuntu Pro
        API.
        """

        return reboot_required().to_json()
