"""
A monitor plugin that collects data on a machine's network devices.
"""

from landscape.monitor.plugin import DataWatcher
from landscape.lib.network import (
    get_active_device_info, get_active_device_speed)


class NetworkDevice(DataWatcher):

    message_type = "network-device"
    message_key = "devices"
    persist_name = message_type

    def __init__(self, device_info=get_active_device_info,
                 device_speed=get_active_device_speed):
        super(NetworkDevice, self).__init__()
        self._device_info = device_info
        self._device_speed = device_speed

    def register(self, registry):
        super(NetworkDevice, self).register(registry)
        self.call_on_accepted(self.message_type, self.exchange, True)

    def get_message(self):
        device_data = self._device_info()
        device_speed = self._device_speed()
        if (self._persist.get("device-data") != device_data or
            self._persist.get("device-speed") != device_speed):

            self._persist.set("device-data", device_data)
            self._persist.set("device-speed", device_speed)

            return {"type": self.message_type,
                    "devices": device_data,
                    "device-speeds": device_speed}
