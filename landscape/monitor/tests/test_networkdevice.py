
#import subprocess
from landscape.tests.helpers import LandscapeTest, MonitorHelper
from landscape.monitor.networkdevice import NetworkDevice


class NetworkDeviceTest(LandscapeTest):

    helpers = [MonitorHelper]

    def test_get_network_device(self):
        """A message is sent with device info"""
        plugin = NetworkDevice()
        self.monitor.add(plugin)
        self.broker_service.message_store.set_accepted_types(
            [plugin.message_type])
        plugin.exchange()
        message = self.mstore.get_pending_messages()[0]
        self.assertEquals(message["type"], "network-device")
        self.failUnlessIn("devices", message)
        self.assertTrue(len(message["devices"]))

    def test_no_message_with_no_changes(self):
        """If no device changes from the last message, no message is sent."""

    def test_message_on_device_change(self):
        """When the active network devices change a message is generated."""
