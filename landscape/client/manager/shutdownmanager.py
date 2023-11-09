import logging
import dbus

from twisted.internet import reactor

from landscape.client.manager.plugin import FAILED
from landscape.client.manager.plugin import ManagerPlugin
from landscape.client.manager.plugin import SUCCEEDED

class ShutdownManager(ManagerPlugin):
    """
    Plugin that either shuts down or reboots the device.

    In both cases, the manager sends the success command before attempting
    the shutdown/reboot.
    
    With reboot - the call is instanteous but the success message will be 
    send as soon as the device comes back up.
    
    For shutdown there is a 120 second delay between sending the success and
    firing the shutdown. This is usually sufficent.
    """
    
    def register(self, registry):
        super().register(registry)
        self.config = registry.config
        
        registry.register_message("shutdown", self._handle_shutdown)
        
    def _handle_shutdown(self, message):
        """
        Choose shutdown or reboot
        """
        operation_id = message["operation-id"]
        reboot = message["reboot"]
        
        if (reboot):
            logging.info("Reboot Requested")
            deferred = self._respond_reboot_success(
                "Reboot requested of the system",
                operation_id)
            return deferred
        else:
            logging.info("Shutdown Requested")
            deferred = self._respond_shutdown_success(
                "Shutdown requested of the system",
                operation_id)
            return deferred
            
    def _Reboot(self, _):
        logging.info("Sending Reboot Command")
        bus = dbus.SystemBus()
        bus_object = bus.get_object(
            "org.freedesktop.login1", 
            "/org/freedesktop/login1")
        bus_object.Reboot(True, dbus_interface="org.freedesktop.login1.Manager")
        
    def _Shutdown(self):
        logging.info("Sending Shutdown Command")
        bus = dbus.SystemBus()
        bus_object = bus.get_object(
            "org.freedesktop.login1",
            "/org/freedesktop/login1")
        bus_object.PowerOff(True, dbus_interface="org.freedesktop.login1.Manager")

    def _respond_reboot_success(self, data, operation_id):
        deferred = self._respond(SUCCEEDED, data, operation_id)
        deferred.addCallback(self._Reboot)
        deferred.addErrback(self._respond_fail)
        return deferred

    def _respond_shutdown_success(self, data, operation_id):
        deferred = self._respond(SUCCEEDED, data, operation_id)
        reactor.callLater(120, self._Shutdown)
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
