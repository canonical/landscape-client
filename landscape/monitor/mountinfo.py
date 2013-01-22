import logging
import time
import os
import json

from landscape.lib.disk import get_mount_info
from landscape.lib.fetch import fetch, HTTPCodeError, PyCurlError, FetchError
from landscape.lib.monitor import CoverageMonitor
from landscape.lib.network import get_active_device_info
from landscape.accumulate import Accumulator
from landscape.monitor.plugin import MonitorPlugin


class MountInfo(MonitorPlugin):

    persist_name = "mount-info"

    max_free_space_items_to_exchange = 200

    def __init__(self, interval=300, monitor_interval=60 * 60,
                 mounts_file="/proc/mounts", create_time=time.time,
                 statvfs=None, hal_manager=None, mtab_file="/etc/mtab",
                 swift_config="/etc/swift/object-server.conf",
                 swift_ring="/etc/swift/account.ring.gz"):
        self.run_interval = interval
        self._monitor_interval = monitor_interval
        self._create_time = create_time
        self._fetch = fetch
        self._get_network_devices = get_active_device_info
        self._mounts_file = mounts_file
        self._mtab_file = mtab_file
        if statvfs is None:
            statvfs = os.statvfs
        self._statvfs = statvfs
        self._swift_config = swift_config  # If exists, we are a swift node
        self._swift_ring = swift_ring      # To discover swift recon port
        self._swift_recon_url = None
        self._create_time = create_time
        self._free_space = []
        self._mount_info = []
        self._mount_info_to_persist = None
        try:
            from landscape.hal import HALManager
        except ImportError:
            self._hal_manager = hal_manager
        else:
            self._hal_manager = hal_manager or HALManager()
        try:
            from gi.repository import GUdev
        except ImportError:
            self._gudev_client = None
        else:
            try:
                self._gudev_client = GUdev.Client.new([])
            except AttributeError:
                # gudev < 1.2 uses a different unsupported interface
                self._gudev_client = None

    def register(self, registry):
        super(MountInfo, self).register(registry)
        self._accumulate = Accumulator(self._persist, self.registry.step_size)
        self._monitor = CoverageMonitor(self.run_interval, 0.8,
                                        "mount info snapshot",
                                        create_time=self._create_time)
        self.registry.reactor.call_every(self._monitor_interval,
                                         self._monitor.log)
        self.registry.reactor.call_on("stop", self._monitor.log, priority=2000)
        self.call_on_accepted("mount-info", self.send_messages, True)

    def create_messages(self):
        return filter(None, [self.create_mount_info_message(),
                             self.create_free_space_message()])

    def create_mount_info_message(self):
        if self._mount_info:
            message = {"type": "mount-info", "mount-info": self._mount_info}
            self._mount_info_to_persist = self._mount_info[:]
            self._mount_info = []
            return message
        return None

    def create_free_space_message(self):
        if self._free_space:
            items_to_exchange = self._free_space[
                :self.max_free_space_items_to_exchange]
            message = {"type": "free-space",
                       "free-space": items_to_exchange}
            self._free_space = self._free_space[
                self.max_free_space_items_to_exchange:]
            return message
        return None

    def send_messages(self, urgent=False):
        for message in self.create_messages():
            d = self.registry.broker.send_message(message, urgent=urgent)
            if message["type"] == "mount-info":
                d.addCallback(lambda x: self.persist_mount_info())

    def exchange(self):
        self.registry.broker.call_if_accepted("mount-info",
                                              self.send_messages)

    def persist_mount_info(self):
        for timestamp, mount_info in self._mount_info_to_persist:
            mount_point = mount_info["mount-point"]
            self._persist.set(("mount-info", mount_point), mount_info)
        self._mount_info_to_persist = None
        # This forces the registry to write the persistent store to disk
        # This means that the persistent data reflects the state of the
        # messages sent.
        self.registry.flush()

    def run(self):
        self._monitor.ping()
        now = int(self._create_time())
        current_mount_points = set()

        swift_devices = self._get_swift_devices()
        for mount_info in self._get_mount_info():
            mount_point = mount_info["mount-point"]
            if mount_info["device"] in swift_devices:
                mount_info["service-designation"] = "swift"
            free_space = mount_info.pop("free-space")

            key = ("accumulate-free-space", mount_point)
            step_data = self._accumulate(now, free_space, key)
            if step_data:
                timestamp = step_data[0]
                free_space = int(step_data[1])
                self._free_space.append((timestamp, mount_point, free_space))

            prev_mount_info = self._persist.get(("mount-info", mount_point))
            if not prev_mount_info or prev_mount_info != mount_info:
                if mount_info not in [m for t, m in self._mount_info]:
                    self._mount_info.append((now, mount_info))

            current_mount_points.add(mount_point)

    def _get_removable_devices(self):
        if self._hal_manager is not None:
            return self._get_hal_removable_devices()
        elif self._gudev_client is not None:
            return self._get_udev_removable_devices()
        else:
            return set()

    def _get_udev_removable_devices(self):
        class is_removable(object):
            def __contains__(oself, device_name):
                device = self._gudev_client.query_by_device_file(device_name)
                if device:
                    return device.get_sysfs_attr_as_boolean("removable")
                return False
        return is_removable()

    def _get_hal_removable_devices(self):
        block_devices = {}  # {udi: [device, ...]}
        children = {}  # {parent_udi: [child_udi, ...]}
        removable = set()

        # We walk the list of devices building up a dictionary of all removable
        # devices, and a mapping of {UDI => [block devices]}
        # We differentiate between devices that we definitely know are
        # removable and devices that _may_ be removable, depending on their
        # parent device, e.g. /dev/sdb1 isn't flagged as removable, but
        # /dev/sdb may well be removable.

        # Unfortunately, HAL doesn't guarantee the order of the devices
        # returned from get_devices(), so we may not know that a parent device
        # is removable when we find it's first child.
        devices = self._hal_manager.get_devices()
        for device in devices:
            block_device = device.properties.get("block.device")
            if block_device:
                if device.properties.get("storage.removable"):
                    removable.add(device.udi)

                try:
                    block_devices[device.udi].append(block_device)
                except KeyError:
                    block_devices[device.udi] = [block_device]

                parent_udi = device.properties.get("info.parent")
                if parent_udi is not None:
                    try:
                        children[parent_udi].append(device.udi)
                    except KeyError:
                        children[parent_udi] = [device.udi]

        # Propagate the removable flag from each node all the way to
        # its leaf children.
        updated = True
        while updated:
            updated = False
            for parent_udi in children:
                if parent_udi in removable:
                    for child_udi in children[parent_udi]:
                        if child_udi not in removable:
                            removable.add(child_udi)
                            updated = True

        # We've now seen _all_ devices, and have the definitive list of
        # removable UDIs, so we can now find all the removable devices in the
        # system.
        removable_devices = set()
        for udi in removable:
            removable_devices.update(block_devices[udi])

        return removable_devices

    def _get_mount_info(self):
        """Generator yields local mount points worth recording data for."""
        removable_devices = self._get_removable_devices()
        bound_mount_points = self._get_bound_mount_points()

        for info in get_mount_info(self._mounts_file, self._statvfs):
            device = info["device"]
            mount_point = info["mount-point"]
            if (device.startswith("/dev/") and
                not mount_point.startswith("/dev/") and
                not device in removable_devices and
                not mount_point in bound_mount_points):
                yield info

    def _get_bound_mount_points(self):
        """
        Returns a set of mount points that have the "bind" option
        by parsing /etc/mtab.
        """
        bound_points = set()
        if not self._mtab_file or not os.path.isfile(self._mtab_file):
            return bound_points

        file = open(self._mtab_file, "r")
        for line in file:
            try:
                device, mount_point, filesystem, options = line.split()[:4]
                mount_point = mount_point.decode("string-escape")
            except ValueError:
                continue
            if "bind" in options.split(","):
                bound_points.add(mount_point)
        return bound_points

    def _get_swift_devices(self):
        config_file = self._swift_config
        # Check if a swift storage config file is available. No need to run
        # if we know that we're not on a swif monitor node anyway.
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
        return [
            "/dev/%s" % device["device"]
                for device in recon_disk_info if device["mounted"]]

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

        if content is None:
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
