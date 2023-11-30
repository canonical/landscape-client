from unittest.mock import Mock

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

        self.dbus_mock = Mock()
        self.dbus_sysbus_mock = Mock()
        self.dbus_mock.get_object.return_value = self.dbus_sysbus_mock
        self.plugin = ShutdownManager(dbus=self.dbus_mock, shutdown_delay=0)
        self.manager.add(self.plugin)

    def test_reboot(self):
        message = {"type": "shutdown", "reboot": True, "operation-id": 100}
        deferred = self.plugin._handle_shutdown(message)

        def check(_):
            self.plugin.dbus_sysbus.get_object.assert_called_once()
            self.plugin.dbus_sysbus.get_object().Reboot.assert_called_once()

        deferred.addCallback(check)
        return deferred

    def test_shutdown(self):
        message = {"type": "shutdown", "reboot": False, "operation-id": 100}
        deferred = self.plugin._handle_shutdown(message)

        def check(_):
            self.plugin.dbus_sysbus.get_object.assert_called_once()
            self.plugin.dbus_sysbus.get_object().PowerOff.assert_called_once()

        self.plugin.shutdown_deferred.addCallback(check)
        return deferred
