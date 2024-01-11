from unittest.mock import patch

from landscape.client.monitor.snapmonitor import SnapMonitor
from landscape.client.tests.helpers import LandscapeTest
from landscape.client.tests.helpers import MonitorHelper

try:
    from snap_http import SnapdHttpException
except ImportError:
    from landscape.client.snap.http import SnapdHttpException


class SnapMonitorTest(LandscapeTest):
    """Snap plugin tests."""

    helpers = [MonitorHelper]

    def setUp(self):
        super(SnapMonitorTest, self).setUp()
        self.mstore.set_accepted_types(["snaps"])

    def test_get_data(self):
        """Tests getting installed snap data."""
        plugin = SnapMonitor()
        self.monitor.add(plugin)

        plugin.exchange()

        messages = self.mstore.get_pending_messages()

        self.assertTrue(len(messages) > 0)
        self.assertIn("installed", messages[0]["snaps"])

    def test_get_data_snapd_http_exception(self):
        """
        Tests that we return no data if there is an error getting it.
        """
        plugin = SnapMonitor()
        self.monitor.add(plugin)

        with patch(
            "landscape.client.monitor.snapmonitor.snap_http",
        ) as snap_http_mock, self.assertLogs(level="ERROR") as cm:
            snap_http_mock.list.side_effect = SnapdHttpException
            plugin.exchange()

        messages = self.mstore.get_pending_messages()

        self.assertEqual(len(messages), 0)
        self.assertEqual(
            cm.output,
            ["ERROR:root:Unable to list installed snaps: "],
        )
