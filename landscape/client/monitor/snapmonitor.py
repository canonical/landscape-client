import logging

from landscape.client.monitor.plugin import DataWatcher
from landscape.client.snap.http import SnapdHttpException
from landscape.client.snap.http import SnapHttp
from landscape.message_schemas.server_bound import SNAPS


class SnapMonitor(DataWatcher):

    message_type = "snaps"
    message_key = message_type
    persist_name = message_type
    scope = "snaps"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self._snap_http = SnapHttp()

    def register(self, registry):
        self.config = registry.config
        # The default interval is 30 minutes.
        self.run_interval = self.config.snap_monitor_interval

        super(SnapMonitor, self).register(registry)

    def get_data(self):
        try:
            snaps = self._snap_http.get_snaps()
        except SnapdHttpException as e:
            logging.error(f"Unable to list installed snaps: {e}")
            return

        # We get a lot of extra info from snapd. To avoid caching it all
        # or invalidating the cache on timestamp changes, we use Message
        # coercion to strip out the unnecessaries, then sort on the snap
        # IDs to order the list.
        data = SNAPS.coerce(
            {"type": "snaps", "snaps": {"installed": snaps["result"]}},
        )
        data["snaps"]["installed"].sort(key=lambda x: x["id"])

        return data["snaps"]
