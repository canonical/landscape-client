import os
import time

from landscape.client.accumulate import Accumulator
from landscape.lib.monitor import CoverageMonitor
from landscape.client.monitor.plugin import MonitorPlugin


class LoadAverage(MonitorPlugin):
    """Plugin captures information about load average."""

    persist_name = "load-average"
    scope = "load"
    # Prevent the Plugin base-class from scheduling looping calls.
    run_interval = None

    def __init__(self, interval=15, monitor_interval=60*60,
                 create_time=time.time, get_load_average=os.getloadavg):
        self._interval = interval
        self._monitor_interval = monitor_interval
        self._create_time = create_time
        self._load_averages = []
        self._get_load_average = get_load_average

    def register(self, registry):
        super(LoadAverage, self).register(registry)
        self._accumulate = Accumulator(self._persist, registry.step_size)

        self.registry.reactor.call_every(self._interval, self.run)

        self._monitor = CoverageMonitor(self._interval, 0.8,
                                        "load average snapshot",
                                        create_time=self._create_time)
        self.registry.reactor.call_every(self._monitor_interval,
                                         self._monitor.log)
        self.registry.reactor.call_on("stop", self._monitor.log, priority=2000)
        self.call_on_accepted("load-average", self.send_message, True)

    def create_message(self):
        load_averages = self._load_averages
        self._load_averages = []
        return {"type": "load-average", "load-averages": load_averages}

    def exchange(self, urgent=False):
        self.registry.broker.call_if_accepted("load-average",
                                              self.send_message, urgent)

    def send_message(self, urgent=False):
        message = self.create_message()
        if len(message["load-averages"]):
            self.registry.broker.send_message(message, self._session_id,
                                              urgent=urgent)

    def run(self):
        self._monitor.ping()
        new_timestamp = int(self._create_time())
        new_load_average = self._get_load_average()[0]
        step_data = self._accumulate(new_timestamp, new_load_average,
                                     "accumulate")
        if step_data:
            self._load_averages.append(step_data)
