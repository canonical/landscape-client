import time

from landscape.lib.monitor import CoverageMonitor

from landscape.accumulate import Accumulator
from landscape.monitor.monitor import MonitorPlugin


class MemoryInfo(MonitorPlugin):
    """Plugin captures information about free memory and free swap."""

    persist_name = "memory-info"
    # Prevent the Plugin base-class from scheduling looping calls.
    run_interval = None

    def __init__(self, interval=15, monitor_interval=60*60,
                 source_filename="/proc/meminfo", create_time=time.time):
        self._interval = interval
        self._monitor_interval = monitor_interval
        self._source_filename = source_filename
        self._memory_info = []
        self._create_time = create_time

    def register(self, registry):
        super(MemoryInfo, self).register(registry)
        self._accumulate = Accumulator(self._persist, self.registry.step_size)
        self.registry.reactor.call_every(self._interval, self.run)
        self._monitor = CoverageMonitor(self._interval, 0.8,
                                        "memory/swap snapshot",
                                        create_time=self._create_time)
        self.registry.reactor.call_every(self._monitor_interval,
                                         self._monitor.log)
        self.registry.reactor.call_on("stop", self._monitor.log, priority=2000)
        self.call_on_accepted("memory-info", self.send_message, True)

    def create_message(self):
        memory_info = self._memory_info
        self._memory_info = []
        return {"type": "memory-info", "memory-info": memory_info}

    def send_message(self, urgent=False):
        message = self.create_message()
        if len(message["memory-info"]):
            self.registry.broker.send_message(message, urgent=urgent)

    def exchange(self, urgent=False):
        self.registry.broker.call_if_accepted("memory-info",
                                              self.send_message, urgent)

    def run(self):
        self._monitor.ping()
        new_timestamp = int(self._create_time())
        new_values = self._get_memory_info()
        memory_step_data = self._accumulate(new_timestamp, new_values[0],
                                            "accumulate-memory")
        swap_step_data = self._accumulate(new_timestamp, new_values[1],
                                          "accumulate-swap")

        if memory_step_data and swap_step_data:
            timestamp = memory_step_data[0]
            free_memory = int(memory_step_data[1])
            free_swap = int(swap_step_data[1])
            self._memory_info.append((timestamp, free_memory, free_swap))

    def _get_memory_info(self):
        """Gets data in megabytes and returns a C{(memory, swap)} tuple."""
        file = open(self._source_filename)
        try:
            data = {}
            for line in file.readlines():
                if line != "\n":
                    parts = line.split(":")
                    key = parts[0]

                    if key in ["Active", "MemTotal", "SwapFree"]:
                        value = int(parts[1].strip().split(" ")[0])
                        data[key] = value

            free_memory = data["MemTotal"] - data["Active"]
            free_swap = data["SwapFree"]
            return (free_memory // 1024, free_swap // 1024)
        finally:
            file.close()
