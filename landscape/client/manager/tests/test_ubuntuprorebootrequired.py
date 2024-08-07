import json
from unittest.mock import patch

from landscape.client.manager.ubuntuprorebootrequired import (
    UbuntuProRebootRequired,
)
from landscape.client.tests.helpers import LandscapeTest, ManagerHelper


class UbuntuProRebootRequiredTest(LandscapeTest):
    """Ubuntu Pro required plugin tests."""

    helpers = [ManagerHelper]

    def setUp(self):
        super().setUp()
        self.mstore = self.broker_service.message_store
        self.mstore.set_accepted_types(["ubuntu-pro-reboot-required"])

    @patch('landscape.client.manager.ubuntuprorebootrequired.get_reboot_info')
    def test_ubuntu_pro_reboot_required(self, mock_reboot_info):
        """Basic test"""

        mock_reboot_info.return_value = "reboot_required"
        plugin = UbuntuProRebootRequired()
        self.manager.add(plugin)
        plugin.run()

        messages = self.mstore.get_pending_messages()

        self.assertGreater(len(messages), 0)
        self.assertIn("ubuntu-pro-reboot-required", messages[0])
        info = json.loads(messages[0]["ubuntu-pro-reboot-required"])
        self.assertEqual("reboot_required", info["output"])
        self.assertFalse(info["error"])

    @patch('landscape.client.manager.ubuntuprorebootrequired.get_reboot_info')
    @patch('landscape.client.manager.ubuntuprorebootrequired.logging.error')
    def test_generic_error(self, mock_logger, mock_reboot_info):
        """
        Test we get a response and an error is logged when exception triggers
        """

        mock_reboot_info.side_effect = Exception("Error!")

        plugin = UbuntuProRebootRequired()
        self.manager.add(plugin)
        plugin.run()

        messages = self.mstore.get_pending_messages()

        mock_logger.assert_called()
        self.assertGreater(len(messages), 0)
        self.assertIn("ubuntu-pro-reboot-required", messages[0])
        info = json.loads(messages[0]["ubuntu-pro-reboot-required"])
        self.assertFalse(info["output"])
        self.assertTrue(info["error"])
