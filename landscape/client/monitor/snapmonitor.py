import logging

from landscape.client.monitor.plugin import DataWatcher
from landscape.client.snap.http import SnapdHttpException
from landscape.client.snap.http import SnapHttp


class SnapMonitor(DataWatcher):

    run_interval = 1800  # 30 minutes
    message_type = "snaps"
    message_key = message_type
    persist_name = message_type
    scope = "snaps"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self._snap_http = SnapHttp()

    def register(self, registry):
        self.config = registry.config
        self.run_interval = self.config.snap_monitor_interval

        super(SnapMonitor, self).register(registry)

    def get_data(self):
        return get_installed_snaps(self._snap_http)


def get_installed_snaps(snap_http):
    try:
        snaps = snap_http.get_snaps()
    except SnapdHttpException as e:
        logging.error(f"Unable to list installed snaps: {e}")
        return

    return {"installed": snaps["result"]}
