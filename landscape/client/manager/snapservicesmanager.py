import logging

from landscape.client import snap_http
from landscape.client.manager.snapmanager import BaseSnapManager
from landscape.client.snap_http import SnapdHttpException


class SnapServicesManager(BaseSnapManager):
    """
    Plugin that updates the state of snap services on this machine, starting,
    stopping, restarting, enabling, disabling, and reloading them in response
    to messages.

    Changes trigger SnapServicesMonitor to send an updated state message
    immediately.
    """

    def __init__(self):
        super().__init__()

        self.SNAP_METHODS = {
            "start-snap-service": snap_http.start,
            "start-snap-service-batch": snap_http.start_all,
            "stop-snap-service": snap_http.stop,
            "stop-snap-service-batch": snap_http.stop_all,
            "restart-snap-service": snap_http.restart,
            "restart-snap-service-batch": snap_http.restart_all,
        }

    def register(self, registry):
        super().register(registry)
        self.config = registry.config

        message_types = [
            "start-snap-service",
            "start-snap-service-batch",
            "stop-snap-service",
            "stop-snap-service-batch",
            "restart-snap-service",
            "restart-snap-service-batch",
        ]
        for msg_type in message_types:
            registry.register_message(msg_type, self._handle_snap_task)

    def _send_snap_update(self):
        try:
            services = snap_http.get_apps(services_only=True).result
        except SnapdHttpException as e:
            logging.error(f"Unable to list services: {e}")
            return

        if services:
            return self.registry.broker.send_message(
                {
                    "type": "snap-services",
                    "services": {"running": services},
                },
                self._session_id,
                True,
            )
