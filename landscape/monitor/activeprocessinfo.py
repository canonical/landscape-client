import os
import subprocess

from landscape.lib.process import ProcessInformation
from landscape.jiffies import detect_jiffies
from landscape.monitor.monitor import DataWatcher


class ActiveProcessInfo(DataWatcher):

    message_type = "active-process-info"

    def __init__(self, proc_dir="/proc", uptime=None, jiffies=None,
                 popen=subprocess.Popen):
        super(ActiveProcessInfo, self).__init__()
        self._proc_dir = proc_dir
        self._persist_processes = None
        self._persist_process_states = None
        self._previous_processes = set()
        self._previous_process_states = {}
        self._jiffies_per_sec = jiffies or detect_jiffies()
        self._popen = popen
        self._first_run = True
        self._process_info = ProcessInformation(proc_dir=proc_dir,
                                                jiffies=jiffies,
                                                boot_time=uptime)

    def register(self, manager):
        super(ActiveProcessInfo, self).register(manager)
        self.call_on_accepted(self.message_type, self.exchange, True)
        self.registry.reactor.call_on("resynchronize", self._resynchronize)

    def _resynchronize(self):
        """Resynchronize active process data."""
        self._first_run = True
        self._persist_processes = None
        self._persist_process_states = None
        self._previous_processes = set()
        self._previous_process_states = {}

    def get_message(self):
        message = {}
        processes = self._get_processes()
        killed_processes = None

        if self._first_run:
            message["kill-all-processes"] = True
        else:
            killed_processes = [pid for pid in self._previous_processes
                                if pid not in processes]

        # Gather new processes to report.  If we're reporting a
        # process that has changed to an interesting state make sure
        # we include it in the kill list, too.
        new_processes = [processes[pid] for pid in processes
                         if pid not in self._previous_processes]
        pids = set([process["pid"] for process in new_processes])
        for pid in processes:
            if (self._previous_process_states.get(pid, None) != "Z"
                and processes[pid]["state"] == "Z"):
                if pid not in pids:
                    new_processes.append(processes[pid])
                    killed_processes.append(pid)

        # Update cached values for use on the next run.
        self._persist_processes = set(processes.keys())
        self._persist_process_states = {}
        for pid in processes.iterkeys():
            self._persist_process_states[pid] = processes[pid]["state"]

        if killed_processes:
            message["kill-processes"] = killed_processes
        if new_processes:
            message["add-processes"] = new_processes
        if message:
            message["type"] = "active-process-info"
            return message
        return None

    def persist_data(self):
        self._first_run = False
        self._previous_processes = self._persist_processes
        self._previous_process_states = self._persist_process_states
        self._persist_processes = set()
        self._persist_process_states = {}

    def _get_processes(self):
        processes = {}
        for filename in os.listdir(self._proc_dir):
            try:
                process_id = int(filename)
            except ValueError:
                continue
            process_info = self._process_info.get_process_info(process_id)
            if process_info:
                if process_info["state"] != "X":
                    processes[process_info["pid"]] = process_info
        return processes
