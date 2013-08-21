import os
import logging

from landscape.lib.fetch import fetch_async
from landscape.lib.fs import read_file
from landscape.lib.log import log_failure
from landscape.lib.lsb_release import LSB_RELEASE_FILENAME, parse_lsb_release
from landscape.lib.network import get_fqdn
from landscape.monitor.plugin import MonitorPlugin

EC2_HOST = "169.254.169.254"
EC2_API = "http://%s/latest" % (EC2_HOST,)


class DistributionInfoError(Exception):
    pass


class ComputerInfo(MonitorPlugin):
    """Plugin captures and reports basic computer information."""

    persist_name = "computer-info"
    scope = "computer"

    def __init__(self, get_fqdn=get_fqdn,
                 meminfo_file="/proc/meminfo",
                 lsb_release_filename=LSB_RELEASE_FILENAME,
                 root_path="/", fetch_async=fetch_async):
        self._get_fqdn = get_fqdn
        self._meminfo_file = meminfo_file
        self._lsb_release_filename = lsb_release_filename
        self._root_path = root_path
        self._config = None
        self._cloud_meta_data = {}
        self._fetch_async = fetch_async

    def register(self, registry):
        super(ComputerInfo, self).register(registry)
        self._meta_data_path = registry.config.meta_data_path
        self.call_on_accepted("computer-info",
                              self.send_computer_message, True)
        self.call_on_accepted("distribution-info",
                              self.send_distribution_message, True)
        self.client.reactor.call_on("run", self._fetch_cloud_meta_data)

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
        meta_data = {}
        if os.path.exists(self._meta_data_path):
            for key in os.listdir(self._meta_data_path):
                meta_data[key] = read_file(
                    os.path.join(self._meta_data_path, key))

        self._fetch_cloud_meta_data()
        meta_data = dict(
            meta_data.items() + self._get_cloud_meta_data().items())
        if meta_data:
            self._add_if_new(message, "meta-data", meta_data)
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

    def _get_cloud_meta_data(self):
        return self._cloud_meta_data

    def _fetch_data(self, path, accumulate):
        """
        Get data at C{path} on the EC2 API endpoint, and add the result to the
        C{accumulate} list.
        """
        logging.info("Queueing url fetch %s." % (EC2_API + path))
        return self._fetch_async(EC2_API + path).addCallback(accumulate.append)

    def _fetch_cloud_meta_data(self):
        """Fetch information about the cloud instance."""
        if self.monitor.config.get("cloud", None):
            cloud_data = []
            # We're not using a DeferredList here because we want to keep the
            # number of connections to the backend minimal. See lp:567515.
            deferred = self._fetch_data("/meta-data/instance-id", cloud_data)
            deferred.addCallback(
                    lambda ignore, path="/meta-data/instance-type":
                        self._fetch_data(path, cloud_data))
            deferred.addCallback(
                    lambda ignore, path="/meta-data/ami-id":
                        self._fetch_data(path, cloud_data))

            def store_data(ignore):
                """Record the instance data returned by the EC2 API."""
                (instance_key, instance_type, ami_key) = cloud_data
                self._cloud_meta_data = {
                    "instance_key": instance_key,
                    "image_key": ami_key,
                    "instance_type": instance_type}
                for k, v in self._cloud_meta_data.items():
                    if v is None:
                        continue
                    self._cloud_meta_data[k] = v.decode("utf-8")

            def log_error(error):
                log_failure(error, msg="Got error while fetching meta-data: %r"
                            % (error.value,))

            deferred.addCallback(store_data)
            deferred.addErrback(log_error)
