import time

from landscape.accumulate import Accumulator
from landscape.lib.monitor import CoverageMonitor
from landscape.monitor.plugin import MonitorPlugin

class CPUUsage(MonitorPlugin):
    """
    Plugin that captures CPU usage information.
    """

    persist_name = "cpu-usage"
    # Prevent the Plugin base-class from scheduling looping calls.
    run_interval = None

    def __init__(self, interval=30, monitor_interval=60*60,
                 create_time=time.time):
        self._interval = interval
        self._monitor_interval = monitor_interval
        self._cpu_usage_points = []
        self._create_time = create_time

    def register(self, registry):
        super(CPUUsage, self).register(registry)
        self._accumulate = Accumulator(self._persist, registry.step_size)

        self.registry.reactor.call_every(self._interval, self.run)

        self._monitor = CoverageMonitor(self._interval, 0.8,
                                        "CPU usage snapshot",
                                        create_time=self._create_time)
        self.registry.reactor.call_every(self._monitor_interval,
                                         self._monitor.log)
        self.registry.reactor.call_on("stop", self._monitor.log, priority=2000)
        self.call_on_accepted("cpu-usage", self.send_message, True)

    def create_message(self):
        cpu_points = self._cpu_usage_points
        self._cpu_usage_points = []
        return {"type": "cpu-usage", "cpu-usage": cpu_points}

    def send_message(self, urgent=False):
        message = self.create_message()
        if len(message["cpu-usage"]):
            self.registry.broker.send_message(message, urgent=urgent)

    def exchange(self, urgent=False):
        self.registry.broker.call_if_accepted("cpu-usage",
                                              self.send_message, urgent)

    def run(self):
        self._monitor.ping()
        new_timestamp = int(self._create_time())
        new_cpu_usage = self._get_cpu_usage()
        step_data = self._accumulate(new_timestamp, new_cpu_usage, "cpu")
        if step_data:
            self._cpu_usage_points.append(step_data)


    def _get_cpu_usage(self):
        """
        This method computes the CPU usage from /proc/stat.
        """
        return True
