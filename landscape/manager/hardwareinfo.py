import os

from twisted.internet.utils import getProcessOutput

from landscape.manager.plugin import ManagerPlugin


class HardwareInfoPlugin(ManagerPlugin):
    """A plugin to retrieve hardware information."""

    message_type = "hardware-info"
    run_interval = 60 * 60 * 6
    command = "/usr/bin/lshw"

    def run(self):
        return self.registry.broker.call_if_accepted(
            self.message_type, self.send_message)

    def send_message(self):
        result = getProcessOutput(
            self.command, args=["-xml", "-quiet"], env=os.environ, path=None)
        return result.addCallback(self._got_output)

    def _got_output(self, output):
        message = {"type": self.message_type, "data": output}
        return self.registry.broker.send_message(message)
