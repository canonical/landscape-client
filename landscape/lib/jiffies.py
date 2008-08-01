import os


def detect_jiffies():
    """Returns the number of jiffies per second for this machine.

    A jiffy is a value used by the kernel to report certain time-based
    events.  Jiffies occur N times per second where N varies depending
    on the hardware the kernel is running on.  This function gets the
    uptime for the current process, forks a child process and gets the
    uptime again; finally, using the running time of the child process
    compared with the uptimes to determine number of jiffies per
    second.
    """
    uptime1_file = open("/proc/uptime")
    uptime2_file = open("/proc/uptime")
    read_uptime1 = uptime1_file.read
    read_uptime2 = uptime2_file.read

    while True:
        uptime1_data = read_uptime1()

        # Fork a process and exit immediately; this results in the
        # child process being left around as a zombie until waitpid()
        # is called.
        pid = os.fork()
        if pid == 0:
            os._exit(0)

        uptime2_data = read_uptime2()

        stat_file = open("/proc/%d/stat" % pid)
        stat_data = stat_file.read()
        stat_file.close()

        os.waitpid(pid, 0)

        seconds_uptime1 = float(uptime1_data.split()[0])
        seconds_uptime2 = float(uptime2_data.split()[0])
        jiffie_uptime = int(stat_data.split()[21])

        jiffies1 = int(jiffie_uptime/seconds_uptime1+0.5)
        jiffies2 = int(jiffie_uptime/seconds_uptime2+0.5)

        if jiffies1 == jiffies2:
            break

        uptime1_file.seek(0)
        uptime2_file.seek(0)

    uptime1_file.close()
    uptime2_file.close()
    return jiffies1
