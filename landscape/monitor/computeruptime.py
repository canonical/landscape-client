import time
from datetime import datetime
import os
import struct

from landscape.lib.timestamp import to_timestamp
from landscape.monitor.plugin import MonitorPlugin


def get_uptime(uptime_file=u"/proc/uptime"):
    """
    This parses a file in /proc/uptime format and returns a floating point
    version of the first value (the actual uptime).
    """
    data = file(uptime_file, "r").readline()
    up, idle = data.split()
    return float(up)


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
        self.tty_device = info[2].strip("\0")
        self.id = info[3].strip("\0")
        self.username = info[4].strip("\0")
        self.hostname = info[5].strip("\0")
        self.termination_status = info[6]
        self.exit_status = info[7]
        self.session_id = info[8]
        self.entry_time = datetime.utcfromtimestamp(info[9])
        # FIXME Convert this to a dotted decimal string. -jk
        self.remote_ip_address = info[11]


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
        reader = LoginInfoReader(file(self._filename))
        self._last_boot = self._boots_newer_than
        self._last_shutdown = self._shutdowns_newer_than

        for info in reader.login_info():
            if info.tty_device.startswith("~"):
                timestamp = to_timestamp(info.entry_time)
                if (info.username == "reboot"
                    and timestamp > self._last_boot):
                    reboot_times.append(timestamp)
                    self._last_boot = timestamp
                elif (info.username == "shutdown"
                      and timestamp > self._last_shutdown):
                    shutdown_times.append(timestamp)
                    self._last_shutdown = timestamp
        return reboot_times, shutdown_times

    def get_last_boot_time(self):
        if self._last_boot is None:
            self._last_boot = int(time.time() - get_uptime())
        return self._last_boot


class ComputerUptime(MonitorPlugin):
    """Plugin reports information about computer uptime."""

    persist_name = "computer-uptime"
    scope = "computer"

    def __init__(self, wtmp_file="/var/log/wtmp"):
        self._first_run = True
        self._wtmp_file = wtmp_file

    def register(self, registry):
        """Register this plugin with the specified plugin manager."""
        super(ComputerUptime, self).register(registry)
        registry.reactor.call_on("run", self.run)
        self.call_on_accepted("computer-uptime", self.run, True)

    def run(self, urgent=False):
        """Create a message and put it on the message queue.

        The last logrotated file, if it exists, will be checked the
        first time the plugin runs.  This behaviour ensures we don't
        accidentally miss a reboot/shutdown event if the machine is
        rebooted and wtmp is logrotated before the client starts.
        """
        broker = self.registry.broker
        if self._first_run:
            filename = self._wtmp_file + ".1"
            if os.path.isfile(filename):
                broker.call_if_accepted("computer-uptime",
                                        self.send_message,
                                        filename,
                                        urgent)

        if os.path.isfile(self._wtmp_file):
            broker.call_if_accepted("computer-uptime", self.send_message,
                                    self._wtmp_file, urgent)

    def send_message(self, filename, urgent=False):
        message = self._create_message(filename)
        if "shutdown-times" in message or "startup-times" in message:
            message["type"] = "computer-uptime"
            self.registry.broker.send_message(message, self._session_id,
                                              urgent=urgent)

    def _create_message(self, filename):
        """Generate a message with new startup and shutdown times."""
        message = {}
        startup_times = []
        shutdown_times = []

        last_startup_time = self._persist.get("last-startup-time", 0)
        last_shutdown_time = self._persist.get("last-shutdown-time", 0)

        times = BootTimes(filename,
                          boots_newer_than=last_startup_time,
                          shutdowns_newer_than=last_shutdown_time)

        startup_times, shutdown_times = times.get_times()

        if startup_times:
            self._persist.set("last-startup-time", startup_times[-1])
            message["startup-times"] = startup_times

        if shutdown_times:
            self._persist.set("last-shutdown-time", shutdown_times[-1])
            message["shutdown-times"] = shutdown_times

        return message
