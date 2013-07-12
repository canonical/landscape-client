"""
A monitor plugin that collects data on a machine's network devices.
"""

from landscape.monitor.plugin import DataWatcher
from landscape.lib.network import get_active_device_info


class NetworkDevice(DataWatcher):

    message_type = "network-device"
    message_key = "devices"
    persist_name = message_type
    scope = "network"

    def __init__(self, device_info=get_active_device_info):
        super(NetworkDevice, self).__init__()
        self._device_info = device_info

    def register(self, registry):
        super(NetworkDevice, self).register(registry)
        self.call_on_accepted(self.message_type, self.exchange, True)

    def get_message(self):
        device_data = self._device_info()
        # Persist if the info is new.
        if self._persist.get("network-device-data") != device_data:
            self._persist.set("network-device-data", device_data)
            # We need to split the message in two top-level keys (see bug)
            device_speeds = []
            for device in device_data:
                speed_entry = {"interface": device["interface"]}
                speed_entry["speed"] = device.pop("speed")
                speed_entry["duplex"] = device.pop("duplex")
                device_speeds.append(speed_entry)

            return {"type": self.message_type,
                    "devices": device_data,
                    "device-speeds": device_speeds}
