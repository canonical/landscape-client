import os

from twisted.internet.defer import succeed


class Processes(object):

    def __init__(self, proc_dir="/proc"):
        self._proc_dir = proc_dir

    def register(self, sysinfo):
        self._sysinfo = sysinfo

    def run(self):
        num_processes = 0
        num_zombies = 0
        for pid in os.listdir(self._proc_dir):
            if not pid.isdigit():
                continue
            status_path = os.path.join(self._proc_dir, pid, "status")
            try:
                fd = os.open(status_path, os.O_RDONLY)
                try:
                    data = os.read(fd, 2048)
                finally:
                    os.close(fd)
            except IOError:
                continue
            num_processes += 1
            if b'State:\tZ' in data:
                num_zombies += 1
        if num_zombies:
            if num_zombies == 1:
                msg = "There is 1 zombie process."
            else:
                msg = "There are %d zombie processes." % (num_zombies,)
            self._sysinfo.add_note(msg)
        self._sysinfo.add_header("Processes", str(num_processes))
        return succeed(None)
