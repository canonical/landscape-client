import os.path

from landscape.lib import sysstats
from landscape.client.monitor.plugin import MonitorPlugin


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

        times = sysstats.BootTimes(filename,
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
