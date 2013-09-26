import logging

from landscape.lib.juju import get_juju_info
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
        message = self._create_juju_info_message()
        if message:
            message["type"] = "juju-info"
            logging.info("Queuing message with updated juju info.")
            self.registry.broker.send_message(message, self._session_id,
                                              urgent=urgent)

    def _create_juju_info_message(self):
        message = get_juju_info(self.registry.config)
        if message is not None:
            message["api-addresses"] = message["api-addresses"].split()
        if message != self._persist.get("juju-info"):
            self._persist.set("juju-info", message)
            return message
        return None
