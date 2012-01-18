import dbus

from landscape.ui.model.registration.mechanism import (
    SERVICE_NAME, INTERFACE_NAME, OBJECT_PATH)


class RegistrationProxy(object):

    def __init__(self, bus=None):
        self._interface = None
        self._setup_interface(bus)

    def _setup_interface(self, bus):
        """
        Redefining L{_setup_interface} allows us to bypass DBus for more
        convenient testing in some instances.
        """
        if bus is None:
            self._bus = dbus.SystemBus()
        else:
            self._bus = bus
        self._remote_object = self._bus.get_object(SERVICE_NAME, OBJECT_PATH)
        self._interface = dbus.Interface(self._remote_object, INTERFACE_NAME)

    def register(self, config_path):
        return self._interface.register(config_path)

    def poll(self):
        return self._interface.poll()
