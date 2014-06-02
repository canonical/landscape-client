import logging

from landscape.lib.juju import get_juju_info
from landscape.monitor.plugin import MonitorPlugin


class JujuInfo(MonitorPlugin):
    """Plugin for reporting Juju information."""

    persist_name = "juju-info"
    scope = "juju"

    def register(self, registry):
        super(JujuInfo, self).register(registry)
        self.call_on_accepted("juju-units-info", self.send_juju_message, True)

    def exchange(self, urgent=False):
        broker = self.registry.broker
        broker.call_if_accepted(
            "juju-units-info", self.send_juju_message, urgent)

    def send_juju_message(self, urgent=False):
        message = self._create_juju_info_message()
        if message:
            logging.info("Queuing message with updated juju info.")
            self.registry.broker.send_message(message, self._session_id,
                                              urgent=urgent)

    def _create_juju_info_message(self):
        """Return a "juju-info" message if the juju info gathered from the JSON
        files living in juju-info.d/ has changed.

        The message is of the form:
            {"type": "juju-info",
             "juju-info": [{<juju-info dict>}, {<juju-info dict>}]}
        """
        juju_info = get_juju_info(self.registry.config)

        if juju_info != self._persist.get("juju-info"):
            self._persist.set("juju-info", juju_info)
            message = {"type": "juju-units-info",
                       "juju-units-info": juju_info}
            return message

        return None
