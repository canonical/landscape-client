from twisted.internet.defer import succeed

from landscape.lib.process import ProcessInformation


class Processes(object):

    def __init__(self, proc_dir="/proc"):
        self._proc_dir = proc_dir

    def register(self, sysinfo):
        self._sysinfo = sysinfo

    def run(self):
        num_processes = 0
        num_zombies = 0
        info = ProcessInformation(proc_dir=self._proc_dir)
        for process_info in info.get_all_process_info():
            num_processes += 1
            if process_info["state"] == b"Z":
                num_zombies += 1
        if num_zombies:
            if num_zombies == 1:
                msg = "There is 1 zombie process."
            else:
                msg = "There are %d zombie processes." % (num_zombies,)
            self._sysinfo.add_note(msg)
        self._sysinfo.add_header("Processes", str(num_processes))
        return succeed(None)
