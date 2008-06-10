from dbus import SystemBus, Interface

from landscape.hal import HALDevice, HALManager
from landscape.tests.helpers import LandscapeTest


class HALManagerTest(LandscapeTest):

    def setUp(self):
        super(HALManagerTest, self).setUp()
        self.bus = SystemBus()
        self.manager = HALManager()

    def test_get_devices(self):
        """
        A HALManager can return a flat list of devices.  All available
        devices should be included in the returned list.
        """
        devices = self.manager.get_devices()
        manager = self.bus.get_object("org.freedesktop.Hal",
                                      "/org/freedesktop/Hal/Manager")
        manager = Interface(manager, "org.freedesktop.Hal.Manager")
        expected_devices = manager.GetAllDevices()
        actual_devices = [device.udi for device in devices]
        self.assertEquals(set(expected_devices), set(actual_devices))


class MockHALManager(object):

    def __init__(self, devices):
        self.devices = devices

    def get_devices(self):
        return [HALDevice(device) for device in self.devices]


class MockRealHALDevice(object):

    def __init__(self, properties):
        self._properties = properties
        self.udi = properties.get("info.udi", "fake_udi")

    def GetAllProperties(self):
        return self._properties


class HALDeviceTest(LandscapeTest):

    def test_init(self):
        device = HALDevice(MockRealHALDevice({"info.udi": "wubble"}))
        self.assertEquals(device.properties, {"info.udi": "wubble"})
        self.assertEquals(device.udi, "wubble")
        self.assertEquals(device.parent, None)

    def test_add_child(self):
        parent = HALDevice(MockRealHALDevice({"info.udi": "wubble"}))
        child = HALDevice(MockRealHALDevice({"info.udi": "ooga"}))
        parent.add_child(child)
        self.assertEquals(parent.get_children(), [child])
        self.assertEquals(child.parent, parent)
