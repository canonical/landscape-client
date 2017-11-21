import logging
import time
import os

from twisted.internet import threads

from landscape.client.accumulate import Accumulator
from landscape.lib.monitor import CoverageMonitor
from landscape.lib.network import get_active_device_info
from landscape.client.monitor.plugin import MonitorPlugin

try:
    from swift.common.ring import Ring
    from swift.cli.recon import Scout
    has_swift = True
except ImportError:
    has_swift = False


class SwiftUsage(MonitorPlugin):
    """Plugin reporting Swift cluster usage.

    This only works if the client runs on a Swift node.  It requires the
    'python-swift' package to be installed (which is installed on swift nodes).

    """

    persist_name = "swift-usage"
    scope = "storage"

    def __init__(self, interval=30, monitor_interval=60 * 60,
                 create_time=time.time,
                 swift_ring="/etc/swift/object.ring.gz"):
        self._interval = interval
        self._monitor_interval = monitor_interval
        self._create_time = create_time
        self._swift_ring = swift_ring  # To discover Recon host/port

        self._has_swift = has_swift
        self._swift_usage_points = []
        self.active = True

    def register(self, registry):
        super(SwiftUsage, self).register(registry)
        self._accumulate = Accumulator(self._persist, self._interval)
        self._monitor = CoverageMonitor(
            self.run_interval, 0.8, "Swift device usage snapshot",
            create_time=self._create_time)
        self.registry.reactor.call_every(
            self._monitor_interval, self._monitor.log)

        self.registry.reactor.call_on("stop", self._monitor.log, priority=2000)
        self.call_on_accepted("swift-usage", self.send_message, True)

    def create_message(self):
        usage_points = self._swift_usage_points
        self._swift_usage_points = []
        if usage_points:
            return {"type": "swift-usage", "data-points": usage_points}

    def send_message(self, urgent=False):
        message = self.create_message()
        if message:
            self.registry.broker.send_message(
                message, self._session_id, urgent=urgent)

    def exchange(self, urgent=False):
        self.registry.broker.call_if_accepted(
            "swift-usage", self.send_message, urgent)

    def run(self):
        if not self._should_run():
            return

        self._monitor.ping()

        host = self._get_recon_host()
        deferred = threads.deferToThread(self._perform_recon_call, host)
        deferred.addCallback(self._handle_usage)
        return deferred

    def _should_run(self):
        """Return whether the plugin should run."""
        if not self.active:
            return False

        if not self._has_swift:
            logging.info(
                "This machine does not appear to be a Swift machine. "
                "Deactivating plugin.")
            self.active = False
            return False

        # Check for object ring config file.
        # If it is not present, it's not a Swift machine or it not yet set up.
        if not os.path.exists(self._swift_ring):
            return False

        return True

    def _get_recon_host(self):
        """Return a tuple with Recon (host, port)."""
        local_ips = self._get_local_ips()
        ring = Ring(self._swift_ring)
        for dev in ring.devs:
            if dev and dev["ip"] in local_ips:
                return dev["ip"], dev["port"]

    def _get_local_ips(self):
        """Return a list of IP addresses for local devices."""
        return [
            device["ip_address"] for device in get_active_device_info()]

    def _perform_recon_call(self, host):
        """Get usage information from Swift Recon service."""
        if not host:
            return

        scout = Scout("diskusage")
        # Perform the actual call
        scout_result = scout.scout(host)
        disk_usage = scout_result[1]
        status_code = scout_result[2]
        if status_code == 200:
            return disk_usage

    def _handle_usage(self, disk_usage):
        if disk_usage is None:
            # The recon failed, most likely because swift is not responding.
            return
        timestamp = int(self._create_time())

        devices = set()
        for usage in disk_usage:
            if not usage["mounted"]:
                continue

            device = usage["device"]
            devices.add(device)

            step_values = []
            for key in ("size", "avail", "used"):
                # Store values in tree so it's easy to delete all values for a
                # device
                persist_key = "usage.%s.%s" % (device, key)
                step_value = self._accumulate(
                    timestamp, usage[key], persist_key)
                step_values.append(step_value)

            if all(step_values):
                point = [step_value[0], device]  # accumulated timestamp
                point.extend(int(step_value[1]) for step_value in step_values)
                self._swift_usage_points.append(tuple(point))

        # Update device list and remove usage for devices that no longer exist.
        current_devices = set(self._persist.get("devices", ()))
        for device in current_devices - devices:
            self._persist.remove("usage.%s" % device)
        self._persist.set("devices", list(devices))
