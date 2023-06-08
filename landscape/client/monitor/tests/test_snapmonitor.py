from unittest.mock import Mock

from landscape.client.monitor.snapmonitor import SnapMonitor
from landscape.client.snap.http import SnapdHttpException, SnapHttp
from landscape.client.tests.helpers import LandscapeTest, MonitorHelper


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
        snap_http_mock = Mock(
            spec=SnapHttp,
            get_snaps=Mock(side_effect=SnapdHttpException)
        )
        plugin = SnapMonitor()
        plugin._snap_http = snap_http_mock
        self.monitor.add(plugin)

        with self.assertLogs(level="ERROR") as cm:
            plugin.exchange()

        messages = self.mstore.get_pending_messages()

        self.assertEqual(len(messages), 0)
        self.assertEqual(
            cm.output,
            ["ERROR:root:Unable to list installed snaps: "]
        )
