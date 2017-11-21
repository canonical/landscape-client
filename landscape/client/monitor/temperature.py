import time

from landscape.lib.monitor import CoverageMonitor
from landscape.lib.sysstats import get_thermal_zones

from landscape.client.accumulate import Accumulator
from landscape.client.monitor.plugin import MonitorPlugin


class Temperature(MonitorPlugin):
    """Capture thermal zone temperatures and trip point settings."""

    persist_name = "temperature"
    scope = "temperature"
    # Prevent the Plugin base-class from scheduling looping calls.
    run_interval = None

    def __init__(self, interval=30, monitor_interval=60 * 60,
                 thermal_zone_path=None, create_time=time.time):
        self.thermal_zone_path = thermal_zone_path
        self._interval = interval
        self._monitor_interval = monitor_interval
        self._create_time = create_time
        self._thermal_zones = []
        self._temperatures = {}

        for thermal_zone in get_thermal_zones(self.thermal_zone_path):
            self._thermal_zones.append(thermal_zone.name)
            self._temperatures[thermal_zone.name] = []

    def register(self, registry):
        super(Temperature, self).register(registry)
        if self._thermal_zones:
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
            self.registry.broker.send_message(
                message, self._session_id, urgent=urgent)

    def exchange(self, urgent=False):
        self.registry.broker.call_if_accepted("temperature",
                                              self.send_messages, urgent)

    def run(self):
        self._monitor.ping()
        now = int(self._create_time())
        for zone in get_thermal_zones(self.thermal_zone_path):
            if zone.temperature_value is not None:
                key = ("accumulate", zone.name)
                step_data = self._accumulate(now, zone.temperature_value, key)
                if step_data:
                    self._temperatures[zone.name].append(step_data)
