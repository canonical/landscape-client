from unittest import mock

from landscape.client.monitor.ubuntuproinfo import UbuntuProInfo
from landscape.client.tests.helpers import LandscapeTest, MonitorHelper


class UbuntuProInfoTest(LandscapeTest):
    """Ubuntu Pro info plugin tests."""

    helpers = [MonitorHelper]

    def setUp(self):
        super(UbuntuProInfoTest, self).setUp()
        self.mstore.set_accepted_types(["ubuntu-pro-info"])

    def test_ubuntu_pro_info(self):
        """Tests calling `ua status`."""
        plugin = UbuntuProInfo()
        self.monitor.add(plugin)

        with mock.patch("subprocess.run") as run_mock:
            run_mock.return_value = mock.Mock(
                stdout="\"This is a test\"",
            )
            plugin.exchange()

        messages = self.mstore.get_pending_messages()
        run_mock.assert_called_once()
        self.assertTrue(len(messages) > 0)
        self.assertTrue("ubuntu-pro-info" in messages[0])
        self.assertEqual(messages[0]["ubuntu-pro-info"],
                         "\"This is a test\"")

    def test_ubuntu_pro_info_no_ua(self):
        """Tests calling `ua status` when it is not installed."""
        plugin = UbuntuProInfo()
        self.monitor.add(plugin)

        with mock.patch("subprocess.run") as run_mock:
            run_mock.side_effect = FileNotFoundError()
            plugin.exchange()

        messages = self.mstore.get_pending_messages()
        run_mock.assert_called_once()
        self.assertTrue(len(messages) > 0)
        self.assertTrue("ubuntu-pro-info" in messages[0])
        self.assertIn("errors", messages[0]["ubuntu-pro-info"])
