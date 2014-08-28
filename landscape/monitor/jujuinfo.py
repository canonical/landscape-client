import logging

from landscape.lib.juju import get_juju_info
from landscape.monitor.plugin import MonitorPlugin


class JujuInfo(MonitorPlugin):
    """Plugin for reporting Juju information.

    XXX this plugin is going to be dropped when the transition from
    unit-computer association to machine-computer association is
    completed on the server.
    """

    persist_name = "juju-info"
    scope = "juju"
    run_interval = 30

    # Need persist to be setup so have to wait C{run_interval} seconds
    run_immediately = False

    def run(self):
        broker = self.registry.broker
        broker.call_if_accepted("juju-units-info", self.send_juju_message)

    def send_juju_message(self):
        message = self._create_juju_info_message()
        if message:
            logging.info("Queuing message with updated juju info.")
            self.registry.broker.send_message(message, self._session_id,
                                              urgent=True)

    def _create_juju_info_message(self):
        """Return a "juju-units-info" message if the juju info gathered from
        the JSON files living in juju-info.d/ has changed.

        The message is of the form:
            {"type": "juju-units-info",
             "juju-info-list": [{<juju-info dict>}, {<juju-info dict>}]}
        """
        juju_info = get_juju_info(self.registry.config)

        if juju_info:
            juju_info = juju_info[0]

        if juju_info != self._persist.get("juju-info"):
            self._persist.set("juju-info", juju_info)
            message = {"type": "juju-units-info",
                       "juju-info-list": juju_info}
            return message

        return None
