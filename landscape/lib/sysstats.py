from datetime import datetime
import os
import os.path
import struct
import time

from twisted.internet.utils import getProcessOutputAndValue

from landscape.lib.encoding import encode_values
from landscape.lib.timestamp import to_timestamp


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
    environ = encode_values(os.environ)
    result = getProcessOutputAndValue("who", ["-q"], env=environ)

    def parse_output(args):
        stdout_data, stderr_data, status = args
        if status != 0:
            raise CommandError(stderr_data.decode('ascii'))
        first_line = stdout_data.split(b"\n", 1)[0]
        first_line = first_line.decode('ascii')
        return sorted(set(first_line.split()))
    return result.addCallback(parse_output)


def get_uptime(uptime_file=u"/proc/uptime"):
    """
    This parses a file in /proc/uptime format and returns a floating point
    version of the first value (the actual uptime).
    """
    with open(uptime_file, 'r') as ufile:
        data = ufile.readline()
    up, idle = data.split()
    return float(up)


def get_thermal_zones(thermal_zone_path=None):
    if thermal_zone_path is None:
        if os.path.isdir("/sys/class/thermal"):
            thermal_zone_path = "/sys/class/thermal"
        else:
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
        temperature_path = os.path.join(self.path, "temp")
        if os.path.isfile(temperature_path):
            try:
                with open(temperature_path) as f:
                    line = f.readline()
                    try:
                        self.temperature_value = int(line.strip()) / 1000.0
                        self.temperature_unit = 'C'
                        self.temperature = '{:.1f} {}'.format(
                                self.temperature_value, self.temperature_unit)
                    except ValueError:
                        pass
            except EnvironmentError:
                pass
        else:
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


class LoginInfo(object):
    """Information about a login session gathered from wtmp or utmp."""

    # FIXME This format string works fine on my hardware, but *may* be
    # different depending on the values of __WORDSIZE and
    # __WORDSIZE_COMPAT32 defined in /usr/include/bits/utmp.h:68 (in
    # the definition of struct utmp).  Make sure it works
    # everywhere.   -jk
    RAW_FORMAT = "hi32s4s32s256shhiiiiiii20s"

    def __init__(self, raw_data):
        info = struct.unpack(self.RAW_FORMAT, raw_data)
        self.login_type = info[0]
        self.pid = info[1]
        self.tty_device = self._strip_and_decode(info[2])
        self.id = self._strip_and_decode(info[3])
        self.username = self._strip_and_decode(info[4])
        self.hostname = self._strip_and_decode(info[5])
        self.termination_status = info[6]
        self.exit_status = info[7]
        self.session_id = info[8]
        self.entry_time = datetime.utcfromtimestamp(info[9])
        # FIXME Convert this to a dotted decimal string. -jk
        self.remote_ip_address = info[11]

    def _strip_and_decode(self, bytestring):
        """Helper method to strip b"\0" and return a utf-8 decoded string."""
        return bytestring.strip(b"\0").decode("utf-8")


class LoginInfoReader(object):
    """Reader parses C{/var/log/wtmp} and/or C{/var/run/utmp} files.

    @file: Initialize the reader with an open file.
    """

    def __init__(self, file):
        self._file = file
        self._struct_length = struct.calcsize(LoginInfo.RAW_FORMAT)

    def login_info(self):
        """Returns a generator that yields LoginInfo objects."""
        while True:
            info = self.read_next()

            if not info:
                break

            yield info

    def read_next(self):
        """Returns login data or None if no login data is available."""
        data = self._file.read(self._struct_length)

        if data and len(data) == self._struct_length:
            return LoginInfo(data)

        return None


class BootTimes(object):
    _last_boot = None
    _last_shutdown = None

    def __init__(self, filename="/var/log/wtmp",
                 boots_newer_than=0, shutdowns_newer_than=0):
        self._filename = filename
        self._boots_newer_than = boots_newer_than
        self._shutdowns_newer_than = shutdowns_newer_than

    def get_times(self):
        reboot_times = []
        shutdown_times = []
        with open(self._filename, "rb") as login_info_file:
            reader = LoginInfoReader(login_info_file)
            self._last_boot = self._boots_newer_than
            self._last_shutdown = self._shutdowns_newer_than

            for info in reader.login_info():
                if info.tty_device.startswith("~"):
                    timestamp = to_timestamp(info.entry_time)
                    if (info.username == "reboot" and
                            timestamp > self._last_boot):
                        reboot_times.append(timestamp)
                        self._last_boot = timestamp
                    elif (info.username == "shutdown" and
                            timestamp > self._last_shutdown):
                        shutdown_times.append(timestamp)
                        self._last_shutdown = timestamp
        return reboot_times, shutdown_times

    def get_last_boot_time(self):
        if self._last_boot is None:
            self._last_boot = int(time.time() - get_uptime())
        return self._last_boot
