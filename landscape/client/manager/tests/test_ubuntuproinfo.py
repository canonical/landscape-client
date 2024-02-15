from unittest import mock

from landscape.client.manager.ubuntuproinfo import get_ubuntu_pro_info
from landscape.client.manager.ubuntuproinfo import UbuntuProInfo
from landscape.client.tests.helpers import LandscapeTest
from landscape.client.tests.helpers import MonitorHelper


class UbuntuProInfoTest(LandscapeTest):
    """Ubuntu Pro info plugin tests."""

    helpers = [MonitorHelper]

    def setUp(self):
        super().setUp()
        self.mstore.set_accepted_types(["ubuntu-pro-info"])

    def test_ubuntu_pro_info(self):
        """Tests calling `ua status`."""
        plugin = UbuntuProInfo()

        with mock.patch("subprocess.run") as run_mock:
            run_mock.return_value = mock.Mock(
                stdout='"This is a test"',
            )
            self.monitor.add(plugin)  # runs immediately
            plugin.run()

        run_mock.assert_called()
        messages = self.mstore.get_pending_messages()
        self.assertTrue(len(messages) > 0)
        self.assertTrue("ubuntu-pro-info" in messages[0])
        self.assertEqual(messages[0]["ubuntu-pro-info"], '"This is a test"')
        self.assertEqual(messages[1]["ubuntu-pro-info"], '"This is a test"')

    def test_ubuntu_pro_info_runs_immediately(self):
        """Tests that Ubuntu Pro status runs on registration"""
        plugin = UbuntuProInfo()

        with mock.patch("subprocess.run") as run_mock:
            run_mock.return_value = mock.Mock(
                stdout='"Registered"',
            )
            self.monitor.add(plugin)  # runs immediately

        run_mock.assert_called_once()
        messages = self.mstore.get_pending_messages()
        self.assertTrue(len(messages) > 0)
        self.assertTrue("ubuntu-pro-info" in messages[0])
        self.assertEqual(messages[0]["ubuntu-pro-info"], '"Registered"')

    def test_ubuntu_pro_info_no_ua(self):
        """Tests calling `ua status` when it is not installed."""
        plugin = UbuntuProInfo()
        self.monitor.add(plugin)

        with mock.patch("subprocess.run") as run_mock:
            run_mock.side_effect = FileNotFoundError()
            plugin.run()

        messages = self.mstore.get_pending_messages()
        run_mock.assert_called_once()
        self.assertTrue(len(messages) > 0)
        self.assertTrue("ubuntu-pro-info" in messages[0])
        self.assertIn("errors", messages[0]["ubuntu-pro-info"])

    def test_get_ubuntu_pro_info_core(self):
        """In Ubuntu Core, there is no pro info, so return a reasonable erro
        message.
        """
        with mock.patch(
            "landscape.client.manager.ubuntuproinfo.IS_CORE",
            new="1",
        ):
            result = get_ubuntu_pro_info()

        self.assertIn("errors", result)
        self.assertIn("not available", result["errors"][0]["message"])
        self.assertEqual(result["result"], "failure")