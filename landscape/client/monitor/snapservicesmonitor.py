import logging

from landscape.client import snap_http
from landscape.client.monitor.plugin import DataWatcher
from landscape.client.snap_http import SnapdHttpException


class SnapServicesMonitor(DataWatcher):

    message_type = "snap-services"
    message_key = "services"
    persist_name = message_type
    scope = "snaps"

    def register(self, registry):
        self.config = registry.config
        self.run_interval = 60  # 1 minute
        super().register(registry)

    def get_data(self):
        try:
            services = snap_http.get_apps(services_only=True).result
        except SnapdHttpException as e:
            logging.warning(f"Unable to list services: {e}")
            services = []
        services.sort(key=lambda x: x["name"])

        return {"running": services}
