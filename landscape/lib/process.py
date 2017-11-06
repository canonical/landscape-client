from __future__ import absolute_import

import logging
import os
from datetime import timedelta, datetime

from landscape.lib import sysstats
from landscape.lib.timestamp import to_timestamp
from landscape.lib.jiffies import detect_jiffies


class ProcessInformation(object):
    """
    @param proc_dir: The directory to use for process information.
    @param jiffies: The value to use for jiffies per second.
    @param boot_time: An alternate value to use for the last boot time.  If
        None, the system last boot time will be used.
    @param uptime: The uptime value to use (for unit tests only).
    """

    def __init__(self, proc_dir="/proc", jiffies=None, boot_time=None,
                 uptime=None):
        if boot_time is None:
            boot_time = sysstats.BootTimes().get_last_boot_time()
        if boot_time is not None:
            boot_time = datetime.utcfromtimestamp(boot_time)
        self._boot_time = boot_time
        self._proc_dir = proc_dir
        self._jiffies_per_sec = jiffies or detect_jiffies()
        self._uptime = uptime

    def get_all_process_info(self):
        """Get process information for all processes on the system."""
        for filename in os.listdir(self._proc_dir):
            try:
                process_id = int(filename)
            except ValueError:
                continue
            process_info = self.get_process_info(process_id)
            if process_info:
                yield process_info

    def get_process_info(self, process_id):
        """
        Parse the /proc/<pid>/cmdline and /proc/<pid>/status files for
        information about the running process with process_id.

        The /proc filesystem doesn't behave like ext2, open files can disappear
        during the read process.
        """
        cmd_line_name = ""
        process_dir = os.path.join(self._proc_dir, str(process_id))
        process_info = {"pid": process_id}

        try:
            file = open(os.path.join(process_dir, "cmdline"), "r")
            try:
                # cmdline is a \0 separated list of strings
                # We take the first, and then strip off the path, leaving
                # us with the basename.
                cmd_line = file.readline()
                cmd_line_name = os.path.basename(cmd_line.split("\0")[0])
            finally:
                file.close()

            file = open(os.path.join(process_dir, "status"), "r")
            try:
                for line in file:
                    parts = line.split(":", 1)
                    if parts[0] == "Name":
                        process_info["name"] = (cmd_line_name.strip() or
                                                parts[1].strip())
                    elif parts[0] == "State":
                        state = parts[1].strip()
                        # In Lucid, capital T is used for both tracing stop
                        # and stopped. Starting with Natty, lowercase t is
                        # used for tracing stop.
                        if state == "T (tracing stop)":
                            state = state.lower()
                        process_info["state"] = state[0].encode("ascii")
                    elif parts[0] == "Uid":
                        value_parts = parts[1].split()
                        process_info["uid"] = int(value_parts[0])
                    elif parts[0] == "Gid":
                        value_parts = parts[1].split()
                        process_info["gid"] = int(value_parts[0])
                    elif parts[0] == "VmSize":
                        value_parts = parts[1].split()
                        process_info["vm-size"] = int(value_parts[0])
                        break
            finally:
                file.close()

            file = open(os.path.join(process_dir, "stat"), "r")
            try:
                # These variable names are lifted directly from proc(5)
                # utime: The number of jiffies that this process has been
                #        scheduled in user mode.
                # stime: The number of jiffies that this process has been
                #        scheduled in kernel mode.
                # cutime: The number of jiffies that this process's waited-for
                #         children have been scheduled in user mode.
                # cstime: The number of jiffies that this process's waited-for
                #         children have been scheduled in kernel mode.
                parts = file.read().split()
                start_time = int(parts[21])
                utime = int(parts[13])
                stime = int(parts[14])
                uptime = self._uptime or sysstats.get_uptime()
                pcpu = calculate_pcpu(utime, stime, uptime,
                                      start_time, self._jiffies_per_sec)
                process_info["percent-cpu"] = pcpu
                delta = timedelta(0, start_time // self._jiffies_per_sec)
                if self._boot_time is None:
                    logging.warning(
                        "Skipping process (PID %s) without boot time.")
                    return None
                process_info["start-time"] = to_timestamp(
                    self._boot_time + delta)
            finally:
                file.close()

        except IOError:
            # Handle the race that happens when we find a process
            # which terminates before we open the stat file.
            return None

        assert("pid" in process_info and "state" in process_info and
               "name" in process_info and "uid" in process_info and
               "gid" in process_info and "start-time" in process_info)
        return process_info


def calculate_pcpu(utime, stime, uptime, start_time, hertz):
    """
    Implement ps' algorithm to calculate the percentage cpu utilisation for a
    process.::

    unsigned long long total_time;   /* jiffies used by this process */
    unsigned pcpu = 0;               /* scaled %cpu, 99 means 99% */
    unsigned long long seconds;      /* seconds of process life */
    total_time = pp->utime + pp->stime;
    if(include_dead_children) total_time += (pp->cutime + pp->cstime);
    seconds = seconds_since_boot - pp->start_time / hertz;
    if(seconds) pcpu = (total_time * 100ULL / hertz) / seconds;
    if (pcpu > 99U) pcpu = 99U;
    return snprintf(outbuf, COLWID, "%2u", pcpu);
    """
    pcpu = 0
    total_time = utime + stime
    seconds = uptime - (start_time / hertz)
    if seconds:
        pcpu = total_time * 100 / hertz / seconds
    return round(max(min(pcpu, 99.0), 0), 1)
