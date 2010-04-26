import logging

from twisted.internet.defer import succeed

from landscape.lib.log import log_failure

from landscape.diff import diff
from landscape.hal import HALManager
from landscape.monitor.plugin import MonitorPlugin


class HardwareInventory(MonitorPlugin):

    persist_name = "hardware-inventory"

    def __init__(self, hal_manager=None):
        super(HardwareInventory, self).__init__()
        self._persist_sets = []
        self._persist_removes = []
        self._hal_manager = hal_manager or HALManager()

    def register(self, manager):
        super(HardwareInventory, self).register(manager)
        manager.reactor.call_on("resynchronize", self._resynchronize)
        self.call_on_accepted("hardware-inventory", self.exchange, True)

    def _resynchronize(self):
        self._persist.remove("devices")

    def send_message(self, urgent):
        devices = self.create_message()
        if devices:
            message = {"type": "hardware-inventory", "devices": devices}
            result = self.registry.broker.send_message(message, urgent=urgent)
            result.addCallback(self.persist_data)
            result.addErrback(log_failure)
            logging.info("Queueing a message with hardware-inventory "
                         "information.")
        else:
            result = succeed(None)
        return result

    def exchange(self, urgent=False):
        return self.registry.broker.call_if_accepted("hardware-inventory",
                                                     self.send_message, urgent)

    def persist_data(self, message_id):
        for key, udi, value in self._persist_sets:
            self._persist.set((key, udi), value)
        for key in self._persist_removes:
            self._persist.remove(key)
        del self._persist_sets[:]
        del self._persist_removes[:]
        # This forces the registry to write the persistent store to disk
        # This means that the persistent data reflects the state of the
        # messages sent.
        self.registry.flush()

    def create_message(self):
        # FIXME Using persist to keep track of changes here uses a
        # fair amount of memory.  On my machine a rough test seemed to
        # indicate that memory usage grew by 1.3mb, about 12% of the
        # overall process size.  Look here to save memory.
        del self._persist_sets[:]
        del self._persist_removes[:]
        devices = []
        previous_devices = self._persist.get("devices", {})
        current_devices = set()

        for device in self._hal_manager.get_devices():
            previous_properties = previous_devices.get(device.udi)
            if not previous_properties:
                devices.append(("create", device.properties))
            elif previous_properties != device.properties:
                creates, updates, deletes = diff(previous_properties,
                                                 device.properties)
                devices.append(("update", device.udi,
                                creates, updates, deletes))
            current_devices.add(device.udi)
            self._persist_sets.append(
                ("devices", device.udi, device.properties))

        items_with_parents = {}
        deleted_devices = set()
        for udi, value in previous_devices.iteritems():
            if udi not in current_devices:
                if "info.parent" in value:
                    items_with_parents[udi] = value["info.parent"]
                deleted_devices.add(udi)

        # We remove the deleted devices from our persistent store it's
        # only the information we're sending to the server that we're
        # compressing.
        for udi in deleted_devices:
            self._persist_removes.append(("devices", udi))

        # We can now flatten the list of devices we send to the server
        # For each of the items_with_parents, if both the item and it's parent
        # are in the deleted_devices set, then we can remove this item from the
        # set.
        minimal_deleted_devices = deleted_devices.copy()
        for child, parent in items_with_parents.iteritems():
            if child in deleted_devices and parent in deleted_devices:
                minimal_deleted_devices.remove(child)
        # We now build the deleted devices message
        for udi in minimal_deleted_devices:
            devices.append(("delete", udi))

        return devices
