import os
import logging
import socket

from landscape.monitor.monitor import MonitorPlugin


class DistributionInfoError(Exception):
    pass


class ComputerInfo(MonitorPlugin):
    """Plugin captures and reports basic computer information."""

    persist_name = "computer-info"

    def __init__(self, get_hostname=socket.gethostname,
                 meminfo_file="/proc/meminfo",
                 lsb_release_filename="/etc/lsb-release",
                 reboot_required_filename="/var/run/reboot-required"):
        self._get_hostname = get_hostname
        self._meminfo_file = meminfo_file
        self._lsb_release_filename = lsb_release_filename
        self._reboot_required_filename = reboot_required_filename

    def register(self, registry):
        super(ComputerInfo, self).register(registry)
        self.registry.reactor.call_on("resynchronize", self._resynchronize)
        self.call_on_accepted("computer-info",
                              self.send_computer_message, True)
        self.call_on_accepted("distribution-info",
                              self.send_distribution_message, True)

    def _resynchronize(self):
        self.registry.persist.remove(self.persist_name)

    def send_computer_message(self, urgent=False):
        message = self._create_computer_info_message()
        if message:
            message["type"] = "computer-info"
            logging.info("Queueing message with updated computer info.")
            self.registry.broker.send_message(message, urgent=urgent)

    def send_distribution_message(self, urgent=False):
        message = self._create_distribution_info_message()
        if message:
            message["type"] = "distribution-info"
            logging.info("Queueing message with updated distribution info.")
            self.registry.broker.send_message(message, urgent=urgent)

    def exchange(self, urgent=False):
        broker = self.registry.broker
        broker.call_if_accepted("computer-info",
                                self.send_computer_message, urgent)
        broker.call_if_accepted("distribution-info",
                                self.send_distribution_message, urgent)

    def _create_computer_info_message(self):
        message = {}
        self._add_if_new(message, "hostname",
                         self._get_hostname())
        total_memory, total_swap = self._get_memory_info()
        self._add_if_new(message, "total-memory",
                         total_memory)
        self._add_if_new(message, "total-swap", total_swap)
        self._add_if_new(message, "reboot-required",
                         self._check_reboot_required())
        return message

    def _add_if_new(self, message, key, value):
        if value != self._persist.get(key):
            self._persist.set(key, value)
            message[key] = value

    def _create_distribution_info_message(self):
        message = self._get_distribution_info()
        if message != self._persist.get("distribution-info"):
            self._persist.set("distribution-info", message)
            return message
        return None

    def _get_memory_info(self):
        """Get details in megabytes and return a C{(memory, swap)} tuple."""
        message = {}
        file = open(self._meminfo_file)
        for line in file:
            if line != '\n':
                parts = line.split(":")
                key = parts[0]
                if key in ["MemTotal", "SwapTotal"]:
                    value = int(parts[1].strip().split(" ")[0])
                    message[key] = value
        file.close()
        return (message["MemTotal"] // 1024, message["SwapTotal"] // 1024)

    lsb_release_keys = {"DISTRIB_ID": "distributor-id",
                        "DISTRIB_DESCRIPTION": "description",
                        "DISTRIB_RELEASE": "release",
                        "DISTRIB_CODENAME": "code-name"}

    def _check_reboot_required(self):
        return os.path.exists(self._reboot_required_filename)

    def _get_distribution_info(self):
        """Get details about the distribution."""
        message = {}
        file = open(self._lsb_release_filename, "r")
        for line in file:
            key, value = line.split("=")
            if key in self.lsb_release_keys:
                key = self.lsb_release_keys[key.strip()]
                value = value.strip().strip('"')
                message[key] = value
        file.close()
        return message
