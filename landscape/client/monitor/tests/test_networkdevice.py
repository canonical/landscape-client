import mock

from landscape.client.tests.helpers import LandscapeTest, MonitorHelper
from landscape.lib.network import (
    get_active_device_info)
from landscape.client.monitor.networkdevice import NetworkDevice


def test_get_active_device_info():
    # Don't skip any interfaces for the tests
    return get_active_device_info(skipped_interfaces=())


class NetworkDeviceTest(LandscapeTest):

    helpers = [MonitorHelper]

    def setUp(self):
        super(NetworkDeviceTest, self).setUp()
        self.plugin = NetworkDevice(test_get_active_device_info)
        self.monitor.add(self.plugin)
        self.broker_service.message_store.set_accepted_types(
            [self.plugin.message_type])

    def test_get_network_device(self):
        """A message is sent with device info"""
        self.plugin.exchange()
        message = self.mstore.get_pending_messages()[0]
        self.assertEqual(message["type"], "network-device")
        self.failUnlessIn("devices", message)
        self.assertTrue(len(message["devices"]))
        # only network device we can truly assert is localhost
        self.assertTrue(message["devices"][0]["interface"], "lo")
        self.assertTrue(message["devices"][0]["ip_address"], "0.0.0.0")
        self.assertTrue(message["devices"][0]["netmask"], "255.0.0.0")
        flags = message["devices"][0]["flags"]
        self.assertEqual(1, flags & 1)  # UP
        self.assertEqual(8, flags & 8)  # LOOPBACK
        self.assertEqual(64, flags & 64)  # RUNNING

    def test_no_message_with_no_changes(self):
        """If no device changes from the last message, no message is sent."""
        self.plugin.exchange()
        self.mstore.delete_all_messages()
        self.plugin.exchange()
        self.assertFalse(self.mstore.count_pending_messages())

    def test_message_on_device_change(self):
        """When the active network devices change a message is generated."""
        self.plugin.exchange()
        self.mstore.delete_all_messages()
        with mock.patch.object(self.plugin, "_device_info", return_value=[]):
            self.plugin.exchange()
            self.assertEqual(1, self.mstore.count_pending_messages())

    def test_config(self):
        """The network device plugin is enabled by default."""
        self.assertIn("NetworkDevice", self.config.plugin_factories)
