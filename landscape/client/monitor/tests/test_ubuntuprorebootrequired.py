from landscape.client.monitor.ubuntuprorebootrequired import (
    UbuntuProRebootRequired,
)
from landscape.client.tests.helpers import LandscapeTest, MonitorHelper


class UbuntuProRebootRequiredTest(LandscapeTest):
    """Ubuntu Pro required plugin tests."""

    helpers = [MonitorHelper]

    def setUp(self):
        super().setUp()
        self.mstore.set_accepted_types(["ubuntu-pro-reboot-required"])

    def test_ubuntu_pro_reboot_required(self):
        """Tests calling reboot required."""

        plugin = UbuntuProRebootRequired()
        self.monitor.add(plugin)
        plugin.exchange()

        messages = self.mstore.get_pending_messages()

        self.assertGreater(len(messages), 0)
        self.assertIn("ubuntu-pro-reboot-required", messages[0])
        self.assertIn(
            "reboot_required", messages[0]["ubuntu-pro-reboot-required"]
        )
