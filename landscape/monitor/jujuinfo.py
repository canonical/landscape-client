import json
import logging
import os.path

from landscape.monitor.plugin import MonitorPlugin

class JujuInfo(MonitorPlugin):
    """Plugin for reporting Juju information."""

    persist_name = "juju-info"
    scope = "computer"

    def __init__(self, juju_info_filename=None):
        self._juju_info_filename = juju_info_filename

    def register(self, registry):
        super(JujuInfo, self).register(registry)
        if self._juju_info_filename is None:
            self._juju_info_filename = os.path.join(
                registry.config.data_path, "juju-info.json")
        self.call_on_accepted("juju-info", self.send_juju_message, True)

    def exchange(self, urgent=False):
        broker = self.registry.broker
        broker.call_if_accepted("juju-info", self.send_juju_message, urgent)

    def send_juju_message(self, urgent=False):
        message = {}
        juju_data = self._create_juju_info_message()
        if juju_data:
            message["type"] = "juju-info"
            message["data"] = juju_data
            logging.info("Queuing message with updated juju info.")
            self.registry.broker.send_message(message, self._session_id,
                                              urgent=urgent)

    def _create_juju_info_message(self):
        message = self._get_juju_info()
        if message != self._persist.get("juju-info"):
            self._persist.set("juju-info", message)
            return message
        return None

    def _get_juju_info(self):
        if not os.path.isfile(self._juju_info_filename):
            return None
        with open(self._juju_info_filename, "r") as json_file:
            try:
                juju_info = json.load(json_file)
            except Exception:
                return None
            else:
                return juju_info

