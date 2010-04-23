"""
A monitor that collects data on network activity.
"""

import time

from landscape.lib.monitor import CoverageMonitor
from landscape.lib.network import get_network_traffic
from landscape.accumulate import Accumulator

from landscape.monitor.monitor import MonitorPlugin


class NetworkActivity(MonitorPlugin):
    """
    Collect data regarding a machine's network activity.
    """

    persist_name = "network-activity"

    # Prevent the Plugin base-class from scheduling looping calls.
    run_interval = None

    def __init__(self, interval=30, monitor_interval=60*60,
                 create_time=time.time):
        self._interval = interval
        self._monitor_interval = monitor_interval
        self._network_activity = []
        self._create_time = create_time

    def register(self, registry):
        super(NetworkActivity, self).register(registry)
        self._accumulate = Accumulator(self._persist, registry.step_size)
        self.registry.reactor.call_every(self._interval, self.run)

        self._monitor = CoverageMonitor(self._interval, 0.8,
                                        "network activity snapshot",
                                        create_time=self._create_time)
        self.registry.reactor.call_every(self._monitor_interval,
                                         self._monitor.log)
        self.registry.reactor.call_on("stop", self._monitor.log, priority=2000)

        self.call_on_accepted("network-activity", self.exchange, True)

    def create_message(self):
        network_activity = self._network_activity
        self._network_activity = []
        return {"type": "network-activity", "activity": network_activity}

    def send_message(self, urgent):
        message = self.create_message()
        if len(message["network-activity"]):
            self.registry.broker.send_message(message, urgent=urgent)

    def exchange(self, urgent=False):
        self.registry.broker.call_if_accepted("network-activity",
                                              self.send_message, urgent)

    def run(self):
        self._monitor.ping()
        new_timestamp = int(self._create_time())
        new_traffic = get_network_traffic()
        activity_step_data = self._accumulate(new_timestamp, new_traffic,
                                              "accumulate-traffic")

        if activity_step_data:
            self._network_activity.append(activity_step_data)
