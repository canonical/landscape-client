import os
import logging

from landscape.monitor.monitor import MonitorPlugin


class RebootRequired(MonitorPlugin):
    """
    Report whether the system requires a reboot.
    """

    persist_name = "reboot-required"
    run_interval = 900 # 15 minutes

    def __init__(self, reboot_required_filename="/var/run/reboot-required"):
        self._reboot_required_filename = reboot_required_filename

    def _check_reboot_required(self):
        """Return a boolean indicating whether the computer needs a reboot."""
        return os.path.exists(self._reboot_required_filename)

    def _create_message(self):
        """Return the body of the reboot-required message to be sent."""

        message = {}
        key = "flag"
        value = self._check_reboot_required()
        if value != self._persist.get(key):
            self._persist.set(key, value)
            message[key] = value
        return message

    def send_message(self):
        """Send a reboot-required message if needed.

        A message will be send only if the reboot-required status of the
        system has changed.
        """
        message = self._create_message()
        if message:
            message["type"] = "reboot-required"
            logging.info("Queueing message with updated reboot-required info.")
            self.registry.broker.send_message(message)

    def run(self):
        """Send reboot-required messages if the server accepts them."""
        return self.registry.broker.call_if_accepted(
            "reboot-required", self.send_message)
