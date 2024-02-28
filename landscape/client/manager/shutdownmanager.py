import logging

import dbus
from twisted.internet import reactor
from twisted.internet import task

from landscape.client.manager.plugin import FAILED
from landscape.client.manager.plugin import ManagerPlugin
from landscape.client.manager.plugin import SUCCEEDED


class ShutdownManager(ManagerPlugin):
    """
    Plugin that either shuts down or reboots the device.

    In both cases, the manager sends the success command
    before attempting the shutdown/reboot.
    With reboot - the call is instanteous but the success
    message will be send as soon as the device comes back up.

    For shutdown there is a 120 second delay between
    sending the success and firing the shutdown.
    This is usually sufficent.
    """

    def __init__(self, dbus_provider=None, shutdown_delay=120):
        if dbus_provider is None:
            self.dbus_sysbus = dbus.SystemBus()
        else:
            self.dbus_sysbus = dbus_provider.SystemBus()

        self.shutdown_delay = shutdown_delay

    def register(self, registry):
        super().register(registry)
        self.config = registry.config

        registry.register_message("shutdown", self._handle_shutdown)

    def _handle_shutdown(self, message, DBus_System_Bus=None):
        """
        Choose shutdown or reboot
        """
        operation_id = message["operation-id"]
        reboot = message["reboot"]

        if reboot:
            logging.info("Reboot Requested")
            deferred = self._respond_reboot_success(
                "Reboot requested of the system",
                operation_id,
            )
            return deferred
        else:
            logging.info("Shutdown Requested")
            deferred = self._respond_shutdown_success(
                "Shutdown requested of the system",
                operation_id,
            )
            return deferred

    def _Reboot(self, _, Dbus_System_bus=None):
        logging.info("Sending Reboot Command")

        bus_object = self.dbus_sysbus.get_object(
            "org.freedesktop.login1",
            "/org/freedesktop/login1",
        )
        bus_object.Reboot(
            True,
            dbus_interface="org.freedesktop.login1.Manager",
        )

    def _Shutdown(self):
        logging.info("Sending Shutdown Command")
        bus_object = self.dbus_sysbus.get_object(
            "org.freedesktop.login1",
            "/org/freedesktop/login1",
        )
        bus_object.PowerOff(
            True,
            dbus_interface="org.freedesktop.login1.Manager",
        )

    def _respond_reboot_success(self, data, operation_id):
        deferred = self._respond(SUCCEEDED, data, operation_id)
        deferred.addCallback(self._Reboot)
        deferred.addErrback(self._respond_fail)
        return deferred

    def _respond_shutdown_success(self, data, operation_id):
        deferred = self._respond(SUCCEEDED, data, operation_id)
        self.shutdown_deferred = task.deferLater(
            reactor,
            self.shutdown_delay,
            self._Shutdown,
        )
        deferred.addErrback(self._respond_fail)
        return deferred

    def _respond_fail(self, data, operation_id):
        logging.info("Shutdown/Reboot request failed.")
        deferred = self._respond(FAILED, data, operation_id)
        return deferred

    def _respond(self, status, data, operation_id):
        message = {
            "type": "operation-result",
            "status": status,
            "result-text": data,
            "operation-id": operation_id,
        }
        return self.registry.broker.send_message(
            message,
            self._session_id,
            True,
        )
