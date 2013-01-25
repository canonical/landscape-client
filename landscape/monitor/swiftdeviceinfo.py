import logging
import time
import os
import json

from landscape.lib.fetch import fetch, HTTPCodeError, PyCurlError, FetchError
from landscape.lib.monitor import CoverageMonitor
from landscape.lib.network import get_active_device_info
from landscape.monitor.plugin import MonitorPlugin


class SwiftDeviceInfo(MonitorPlugin):

    persist_name = "swift-device-info"

    def __init__(self, interval=300, monitor_interval=60 * 60,
                 create_time=time.time,
                 swift_config="/etc/swift/object-server.conf",
                 swift_ring="/etc/swift/object.ring.gz"):
        self.run_interval = interval
        self._monitor_interval = monitor_interval
        self._create_time = create_time
        self._fetch = fetch
        self._get_network_devices = get_active_device_info
        self._swift_config = swift_config  # If exists, we are a swift node
        self._swift_ring = swift_ring      # To discover swift recon port
        self._swift_recon_url = None
        self._create_time = create_time
        self._swift_device_info = []
        self._swift_device_info_to_persist = []

    def register(self, registry):
        super(SwiftDeviceInfo, self).register(registry)
        self._monitor = CoverageMonitor(self.run_interval, 0.8,
                                        "swift device info snapshot",
                                        create_time=self._create_time)
        self.registry.reactor.call_every(self._monitor_interval,
                                         self._monitor.log)
        self.registry.reactor.call_on("stop", self._monitor.log, priority=2000)
        self.call_on_accepted("swift-device-info", self.send_messages, True)

    def create_swift_device_info_message(self):
        if self._swift_device_info:
            message = {"type": "swift-device-info",
                       "swift-device-info": self._swift_device_info}
            self._swift_device_info_to_persist = self._swift_device_info[:]
            self._swift_device_info = []
            return message
        return None

    def send_messages(self, urgent=False):
        message = self.create_swift_device_info_message()
        if message:
            logging.info("Queueing message with updated swift device info.")
            d = self.registry.broker.send_message(message, urgent=urgent)
            d.addCallback(lambda x: self.persist_swift_info())

    def exchange(self):
        self.registry.broker.call_if_accepted("swift-device-info",
                                              self.send_messages)

    def persist_swift_info(self):
        for swift_device_info in self._swift_device_info_to_persist:
            device_name = swift_device_info["device"]
            key = (self.persist_name, device_name)
            self._persist.set(key, swift_device_info)
        self._swift_device_info_to_persist = None
        # This forces the registry to write the persistent store to disk
        # This means that the persistent data reflects the state of the
        # messages sent.
        self.registry.flush()

    def run(self):
        self._monitor.ping()

        current_swift_devices = self._get_swift_devices()
        current_device_names = []
        for swift_info in current_swift_devices:
            device_name = swift_info["device"]
            current_device_names.append(device_name)
            key = (self.persist_name, device_name)
            prev_swift_info = self._persist.get(key)
            if not prev_swift_info or prev_swift_info != swift_info:
                if swift_info not in self._swift_device_info:
                    self._swift_device_info.append(swift_info)

        # Get all persisted devices and remove those that no longer exist
        persisted_devices = self._persist.get(self.persist_name)
        if persisted_devices:
            for device_name in persisted_devices.keys():
                if device_name not in current_device_names:
                    self._persist.remove((self.persist_name, device_name))

    def _get_swift_devices(self):
        config_file = self._swift_config
        # Check if a swift storage config file is available. No need to run
        # if we know that we're not on a swift monitor node anyway.
        if not os.path.exists(config_file):
            # There is no config file - it's not a swift storage machine.
            return []

        # Extract the swift service URL from the ringfile and cache it.
        if self._swift_recon_url is None:
            ring = self._get_ring()
            if ring is None:
                return []

            network_devices = self._get_network_devices()
            local_ips = [device["ip_address"] for device in network_devices]

            # Grab first swift service with an IP on this host
            for dev in ring.devs:
                if dev and dev["ip"] in local_ips:
                    self._swift_recon_url = "http://%s:%d/recon/diskusage" % (
                        dev['ip'], dev['port'])
                    break

            if self._swift_recon_url is None:
                logging.error(
                    "Local swift service not found.")
                return []

        recon_disk_info = self._get_swift_disk_usage()
        # We don't care about avail and free figures because we track
        # free_space for mounted devices in free-space messages
        return [{"device": "/dev/%s" % device["device"],
                 "mounted":  device["mounted"]} for device in recon_disk_info]

    def _get_swift_disk_usage(self):
        """
        Query the swift storage usage data by parsing the curled recon data
        from http://localhost:<_swift_service_port>/recon/diskusage.
        Lots of recon data for the picking described at:
        http://docs.openstack.org/developer/swift/admin_guide.html
        """
        error_message = None
        try:
            content = self._fetch(self._swift_recon_url)
        except HTTPCodeError, error:
            error_message = (
                "Swift service is running without swift-recon enabled.")
        except (FetchError, PyCurlError), error:
            error_message = (
                "Swift service not available at %s. %s" %
                (self._swift_recon_url, str(error)))
        if error_message is not None:
            logging.error(error_message)
            return None

        if not content:
            return None

        swift_disk_usages = json.loads(content)  # list of device dicts
        return swift_disk_usages

    def _get_ring(self):
        """Return ring-file object from self._swift_ring location"""
        if not os.path.exists(self._swift_ring):
            logging.warning(
                "Swift ring files are not available yet.")
            return None
        try:
            from swift.common.ring import Ring
        except ImportError:
            logging.error(
                "Swift python common libraries not found.")
            return None
        return Ring(self._swift_ring)
