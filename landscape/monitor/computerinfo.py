import os
import logging
from twisted.internet.defer import inlineCallbacks

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
        self._cloud_meta_data = None
        self._fetch_async = fetch_async

    def register(self, registry):
        super(ComputerInfo, self).register(registry)
        self._meta_data_path = registry.config.meta_data_path
        self.call_on_accepted("computer-info",
                              self.send_computer_message, True)
        self.call_on_accepted("distribution-info",
                              self.send_distribution_message, True)

    @inlineCallbacks
    def send_computer_message(self, urgent=False):
        if self._cloud_meta_data is None:
            self._cloud_meta_data = yield self._fetch_cloud_meta_data()

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

        if self._cloud_meta_data:
            meta_data = dict(
                meta_data.items() + self._cloud_meta_data.items())
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

    def _fetch_data(self, path, accumulate):
        """
        Get data at C{path} on the EC2 API endpoint, and add the result to the
        C{accumulate} list.
        """
        url = EC2_API + "/meta-data/" + path
        logging.info("Queueing url fetch %s." % url)
        return self._fetch_async(url).addCallback(accumulate.append)

    def _fetch_cloud_meta_data(self):
        """Fetch information about the cloud instance."""
        cloud_data = []
        # We're not using a DeferredList here because we want to keep the
        # number of connections to the backend minimal. See lp:567515.
        deferred = self._fetch_data("instance-id", cloud_data)
        deferred.addCallback(
            lambda ignore:
                self._fetch_data("instance-type", cloud_data))
        deferred.addCallback(
            lambda ignore:
                self._fetch_data("ami-id", cloud_data))

        def store_data(ignore):
            """Record the instance data returned by the EC2 API."""

            def _unicode_none(value):
                if value is None:
                    return None
                else:
                    return value.decode("utf-8")

            (instance_id, instance_type, ami_id) = cloud_data
            return {
                "instance-id": _unicode_none(instance_id),
                "instance-type": _unicode_none(instance_type),
                "ami-id": _unicode_none(ami_id)}

        def log_error(error):
            log_failure(error, msg="Got error while fetching meta-data: %r"
                        % (error.value,))

        deferred.addCallback(store_data)
        deferred.addErrback(log_error)
        return deferred
