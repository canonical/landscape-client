import commands
import os


class CommandError(Exception):
    """Raised when an external command returns a non-zero status."""


class MemoryStats(object):

    def __init__(self, filename="/proc/meminfo"):
        data = {}
        for line in open(filename):
            if ":" in line:
                key, value = line.split(":", 1)
                if key in ["Active", "MemTotal", "SwapFree", "SwapTotal"]:
                    data[key] = int(value.split()[0])

        self.total_memory = data["MemTotal"] // 1024
        self.free_memory = (data["MemTotal"] - data["Active"]) // 1024
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
        return (self.free_swap / float(self.total_swap)) * 100

    @property
    def used_memory_percentage(self):
        return 100 - self.free_memory_percentage

    @property
    def used_swap_percentage(self):
        return 100 - self.free_swap_percentage



def get_logged_users():
    status, output = commands.getstatusoutput("who -q")
    if status != 0:
        raise CommandError(output)
    first_line = output.split("\n", 1)[0]
    return sorted(set(first_line.split()))


def get_thermal_zones(thermal_zone_path="/proc/acpi/thermal_zone"):
    if os.path.isdir(thermal_zone_path):
        for zone_name in os.listdir(thermal_zone_path):
            yield ThermalZone(os.path.join(thermal_zone_path, zone_name))


class ThermalZone(object):

    temperature = None
    temperature_value = None
    temperature_unit = None

    def __init__(self, zone_path):
        temperature_path = os.path.join(zone_path, "temperature")
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
