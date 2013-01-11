import time
import os

from landscape.accumulate import Accumulator
from landscape.lib.monitor import CoverageMonitor
from landscape.monitor.plugin import MonitorPlugin

ACCUMULATOR_KEY = "ceph-usage-accumulator"


class CephUsage(MonitorPlugin):
    """
    Plugin that captures Ceph usage information. This only works if the client
    runs on one of the Ceph monitor nodes, and it noops otherwise.
    """
    persist_name = "ceph-usage"
    # Prevent the Plugin base-class from scheduling looping calls.
    run_interval = None

    def __init__(self, interval=30, monitor_interval=60 * 60,
                 create_time=time.time):
        self._interval = interval
        self._monitor_interval = monitor_interval
        self._ceph_usage_points = []
        self._create_time = create_time
        self._ceph_config = "/etc/ceph/ceph.conf"

    def register(self, registry):
        super(CephUsage, self).register(registry)
        self._accumulate = Accumulator(self._persist, registry.step_size)

        self.registry.reactor.call_every(self._interval, self.run)

        self._monitor = CoverageMonitor(self._interval, 0.8,
                                        "Ceph usage snapshot",
                                        create_time=self._create_time)
        self.registry.reactor.call_every(self._monitor_interval,
                                         self._monitor.log)
        self.registry.reactor.call_on("stop", self._monitor.log, priority=2000)
        self.call_on_accepted("ceph-usage", self.send_message, True)

    def create_message(self):
        ceph_points = self._ceph_usage_points
        self._ceph_usage_points = []
        return {"type": "ceph-usage", "ceph-usages": ceph_points}

    def send_message(self, urgent=False):
        message = self.create_message()
        if len(message["ceph-usages"]):
            self.registry.broker.send_message(message, urgent=urgent)

    def exchange(self, urgent=False):
        self.registry.broker.call_if_accepted("ceph-usage",
                                              self.send_message, urgent)

    def run(self):
        self._monitor.ping()
        new_timestamp = int(self._create_time())
        new_ceph_usage = self._get_ceph_usage(self._ceph_config)

        step_data = None
        if new_ceph_usage is not None:
            step_data = self._accumulate(new_timestamp, new_ceph_usage,
                                        ACCUMULATOR_KEY)
        if step_data is not None:
            self._ceph_usage_points.append(step_data)

    def _get_ceph_usage(self, config_file):
        # Execute "ceph status" , get output.
        if not os.path.exists(config_file):
            # There is no config file - it's probably not a ceph machine.
            return None

        return True
