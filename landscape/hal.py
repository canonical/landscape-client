from dbus import Interface, SystemBus


class HALManager(object):

    def __init__(self, bus=None):
        self._bus = bus or SystemBus()
        manager = self._bus.get_object("org.freedesktop.Hal",
                                       "/org/freedesktop/Hal/Manager")
        self._manager = Interface(manager, "org.freedesktop.Hal.Manager")

    def get_devices(self):
        """
        Returns a list of HAL devices.
        """
        devices = []
        for udi in self._manager.GetAllDevices():
            device = self._bus.get_object("org.freedesktop.Hal", udi)
            device = Interface(device, "org.freedesktop.Hal.Device")
            device = HALDevice(device)
            devices.append(device)
        return devices


class HALDevice(object):

    def __init__(self, device):
        self._children = []
        self._device = device
        self.properties = device.GetAllProperties()
        self.udi = self.properties["info.udi"]
        self.parent = None

    def add_child(self, device):
        self._children.append(device)
        device.parent = self

    def get_children(self):
        return self._children
