import json
import logging
import os.path

from landscape.lib.fs import read_file
from landscape.monitor.plugin import MonitorPlugin


class JujuInfo(MonitorPlugin):
    """Plugin for reporting Juju information."""

    persist_name = "juju-info"
    scope = "juju"

    def register(self, registry):
        super(JujuInfo, self).register(registry)
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
        juju_filename = self.registry.config.juju_filename
        if not os.path.isfile(juju_filename):
            return None
        json_contents = read_file(juju_filename)
        try:
            juju_info = json.loads(json_contents)
        except Exception:
            logging.exception(
                "Error attempting to read JSON from %s" % juju_filename)
            return None
        else:
            return juju_info
