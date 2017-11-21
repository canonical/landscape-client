import os
import logging

from landscape.lib.fs import read_text_file
from landscape.client.monitor.plugin import MonitorPlugin


REBOOT_REQUIRED_FILENAME = "/var/run/reboot-required"


class RebootRequired(MonitorPlugin):
    """
    Report whether the system requires a reboot.

    @param reboot_required_filename: The path to the flag file that indicates
        if the system needs to be rebooted.
    """

    persist_name = "reboot-required"
    scope = "package"
    run_interval = 900  # 15 minutes
    run_immediately = True

    def __init__(self, reboot_required_filename=REBOOT_REQUIRED_FILENAME):
        self._flag_filename = reboot_required_filename
        self._packages_filename = reboot_required_filename + ".pkgs"

    def _get_flag(self):
        """Return a boolean indicating whether the computer needs a reboot."""
        return os.path.exists(self._flag_filename)

    def _get_packages(self):
        """Return the list of packages that required a reboot, if any."""
        if not os.path.exists(self._packages_filename):
            return []

        lines = read_text_file(self._packages_filename).splitlines()
        packages = set(line.strip() for line in lines if line)
        return sorted(packages)

    def _create_message(self):
        """Return the body of the reboot-required message to be sent."""
        message = {}
        flag = self._get_flag()
        packages = self._get_packages()
        for key, value in [("flag", flag), ("packages", packages)]:
            if value == self._persist.get(key):
                continue
            self._persist.set(key, value)
            message[key] = value
        return message

    def send_message(self):
        """Send a reboot-required message if needed.

        A message will be sent only if the reboot-required status of the
        system has changed.
        """
        message = self._create_message()
        if message:
            message["type"] = "reboot-required-info"
            logging.info("Queueing message with updated "
                         "reboot-required status.")
            self.registry.broker.send_message(message, self._session_id,
                                              urgent=True)

    def run(self):
        """Send reboot-required messages if the server accepts them."""
        return self.registry.broker.call_if_accepted(
            "reboot-required-info", self.send_message)
