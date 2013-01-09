import time
import logging

from landscape.lib.monitor import CoverageMonitor
from landscape.monitor.plugin import MonitorPlugin


LAST_MESURE_KEY = "last-cpu-usage-mesure"


class CPUUsage(MonitorPlugin):
    """
    Plugin that captures CPU usage information.
    """

    persist_name = "cpu-usage"
    # Prevent the Plugin base-class from scheduling looping calls.
    run_interval = None

    def __init__(self, interval=30, monitor_interval=60 * 60,
                 create_time=time.time):
        self._interval = interval
        self._monitor_interval = monitor_interval
        self._cpu_usage_points = []
        self._create_time = create_time
        self._stat_file = "/proc/stat"

    def register(self, registry):
        super(CPUUsage, self).register(registry)

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
        new_cpu_usage = self._get_cpu_usage(self._stat_file)
        if new_cpu_usage is not None:
            self._cpu_usage_points.append((new_timestamp, new_cpu_usage))

    def _get_cpu_usage(self, stat_file):
        """
        This method computes the CPU usage from C{stat_file}.
        """
        result = None
        stat = None

        try:
            with open(stat_file, "r") as f:
                # The first line of the file is the CPU information aggregated
                # across cores.
                stat = f.readline()
        except IOError:
            logging.error("Could not open %s for reading, "
                          "CPU usage cannot be computed.", stat_file)
            return None

        # The cpu line is composed of:
        # ["cpu", user, nice, system, idle, iowait, irq, softirq, steal, guest,
        # guest nice]
        # The fields are a sum of USER_HZ quantums since boot spent in each
        # "category". We need to keep track of what the previous measure was,
        # since the current CPU usage will be calculated on the delta between
        # the previous measure and the current measure.
        # Remove the trailing "\n"
        fields = stat.replace("\n", "")
        fields = fields.split(" ")
        # remove the "cpu" line header and the first field ("")
        fields = fields[2:]

        previous_fields = self._persist.get(LAST_MESURE_KEY)
        if previous_fields is not None:
            # That's a shortcut for the trivial case where nothing changes.
            if previous_fields == fields:
                return 0

            delta_fields = []
            used_delta = 0
            for i in range(len(fields)):
                delta_fields.append(int(fields[i]) - int(previous_fields[i]))
                # Sum up all delta fields except idle
                if i != 3:
                    used_delta = used_delta + delta_fields[i]

            idle_delta = delta_fields[3]

            divisor = idle_delta + used_delta
            if divisor == 0:
                result = 0
            else:
                result = used_delta / float(divisor)

        self._persist.set(LAST_MESURE_KEY, fields)
        return result
