import logging

from landscape.lib.lsb_release import LSB_RELEASE_FILENAME, parse_lsb_release
from landscape.lib.network import get_fqdn
from landscape.monitor.plugin import MonitorPlugin


class DistributionInfoError(Exception):
    pass


class ComputerInfo(MonitorPlugin):
    """Plugin captures and reports basic computer information."""

    persist_name = "computer-info"

    def __init__(self, get_fqdn=get_fqdn,
                 meminfo_file="/proc/meminfo",
                 lsb_release_filename=LSB_RELEASE_FILENAME):
        self._get_fqdn = get_fqdn
        self._meminfo_file = meminfo_file
        self._lsb_release_filename = lsb_release_filename

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
                         self._get_fqdn())
        total_memory, total_swap = self._get_memory_info()
        self._add_if_new(message, "total-memory",
                         total_memory)
        self._add_if_new(message, "total-swap", total_swap)
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

    def _get_distribution_info(self):
        """Get details about the distribution."""
        message = {}
        message.update(parse_lsb_release(self._lsb_release_filename))
        return message
