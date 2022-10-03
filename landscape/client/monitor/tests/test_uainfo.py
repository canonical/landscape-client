from unittest import mock

from landscape.client.monitor.uainfo import UaInfo
from landscape.client.tests.helpers import LandscapeTest, MonitorHelper


class UaInfoTest(LandscapeTest):
    """UA status info plugin tests."""

    helpers = [MonitorHelper]

    def setUp(self):
        super(UaInfoTest, self).setUp()
        self.mstore.set_accepted_types(["ua-info"])

    def test_ua_status(self):
        """Tests calling `ua status`."""
        plugin = UaInfo()
        self.monitor.add(plugin)

        with mock.patch("subprocess.run") as run_mock:
            run_mock.return_value = mock.Mock(
                stdout="\"This is a test\"",
            )
            plugin.exchange()

        messages = self.mstore.get_pending_messages()
        run_mock.assert_called_once()
        self.assertTrue(len(messages) > 0)
        self.assertTrue("ua-status" in messages[0])
        self.assertEqual(messages[0]["ua-status"],
                         "\"This is a test\"")

    def test_ua_status_no_ua(self):
        """Tests calling `ua status` when it is not installed."""
        plugin = UaInfo()
        self.monitor.add(plugin)

        with mock.patch("subprocess.run") as run_mock:
            run_mock.side_effect = FileNotFoundError()
            plugin.exchange()

        messages = self.mstore.get_pending_messages()
        run_mock.assert_called_once()
        self.assertTrue(len(messages) > 0)
        self.assertTrue("ua-status" in messages[0])
        self.assertIn("errors", messages[0]["ua-status"])
