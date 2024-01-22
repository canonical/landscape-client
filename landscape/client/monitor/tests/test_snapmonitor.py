from unittest.mock import patch

from landscape.client.monitor.snapmonitor import SnapMonitor
from landscape.client.snap_http import SnapdHttpException
from landscape.client.snap_http import SnapdResponse
from landscape.client.tests.helpers import LandscapeTest
from landscape.client.tests.helpers import MonitorHelper


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

    @patch("landscape.client.monitor.snapmonitor.snap_http")
    def test_get_snap_config(self, snap_http_mock):
        """Tests that we can get and coerce snap config."""
        plugin = SnapMonitor()
        self.monitor.add(plugin)

        snap_http_mock.list.return_value = SnapdResponse(
            "sync",
            200,
            "OK",
            [
                {
                    "name": "test-snap",
                    "revision": "1",
                    "confinement": "strict",
                    "version": "v1.0",
                    "id": "123",
                }
            ],
        )
        snap_http_mock.get_conf.return_value = {
            "foo": {"baz": "default", "qux": [1, True, 2.0]},
            "bar": "enabled",
        }
        plugin.exchange()

        messages = self.mstore.get_pending_messages()

        self.assertTrue(len(messages) > 0)
        self.assertDictEqual(
            messages[0]["snaps"]["installed"][0],
            {
                "name": "test-snap",
                "revision": "1",
                "confinement": "strict",
                "version": "v1.0",
                "id": "123",
                "config": (
                    '{"foo": {"baz": "default", "qux": [1, true, 2.0]}, '
                    '"bar": "enabled"}'
                ),
            },
        )
