import json
import logging

from landscape.client import snap_http
from landscape.client.monitor.plugin import DataWatcher
from landscape.client.snap_http import SnapdHttpException
from landscape.message_schemas.server_bound import SNAPS


class SnapMonitor(DataWatcher):

    message_type = "snaps"
    message_key = message_type
    persist_name = message_type
    scope = "snaps"

    def register(self, registry):
        self.config = registry.config
        # The default interval is 30 minutes.
        self.run_interval = self.config.snap_monitor_interval

        super().register(registry)

    def get_data(self):
        try:
            snaps = snap_http.list().result
        except SnapdHttpException as e:
            logging.error(f"Unable to list installed snaps: {e}")
            return

        for i in range(len(snaps)):
            snap_name = snaps[i]["name"]
            try:
                config = snap_http.get_conf(snap_name).result
            except SnapdHttpException as e:
                logging.warning(
                    f"Unable to get config for snap {snap_name}: {e}",
                )
                config = {}

            snaps[i]["config"] = json.dumps(config)

        # We get a lot of extra info from snapd. To avoid caching it all
        # or invalidating the cache on timestamp changes, we use Message
        # coercion to strip out the unnecessaries, then sort on the snap
        # IDs to order the list.
        data = SNAPS.coerce(
            {
                "type": "snaps",
                "snaps": {"installed": snaps},
            },
        )
        data["snaps"]["installed"].sort(key=lambda x: x["id"])

        return data["snaps"]
