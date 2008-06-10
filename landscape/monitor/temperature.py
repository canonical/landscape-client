import time
import os

from landscape.lib.monitor import CoverageMonitor

from landscape.accumulate import Accumulator
from landscape.monitor.monitor import MonitorPlugin


class Temperature(MonitorPlugin):
    """Capture thermal zone temperatures and trip point settings."""

    persist_name = "temperature"
    # Prevent the Plugin base-class from scheduling looping calls.
    run_interval = None

    def __init__(self, interval=30, monitor_interval=60*60,
                 thermal_zone_dir="/proc/acpi/thermal_zone",
                 create_time=time.time):
        self.thermal_zone_dir = thermal_zone_dir
        self._interval = interval
        self._monitor_interval = monitor_interval
        self._create_time = create_time
        self._thermal_zones = []
        self._temperatures = {}

        # A machine that doesn't have any thermal zones will have an
        # empty /proc/acpi/thermal_zone directory.
        if os.path.isdir(self.thermal_zone_dir):
            filenames = sorted(os.listdir(self.thermal_zone_dir))
            for filename in filenames:
                self._thermal_zones.append(filename)
                self._temperatures[filename] = []

    def register(self, registry):
        super(Temperature, self).register(registry)
        if self._thermal_zones:
            self.registry = registry
            self._accumulate = Accumulator(self._persist,
                                           self.registry.step_size)

            registry.reactor.call_every(self._interval, self.run)

            self._monitor = CoverageMonitor(self._interval, 0.8,
                                            "temperature snapshot",
                                            create_time=self._create_time)
            registry.reactor.call_every(self._monitor_interval,
                                        self._monitor.log)
            registry.reactor.call_on("stop", self._monitor.log, priority=2000)
            self.call_on_accepted("temperature", self.exchange, True)

    def create_messages(self):
        messages = []
        for zone in self._thermal_zones:
            temperatures = self._temperatures[zone]
            self._temperatures[zone] = []
            if not temperatures:
                continue
            messages.append({"type": "temperature", "thermal-zone": zone,
                             "temperatures": temperatures})
        return messages

    def send_messages(self, urgent):
        for message in self.create_messages():
            self.registry.broker.send_message(message, urgent=urgent)

    def exchange(self, urgent=False):
        self.registry.broker.call_if_accepted("temperature",
                                              self.send_messages, urgent)

    def _fetch_temperature(self, zone):
        file = open(os.path.join(self.thermal_zone_dir, zone, "temperature"))
        for line in file:
            if line.startswith("temperature"):
                temp = line.split(':', 1)[1].strip().split(' ')[0].strip()
                return int(temp)

    def run(self):
        self._monitor.ping()
        now = int(self._create_time())
        for zone in self._thermal_zones:
            key = ("accumulate", zone)
            new_temperature = self._fetch_temperature(zone)
            step_data = self._accumulate(now, new_temperature, key)
            if step_data:
                self._temperatures[zone].append(step_data)
