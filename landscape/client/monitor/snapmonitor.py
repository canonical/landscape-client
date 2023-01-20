from landscape.client import snap
from landscape.client.monitor.plugin import MonitorPlugin


class SnapMonitor(MonitorPlugin):

    message_type = "snaps"
    run_interval = 1800
    scope = "snaps"

    _reporter_command = None

    def register(self, registry):
        self.config = registry.config
        self.run_interval = self.config.snap_monitor_interval

        super(SnapMonitor, self).register(registry)

    def get_data(self):
        return snap.http.get_snaps()
