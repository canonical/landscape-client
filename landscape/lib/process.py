import logging
import os
from datetime import timedelta, datetime

from landscape.lib.timestamp import to_timestamp
from landscape.jiffies import detect_jiffies
from landscape.monitor.computeruptime import BootTimes


STATES = {"R (running)": "R",
          "D (disk sleep)": "D",
          "S (sleeping)": "S",
          "T (stopped)": "T",
          "T (tracing stop)": "I",
          "X (dead)": "X",
          "Z (zombie)": "Z"}


class ProcessInformation(object):

    def __init__(self, proc_dir="/proc", jiffies=None, boot_time=None):
        self._uptime = boot_time or get_uptime()
        if boot_time is None:
            boot_time = BootTimes().get_last_boot_time()
        if boot_time is not None:
            boot_time = datetime.utcfromtimestamp(boot_time)
        self._boot_time = boot_time
        self._proc_dir = proc_dir
        self._jiffies_per_sec = jiffies or detect_jiffies()

    def get_process_info(self, process_id):
        cmd_line_name = ""
        process_dir = os.path.join(self._proc_dir, str(process_id))
        process_info = {"pid": process_id}

        try:
            file = open(os.path.join(process_dir, "cmdline"), "r")
        except IOError:
            # Handle the race that happens when we find a process
            # which terminates before we open the stat file.
            return None

        try:
            # cmdline is a \0 separated list of strings
            # We take the first, and then strip off the path, leaving us with
            # the basename.
            cmd_line = file.readline()
            cmd_line_name = os.path.basename(cmd_line.split("\0")[0])
        finally:
            file.close()

        try:
            file = open(os.path.join(process_dir, "status"), "r")
        except IOError:
            # Handle the race that happens when we find a process
            # which terminates before we open the status file.
            return None

        try:
            for line in file:
                parts = line.split(":", 1)
                if parts[0] == "Name":
                    process_info["name"] = (cmd_line_name.strip() or
                                            parts[1].strip())
                elif parts[0] == "State":
                    state = parts[1].strip()
                    process_info["state"] = STATES[state]
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

        try:
            file = open(os.path.join(process_dir, "stat"), "r")
        except IOError:
            # Handle the race that happens when we find a process
            # which terminates before we open the stat file.
            return None

        try:
            parts = file.read().split()
            starttime = int(parts[21])
            utime = int(parts[13])
            stime = int(parts[14])
            cutime = int(parts[15])
            cstime = int(parts[16])

            pcpu = calculate_pcpu(utime, stime, cutime, cstime, self._uptime,
                                  starttime, self._jiffies_per_sec)
            process_info["percent-cpu"] = pcpu
            delta = timedelta(0, starttime // self._jiffies_per_sec)
            if self._boot_time is None:
                logging.warning("Skipping process (PID %s) without boot time.")
                return None
            process_info["start-time"] = to_timestamp(self._boot_time  + delta)
        finally:
            file.close()

        assert("pid" in process_info and "state" in process_info
               and "name" in process_info and "uid" in process_info
               and "gid" in process_info and "start-time" in process_info)
        return process_info

def get_uptime(uptime_file=u"/proc/uptime"):
    """
    This parses a file in /proc/uptime format and returns a floating point
    version of the first value (the actual uptime).
    """
    data = file(uptime_file, "r").readline()
    up, idle = data.split()
    return float(up)


def calculate_pcpu(utime, stime, cutime, cstime, uptime, start_time, Hertz):
    """
    Implement ps' algorithm to calculate the percentage cpu utilisation for a
    process.

    unsigned long long total_time;   /* jiffies used by this process */
    unsigned pcpu = 0;               /* scaled %cpu, 99 means 99% */
    unsigned long long seconds;      /* seconds of process life */
    total_time = pp->utime + pp->stime;
    if(include_dead_children) total_time += (pp->cutime + pp->cstime);
    seconds = seconds_since_boot - pp->start_time / Hertz;
    if(seconds) pcpu = (total_time * 100ULL / Hertz) / seconds;
    if (pcpu > 99U) pcpu = 99U;
    return snprintf(outbuf, COLWID, "%2u", pcpu);
    """
    pcpu = 0
    total_time = utime + stime
    total_time += cutime + cstime
    seconds = uptime - (start_time / Hertz)
    if seconds:
        pcpu = total_time * 100 / Hertz / seconds
    return round(min(pcpu, 99.0), 1)
