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

        super(SnapMonitor, self).register(registry)

    def get_snap_config(self, snap_name):
        try:
            config = snap_http.get_conf(snap_name).result
        except SnapdHttpException as e:
            logging.warning(
                f"Unable to get config for snap {snap_name}: {e}",
            )
            config = {}
        return config

    def get_services(self):
        try:
            services = snap_http.get_apps(services_only=True).result
        except SnapdHttpException as e:
            logging.warning(f"Unable to list services: {e}")
            services = []
        services.sort(key=lambda x: x["name"])
        return services

    def get_data(self):
        try:
            snaps = snap_http.list().result
            snaps.sort(key=lambda x: x["id"])
        except SnapdHttpException as e:
            logging.error(f"Unable to list installed snaps: {e}")
            return

        config = snap_http.get_conf("landscape-client").result
        experimental = config.get("experimental", {})
        monitor_config = experimental.get("monitor-config", False)
        monitor_services = experimental.get("monitor-services", False)

        for i in range(len(snaps)):
            if monitor_config:
                config = self.get_snap_config(snaps[i]["name"])
                snaps[i]["config"] = json.dumps(config)

        message = {
            "type": "snaps",
            "snaps": {
                "installed": snaps,
            },
        }

        if monitor_services:
            message["snaps"]["services"] = self.get_services()

        # We get a lot of extra info from snapd. To avoid caching it all
        # or invalidating the cache on timestamp changes, we use Message
        # coercion to strip out the unnecessaries, then sort on the snap
        # IDs to order the list.
        data = SNAPS.coerce(message)
        return data["snaps"]
