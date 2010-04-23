"""
A monitor plugin that collects data on a machine's network devices.
"""

from landscape.monitor.monitor import DataWatcher
from landscape.lib.network import get_active_device_info


class NetworkDevice(DataWatcher):

    message_type = "network-device"
    message_key = "devices"
    persist_name = message_type

    def __init__(self, device_info=get_active_device_info):
        super(NetworkDevice, self).__init__()
        self._device_info = device_info

    def register(self, registry):
        super(NetworkDevice, self).register(registry)
        self.call_on_accepted(self.message_type, self.exchange, True)
        self.registry.reactor.call_on("resynchronize", self._resynchronize)

    def _resynchronize(self):
        """Resynchronize active network device information."""
        self._persist.set("data", [])

    def get_data(self):
        return self._device_info()
