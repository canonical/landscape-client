import logging

from landscape.client.monitor.plugin import MonitorPlugin
from landscape.lib.security import RKHunterLogReader  # , RKHunterLiveInfo


class RKHunterInfo(MonitorPlugin):
    """Plugin captures information about rkhunter results."""

    persist_name = "rootkit-scan-info"
    scope = "security"
    run_interval = 86400  # 1 day
    run_immediately = True

    def __init__(self, filename="/var/log/rkhunter.log"):
        self._filename = filename

    def send_message(self, urgent=False):
        rklog = RKHunterLogReader(filename=self._filename)
        report = rklog.get_last_log()
        if report == self._persist.get("report"):
            return
        self._persist.set("report", report)

        message = {"type": "rootkit-scan-info", "report": report.dict()}
        logging.info(
            "Queueing message with updated rootkit-scan status.",
        )
        return self.registry.broker.send_message(message, self._session_id)

    def run(self, urgent=False):
        """
        Send the rootkit-scan-info messages, if the server accepted them.
        """
        return self.registry.broker.call_if_accepted(
            "rootkit-scan-info",
            self.send_message,
        )
