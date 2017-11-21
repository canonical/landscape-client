import os
import logging
from twisted.internet.defer import inlineCallbacks, returnValue

from landscape.lib.fetch import fetch_async
from landscape.lib.fs import read_text_file
from landscape.lib.lsb_release import LSB_RELEASE_FILENAME, parse_lsb_release
from landscape.lib.cloud import fetch_ec2_meta_data
from landscape.lib.network import get_fqdn
from landscape.client.monitor.plugin import MonitorPlugin

METADATA_RETRY_MAX = 3  # Number of retries to get EC2 meta-data


class DistributionInfoError(Exception):
    pass


class ComputerInfo(MonitorPlugin):
    """Plugin captures and reports basic computer information."""

    persist_name = "computer-info"
    scope = "computer"

    def __init__(self, get_fqdn=get_fqdn,
                 meminfo_filename="/proc/meminfo",
                 lsb_release_filename=LSB_RELEASE_FILENAME,
                 root_path="/", fetch_async=fetch_async):
        self._get_fqdn = get_fqdn
        self._meminfo_filename = meminfo_filename
        self._lsb_release_filename = lsb_release_filename
        self._root_path = root_path
        self._cloud_instance_metadata = None
        self._cloud_retries = 0
        self._fetch_async = fetch_async

    def register(self, registry):
        super(ComputerInfo, self).register(registry)
        self._annotations_path = registry.config.annotations_path
        self.call_on_accepted("computer-info",
                              self.send_computer_message, True)
        self.call_on_accepted("distribution-info",
                              self.send_distribution_message, True)
        self.call_on_accepted("cloud-instance-metadata",
                              self.send_cloud_instance_metadata_message, True)

    def send_computer_message(self, urgent=False):
        message = self._create_computer_info_message()
        if message:
            message["type"] = "computer-info"
            logging.info("Queueing message with updated computer info.")
            self.registry.broker.send_message(message, self._session_id,
                                              urgent=urgent)

    def send_distribution_message(self, urgent=False):
        message = self._create_distribution_info_message()
        if message:
            message["type"] = "distribution-info"
            logging.info("Queueing message with updated distribution info.")
            self.registry.broker.send_message(message, self._session_id,
                                              urgent=urgent)

    @inlineCallbacks
    def send_cloud_instance_metadata_message(self, urgent=False):
        message = yield self._create_cloud_instance_metadata_message()
        if message:
            message["type"] = "cloud-instance-metadata"
            logging.info("Queueing message with updated cloud instance "
                         "metadata.")
            self.registry.broker.send_message(message, self._session_id,
                                              urgent=urgent)

    def exchange(self, urgent=False):
        broker = self.registry.broker
        broker.call_if_accepted("computer-info",
                                self.send_computer_message, urgent)
        broker.call_if_accepted("distribution-info",
                                self.send_distribution_message, urgent)
        broker.call_if_accepted("cloud-instance-metadata",
                                self.send_cloud_instance_metadata_message,
                                urgent)

    def _create_computer_info_message(self):
        message = {}
        self._add_if_new(message, "hostname", self._get_fqdn())
        total_memory, total_swap = self._get_memory_info()
        self._add_if_new(message, "total-memory", total_memory)
        self._add_if_new(message, "total-swap", total_swap)
        annotations = {}
        if os.path.exists(self._annotations_path):
            for key in os.listdir(self._annotations_path):
                annotations[key] = read_text_file(
                    os.path.join(self._annotations_path, key))

        if annotations:
            self._add_if_new(message, "annotations", annotations)
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
        file = open(self._meminfo_filename)
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

    @inlineCallbacks
    def _create_cloud_instance_metadata_message(self):
        """Fetch cloud metadata and insert it in a message."""
        message = None
        if (self._cloud_instance_metadata is None and
            self._cloud_retries < METADATA_RETRY_MAX
            ):

            self._cloud_instance_metadata = yield self._fetch_ec2_meta_data()
            message = self._cloud_instance_metadata
        returnValue(message)

    def _fetch_ec2_meta_data(self):
        """Fetch information about the cloud instance."""
        if self._cloud_retries == 0:
            logging.info("Querying cloud meta-data.")
        deferred = fetch_ec2_meta_data(self._fetch_async)

        def log_no_meta_data_found(error):
            self._cloud_retries += 1
            if self._cloud_retries >= METADATA_RETRY_MAX:
                logging.info("No cloud meta-data available. %s" %
                             error.getErrorMessage())

        def log_success(result):
            logging.info("Acquired cloud meta-data.")
            return result

        deferred.addCallback(log_success)
        deferred.addErrback(log_no_meta_data_found)
        return deferred
