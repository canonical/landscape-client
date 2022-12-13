from unittest import mock

from landscape.client.monitor.livepatch import LivePatch
from landscape.client.tests.helpers import LandscapeTest, MonitorHelper


class LivePatchTest(LandscapeTest):
    """Livepatch status plugin tests."""

    helpers = [MonitorHelper]

    def setUp(self):
        super(LivePatchTest, self).setUp()
        self.mstore.set_accepted_types(["livepatch"])

    def test_livepatch(self):
        """Tests calling livepatch status."""
        plugin = LivePatch()
        self.monitor.add(plugin)

        with mock.patch("subprocess.run") as run_mock:
            run_mock.return_value = mock.Mock(stdout='Test')
            run_mock.return_value.returncode = 0
            plugin.exchange()

        messages = self.mstore.get_pending_messages()
        run_mock.assert_called_once()
        self.assertTrue(len(messages) > 0)
        self.assertTrue("livepatch" in messages[0])
        self.assertEqual(messages[0]["livepatch"]["output"], "Test")
        self.assertEqual(messages[0]["livepatch"]["code"], 0)

    def test_livepatch_when_not_installed(self):
        """Tests calling livepatch when it is not installed."""
        plugin = LivePatch()
        self.monitor.add(plugin)

        with mock.patch("subprocess.run") as run_mock:
            run_mock.side_effect = FileNotFoundError("Not found!")
            plugin.exchange()

        messages = self.mstore.get_pending_messages()
        run_mock.assert_called_once()
        self.assertTrue(len(messages) > 0)
        self.assertTrue("livepatch" in messages[0])
        self.assertTrue(messages[0]["livepatch"]["exception"])
        self.assertEqual(messages[0]["livepatch"]["code"], -1)

    def test_undefined_exception(self):
        """Tests calling livepatch when random exception occurs"""
        plugin = LivePatch()
        self.monitor.add(plugin)

        with mock.patch("subprocess.run") as run_mock:
            run_mock.side_effect = ValueError("Not found!")
            plugin.exchange()

        messages = self.mstore.get_pending_messages()
        run_mock.assert_called_once()
        self.assertTrue(len(messages) > 0)
        self.assertTrue("livepatch" in messages[0])
        self.assertTrue(messages[0]["livepatch"]["exception"])
        self.assertEqual(messages[0]["livepatch"]["code"], -2)
