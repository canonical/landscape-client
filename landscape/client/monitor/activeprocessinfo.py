import subprocess

from twisted.python.compat import itervalues

from landscape.client.diff import diff
from landscape.lib.process import ProcessInformation
from landscape.lib.jiffies import detect_jiffies
from landscape.client.monitor.plugin import DataWatcher


class ActiveProcessInfo(DataWatcher):

    message_type = "active-process-info"
    scope = "process"

    def __init__(self, proc_dir="/proc", boot_time=None, jiffies=None,
                 uptime=None, popen=subprocess.Popen):
        super(ActiveProcessInfo, self).__init__()
        self._proc_dir = proc_dir
        self._persist_processes = {}
        self._previous_processes = {}
        self._jiffies_per_sec = jiffies or detect_jiffies()
        self._popen = popen
        self._first_run = True
        self._process_info = ProcessInformation(proc_dir=proc_dir,
                                                jiffies=jiffies,
                                                boot_time=boot_time,
                                                uptime=uptime)

    def register(self, manager):
        super(ActiveProcessInfo, self).register(manager)
        self.call_on_accepted(self.message_type, self.exchange, True)

    def _reset(self):
        """Reset active process data."""
        self._first_run = True
        self._persist_processes = {}
        self._previous_processes = {}

    def get_message(self):
        message = {}
        if self._first_run:
            message["kill-all-processes"] = True
        message.update(self._detect_process_changes())

        if message:
            message["type"] = "active-process-info"
            return message
        return None

    def persist_data(self):
        self._first_run = False
        self._persist_processes = self._previous_processes
        self._previous_processes = {}
        # This forces the registry to write the persistent store to disk
        # This means that the persistent data reflects the state of the
        # messages sent.
        self.registry.flush()

    def _get_processes(self):
        processes = {}
        for process_info in self._process_info.get_all_process_info():
            if process_info["state"] != b"X":
                processes[process_info["pid"]] = process_info
        return processes

    def _detect_process_changes(self):
        changes = {}
        processes = self._get_processes()
        creates, updates, deletes = diff(self._persist_processes, processes)
        if creates:
            changes["add-processes"] = list(itervalues(creates))
        if updates:
            changes["update-processes"] = list(itervalues(updates))
        if deletes:
            changes["kill-processes"] = list(deletes)

        # Update cached values for use on the next run.
        self._previous_processes = processes
        return changes
