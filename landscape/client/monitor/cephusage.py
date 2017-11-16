import logging
import time
import os

from twisted.internet import threads
from twisted.python.compat import unicode

from landscape.client.accumulate import Accumulator
from landscape.lib.monitor import CoverageMonitor
from landscape.client.monitor.plugin import MonitorPlugin


try:
    from rados import Rados
    has_rados = hasattr(Rados, "get_cluster_stats")
except ImportError:
    has_rados = False


class CephUsage(MonitorPlugin):
    """
    Plugin that captures Ceph usage information. This only works if the client
    runs on one of the Ceph monitor nodes, and noops otherwise.

    The plugin requires the 'python-ceph' package to be installed, which is the
    case on a standard "ceph" charm deployment.
    The landscape-client charm should join a ceph-client relation with the ceph
    charm, which will crete a keyring and config file for the landscape-client
    to consume in <data_path>/ceph-client/ceph.landscape-client.conf. It
    contains the following:

    [global]
    auth supported = cephx
    keyring = <keyring-file>
    mon host = <ip>:6789

    The configured keyring can be generated with:

    ceph-authtool <keyring-file> --create-keyring
        --name=client.landscape-client --add-key=<key>
    """

    persist_name = "ceph-usage"
    scope = "storage"
    # Prevent the Plugin base-class from scheduling looping calls.
    run_interval = None

    def __init__(self, interval=30, monitor_interval=60 * 60,
                 create_time=time.time):
        self.active = True
        self._has_rados = has_rados
        self._interval = interval
        self._monitor_interval = monitor_interval
        self._ceph_usage_points = []
        self._ceph_ring_id = None
        self._create_time = create_time
        self._ceph_config = None

    def register(self, registry):
        super(CephUsage, self).register(registry)
        self._ceph_config = os.path.join(
            self.registry.config.data_path, "ceph-client",
            "ceph.landscape-client.conf")

        self._accumulate = Accumulator(self._persist, self._interval)
        self._monitor = CoverageMonitor(
            self._interval, 0.8, "Ceph usage snapshot",
            create_time=self._create_time)

        self.registry.reactor.call_every(self._interval, self.run)
        self.registry.reactor.call_every(
            self._monitor_interval, self._monitor.log)
        self.registry.reactor.call_on("stop", self._monitor.log, priority=2000)
        self.call_on_accepted("ceph-usage", self.send_message, True)

    def create_message(self):
        ceph_points = self._ceph_usage_points
        ring_id = self._ceph_ring_id
        self._ceph_usage_points = []
        return {"type": "ceph-usage",
                "ring-id": ring_id,
                "ceph-usages": [],  # For backwards-compatibility
                "data-points": ceph_points}

    def send_message(self, urgent=False):
        message = self.create_message()
        if message["ring-id"] and message["data-points"]:
            self.registry.broker.send_message(
                message, self._session_id, urgent=urgent)

    def exchange(self, urgent=False):
        self.registry.broker.call_if_accepted(
            "ceph-usage", self.send_message, urgent)

    def run(self):
        if not self._should_run():
            return

        self._monitor.ping()
        deferred = threads.deferToThread(self._perform_rados_call)
        deferred.addCallback(self._handle_usage)
        return deferred

    def _should_run(self):
        """Returns whether or not this plugin should run."""
        if not self.active:
            return False

        if not self._has_rados:
            logging.info("This machine does not appear to be a Ceph machine. "
                         "Deactivating plugin.")
            self.active = False
            return False

        # Check if a ceph config file is available.
        # If it is not, it's not a ceph machine or ceph is not set up yet.
        if self._ceph_config is None or not os.path.exists(self._ceph_config):
            return False

        return True

    def _perform_rados_call(self):
        """The actual Rados interaction."""
        with Rados(conffile=self._ceph_config,
                   rados_id="landscape-client") as cluster:

            cluster_stats = cluster.get_cluster_stats()
            if self._ceph_ring_id is None:
                fsid = unicode(cluster.get_fsid(), "utf-8")
                self._ceph_ring_id = fsid

        return cluster_stats

    def _handle_usage(self, cluster_stats):
        """A method to use as callback to the rados interaction.

        Parses the output and stores the usage data in an accumulator.
        """
        names_map = [
            ("total", "kb"), ("avail", "kb_avail"), ("used", "kb_used")]
        timestamp = int(self._create_time())

        step_values = []
        for name, key in names_map:
            value = cluster_stats[key] * 1024  # Report usage in bytes
            step_value = self._accumulate(timestamp, value, "usage.%s" % name)
            step_values.append(step_value)

        if not all(step_values):
            return

        point = [step_value[0]]  # accumulated timestamp
        point.extend(int(step_value[1]) for step_value in step_values)
        self._ceph_usage_points.append(tuple(point))
