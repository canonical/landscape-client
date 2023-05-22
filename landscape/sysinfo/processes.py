import os

from twisted.internet.defer import succeed


class Processes:
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
            status_path = os.path.join(self._proc_dir, pid, "stat")

            try:
                with open(status_path, "rb") as fd:
                    data = fd.read()
            except IOError:
                continue

            num_processes += 1

            if b"Z" == data.split(b" ", 3)[2]:
                num_zombies += 1

        if num_zombies:
            if num_zombies == 1:
                msg = "There is 1 zombie process."
            else:
                msg = f"There are {num_zombies:d} zombie processes."
            self._sysinfo.add_note(msg)
        self._sysinfo.add_header("Processes", str(num_processes))
        return succeed(None)
