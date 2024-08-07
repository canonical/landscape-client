import logging
import json
import traceback

from landscape.client.manager.plugin import DataWatcherManager


def get_reboot_info():
    """
    This code is wrapped in a function so the import or any other exceptions
    can be caught and also so it can be mocked
    """
    from uaclient.api.u.pro.security.status.reboot_required.v1 import (
        reboot_required,)
    return reboot_required().to_dict()


class UbuntuProRebootRequired(DataWatcherManager):
    """
    Plugin that captures and reports from Ubuntu Pro API if the system needs to
    be rebooted. The `uaclient` Python API should be installed by default.
    """

    message_type = "ubuntu-pro-reboot-required"
    scope = "ubuntu-pro"
    run_immediately = True
    run_interval = 900  # 15 minutes

    def get_data(self):
        """
        Return the JSON formatted output of "reboot-required" from Ubuntu Pro
        API.
        """
        data = {}
        try:
            info = get_reboot_info()
            json.dumps(info)  # Make sure data is json serializable
            data["error"] = ""
            data["output"] = info
        except Exception as exc:
            data["error"] = str(exc)
            data["output"] = {}
            logging.error(traceback.format_exc())
        return json.dumps(data, sort_keys=True)
