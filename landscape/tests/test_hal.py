from dbus import SystemBus, Interface
from dbus.exceptions import DBusException

from landscape.hal import HALDevice, HALManager
from landscape.tests.helpers import LandscapeTest


class HALManagerTest(LandscapeTest):

    def setUp(self):
        super(HALManagerTest, self).setUp()
        self.bus = SystemBus()

    def test_get_devices(self):
        """
        A HALManager can return a flat list of devices.  All available
        devices should be included in the returned list.
        """
        devices = HALManager().get_devices()
        manager = self.bus.get_object("org.freedesktop.Hal",
                                      "/org/freedesktop/Hal/Manager")
        manager = Interface(manager, "org.freedesktop.Hal.Manager")
        expected_devices = manager.GetAllDevices()
        actual_devices = [device.udi for device in devices]
        self.assertEqual(set(expected_devices), set(actual_devices))

    def test_get_devices_with_dbus_error(self):
        """
        If the L{HALManager} fails connecting to HAL over D-Bus, then the
        L{HALManager.get_devices} method returns an empty list.
        """
        self.log_helper.ignore_errors("Couldn't to connect to Hal via DBus")
        bus = self.mocker.mock()
        bus.get_object("org.freedesktop.Hal", "/org/freedesktop/Hal/Manager")
        self.mocker.throw(DBusException())
        self.mocker.replay()
        devices = HALManager(bus=bus).get_devices()
        self.assertEqual(devices, [])

    def test_get_devices_with_no_server(self):
        """
        If the L{HALManager} fails connecting to HAL over D-Bus, for example
        because the DBus server is not running at all, then the
        L{HALManager.get_devices} method returns an empty list.
        """
        self.log_helper.ignore_errors("Couldn't to connect to Hal via DBus")
        bus_mock = self.mocker.replace("dbus.SystemBus")
        bus_mock()
        self.mocker.throw(DBusException())
        self.mocker.replay()
        devices = HALManager().get_devices()
        self.assertEqual(devices, [])


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
        self.assertEqual(device.properties, {"info.udi": "wubble"})
        self.assertEqual(device.udi, "wubble")
        self.assertEqual(device.parent, None)

    def test_add_child(self):
        parent = HALDevice(MockRealHALDevice({"info.udi": "wubble"}))
        child = HALDevice(MockRealHALDevice({"info.udi": "ooga"}))
        parent.add_child(child)
        self.assertEqual(parent.get_children(), [child])
        self.assertEqual(child.parent, parent)
