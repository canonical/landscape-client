"""
A monitor that collects data on network activity.
"""

import time

from landscape.lib.network import get_network_traffic
from landscape.accumulate import Accumulator

from landscape.monitor.monitor import MonitorPlugin


class NetworkActivity(MonitorPlugin):
    """
    Collect data regarding a machine's network activity.
    """

    message_type = "network-activity"
    persist_name = message_type

    # Prevent the Plugin base-class from scheduling looping calls.
    run_interval = None

    def __init__(self, interval=30, create_time=time.time):
        self._interval = interval
        self._network_activity = {}
        self._create_time = create_time

    def register(self, registry):
        super(NetworkActivity, self).register(registry)
        self._accumulator = Accumulator(self._persist, self.registry.step_size)
        self.registry.reactor.call_every(self._interval, self.run)
        self.call_on_accepted("network-activity", self.exchange, True)

    def create_message(self):
        network_activity = self._network_activity
        self._network_activity = {}
        return {"type": "network-activity", "activity": network_activity}

    def send_message(self, urgent):
        message = self.create_message()
        if len(message["network-activity"]):
            self.registry.broker.send_message(message, urgent=urgent)

    def exchange(self, urgent=False):
        self.registry.broker.call_if_accepted("network-activity",
                                              self.send_message, urgent)

    def run(self):
        new_timestamp = int(self._create_time())
        new_traffic = get_network_traffic()
        for interface in new_traffic:
            traffic = new_traffic[interface]
            recv_step_data = self._accumulate(
                new_timestamp,
                traffic["recv_bytes"],
                "traffic-recv-%s"%interface)
            send_step_data = self._accumulate(
                new_timestamp,
                traffic["send_bytes"],
                "traffic-recv-%s"%interface)

            if interface not in self._network_activity:
                self._network_activity[interface] = []

            self._network_activity[interface].append((
                recv_step_data, send_step_data))
