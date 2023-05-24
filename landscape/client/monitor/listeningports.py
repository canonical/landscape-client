import logging

from landscape.client.monitor.plugin import MonitorPlugin
from landscape.lib.security import get_listeningports


class ListeningPorts(MonitorPlugin):
    """Plugin captures information about listening ports."""

    persist_name = "listening-ports"
    scope = "security"
    run_interval = 60  # 1 minute
    run_immediately = True

    def send_message(self, urgent=False):
        ports = get_listeningports()
        if ports == self._persist.get("ports"):
            return
        self._persist.set("ports", ports)

        message = {
            "type": "listening-ports-info",
            "ports": [port.dict() for port in ports],
        }
        logging.info(
            "Queueing message with updated " "listening-ports status.",
        )
        return self.registry.broker.send_message(message, self._session_id)

    def run(self, urgent=False):
        """
        Send the listening-ports-info messages, if the server accepted them.
        """
        return self.registry.broker.call_if_accepted(
            "listening-ports-info",
            self.send_message,
        )
