import time
import os
import json
import logging
import re

from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.internet import threads

from landscape.accumulate import Accumulator
from landscape.lib.monitor import CoverageMonitor
from landscape.lib.twisted_util import spawn_process
from landscape.monitor.plugin import MonitorPlugin


class CephUsage(MonitorPlugin):
    """
    Plugin that captures Ceph usage information. This only works if the client
    runs on one of the Ceph monitor nodes, and it noops otherwise.

    The plugin requires the 'ceph' command to be available, which is run with a
    config file in <data_path>/ceph-client/ceph.landscape-client.conf with the
    following config:

    [global]
    auth supported = cephx
    keyring = <keyring-file>
    mon host = <ip>:6789

    The configured keyring can be generated with:

    ceph-authtool <keyring-file> --create-keyring
        --name=client.landscape-client --add-key=<key>

    The landscape-client charm automatically provides the client configuration
    and key when deployed as subordinate of a ceph node.
    """

    persist_name = "ceph-usage"
    scope = "storage"
    # Prevent the Plugin base-class from scheduling looping calls.
    run_interval = None

    def __init__(self, interval=30, monitor_interval=60 * 60,
                 create_time=time.time):
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
        return {"type": "ceph-usage", "ceph-usages": ceph_points,
                "ring-id": ring_id}

    def send_message(self, urgent=False):
        message = self.create_message()
        if message["ceph-usages"] and message["ring-id"] is not None:
            self.registry.broker.send_message(message, self._session_id,
                                              urgent=urgent)

    def exchange(self, urgent=False):
        self.registry.broker.call_if_accepted(
            "ceph-usage", self.send_message, urgent)

    @inlineCallbacks
    def run(self):
        self._monitor.ping()

        # Check if a ceph config file is available. If it's not , it's not a
        # ceph machine or ceph is not set up yet. No need to run anything in
        # this case.
        if self._ceph_config is None or not os.path.exists(self._ceph_config):
            returnValue(None)

        fsid, new_ceph_usage = yield threads.deferToThread(self._get_ceph_usage)
        self._ceph_ring_id = fsid
        new_timestamp = int(self._create_time())

        step_data = None
        if new_ceph_usage is not None:
            step_data = self._accumulate(
                new_timestamp, new_ceph_usage, "ceph-usage-accumulator")

        if step_data is not None:
            self._ceph_usage_points.append(step_data)

    def _get_ceph_usage(self):
        """
        Grab the ceph usage data by connecting to the ceph cluster using the
        rados library.

        This method is synchronous, but it's called from deferToThread().

        @return: An (fsid, usage percentage) tuple
        """
        try:
            import rados
        except ImportError:
            # If we cannot import rados, we can't report ceph usage.
            return None, None

        with rados.Rados(conffile=self._ceph_config) as cluster:
            cluster_stats = cluster.get_cluster_stats()
            fsid = cluster.get_fsid()

        total = cluster_stats["kb"]
        available = cluster_stats["kb_avail"]

        # Note: used + available is NOT equal to total (there is some used
        # space for duplication and system info etc...)
        used_space = int(total) - int(available)

        return fsid, used_space / float(total)
