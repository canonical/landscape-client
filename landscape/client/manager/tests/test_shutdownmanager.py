from unittest.mock import patch, Mock
from twisted.internet import task

from landscape.client.manager.shutdownmanager import ShutdownManager
from landscape.client.tests.helpers import LandscapeTest
from landscape.client.tests.helpers import ManagerHelper


class ShutdownManagerTest(LandscapeTest):

    helpers = [ManagerHelper]

    def setUp(self):
        super().setUp()

        self.broker_service.message_store.set_accepted_types(
            ["shutdown", "operation-result"],
        )
        self.broker_service.pinger.start()

        self.clock = task.Clock()
        self.plugin = ShutdownManager()
        self.manager.add(self.plugin)
        self.plugin.callLater = self.clock.callLater

        self.dbus_mock = patch(
            "landscape.client.manager.shutdownmanager.dbus").start()

    def test_reboot(self):
        bus_object = Mock()
        self.dbus_mock.SystemBus.return_value = bus_object

        message = {"type": "shutdown", "reboot": True, "operation-id": 100}
        deferred = self.plugin._handle_shutdown(message)

        def check(_):
            bus_object.get_object.assert_called_once()
            bus_object.Reboot.assert_called_once()

        return deferred

    def test_shutdown(self):
        bus_object = Mock()
        self.dbus_mock.SystemBus.return_value = bus_object

        message = {"type": "shutdown", "reboot": False, "operation-id": 100}
        deferred = self.plugin._handle_shutdown(message)

        self.clock.advance(self.plugin.shutdown_delay)

        def check(_):
            bus_object.get_object.assert_called_once()
            bus_object.PowerOff.assert_called_once()

        return deferred
