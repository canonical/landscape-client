from twisted.internet.utils import getProcessOutputAndValue
import os


class CommandError(Exception):
    """Raised when an external command returns a non-zero status."""


class MemoryStats(object):

    def __init__(self, filename="/proc/meminfo"):
        data = {}
        for line in open(filename):
            if ":" in line:
                key, value = line.split(":", 1)
                if key in ["MemTotal", "SwapFree", "SwapTotal", "MemFree",
                           "Buffers", "Cached"]:
                    data[key] = int(value.split()[0])

        self.total_memory = data["MemTotal"] // 1024
        self.free_memory = (data["MemFree"] + data["Buffers"] +
                            data["Cached"]) // 1024
        self.total_swap = data["SwapTotal"] // 1024
        self.free_swap = data["SwapFree"] // 1024

    @property
    def used_memory(self):
        return self.total_memory - self.free_memory

    @property
    def used_swap(self):
        return self.total_swap - self.free_swap

    @property
    def free_memory_percentage(self):
        return (self.free_memory / float(self.total_memory)) * 100

    @property
    def free_swap_percentage(self):
        if self.total_swap == 0:
            return 0.0
        else:
            return (self.free_swap / float(self.total_swap)) * 100

    @property
    def used_memory_percentage(self):
        return 100 - self.free_memory_percentage

    @property
    def used_swap_percentage(self):
        if self.total_swap == 0:
            return 0.0
        else:
            return 100 - self.free_swap_percentage


def get_logged_in_users():
    result = getProcessOutputAndValue("who", ["-q"], env=os.environ)

    def parse_output((stdout_data, stderr_data, status)):
        if status != 0:
            raise CommandError(stderr_data)
        first_line = stdout_data.split("\n", 1)[0]
        return sorted(set(first_line.split()))
    return result.addCallback(parse_output)


def get_thermal_zones(thermal_zone_path=None):
    if thermal_zone_path is None:
        thermal_zone_path = "/proc/acpi/thermal_zone"
    if os.path.isdir(thermal_zone_path):
        for zone_name in sorted(os.listdir(thermal_zone_path)):
            yield ThermalZone(thermal_zone_path, zone_name)


class ThermalZone(object):

    temperature = None
    temperature_value = None
    temperature_unit = None

    def __init__(self, base_path, name):
        self.name = name
        self.path = os.path.join(base_path, name)
        temperature_path = os.path.join(self.path, "temperature")
        if os.path.isfile(temperature_path):
            for line in open(temperature_path):
                if line.startswith("temperature:"):
                    self.temperature = line[12:].strip()
                    try:
                        value, unit = self.temperature.split()
                        self.temperature_value = int(value)
                        self.temperature_unit = unit
                    except ValueError:
                        pass
