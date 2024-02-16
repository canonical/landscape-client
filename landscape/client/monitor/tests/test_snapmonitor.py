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
                },
            ],
        )
        snap_http_mock.get_conf.return_value = SnapdResponse(
            "sync",
            200,
            "OK",
            {
                "foo": {"baz": "default", "qux": [1, True, 2.0]},
                "bar": "enabled",
            },
        )
        snap_http_mock.get_apps.return_value = SnapdResponse(
            "sync",
            200,
            "OK",
            [],
        )
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

    @patch("landscape.client.monitor.snapmonitor.snap_http")
    def test_get_snap_services(self, snap_http_mock):
        """Tests that we can get and coerce snap services."""
        plugin = SnapMonitor()
        self.monitor.add(plugin)

        services = [
            {
                "snap": "test-snap",
                "name": "hello-svc",
                "daemon": "simple",
                "daemon-scope": "system",
                "active": True,
            },
            {
                "snap": "test-snap",
                "name": "bye-svc",
                "daemon": "simple",
                "daemon-scope": "system",
            },
            {
                "activators": [
                    {
                        "Active": True,
                        "Enabled": True,
                        "Name": "unix",
                        "Type": "socket",
                    },
                ],
                "daemon": "simple",
                "daemon-scope": "system",
                "enabled": True,
                "name": "user-daemon",
                "snap": "lxd",
            },
        ]
        snap_http_mock.list.return_value = SnapdResponse("sync", 200, "OK", [])
        snap_http_mock.get_conf.return_value = SnapdResponse(
            "sync",
            200,
            "OK",
            {},
        )
        snap_http_mock.get_apps.return_value = SnapdResponse(
            "sync",
            200,
            "OK",
            services,
        )
        plugin.exchange()

        messages = self.mstore.get_pending_messages()

        self.assertTrue(len(messages) > 0)
        self.assertCountEqual(messages[0]["snaps"]["services"], services)

    @patch("landscape.client.monitor.snapmonitor.snap_http")
    def test_get_snap_services_error(self, snap_http_mock):
        """Tests that we can get and coerce snap services."""
        plugin = SnapMonitor()
        self.monitor.add(plugin)

        snap_http_mock.list.return_value = SnapdResponse("sync", 200, "OK", [])
        snap_http_mock.get_conf.return_value = SnapdResponse(
            "sync",
            200,
            "OK",
            {},
        )

        with self.assertLogs(level="WARNING") as cm:
            snap_http_mock.get_apps.side_effect = SnapdHttpException
            plugin.exchange()

        messages = self.mstore.get_pending_messages()

        self.assertTrue(len(messages) > 0)
        self.assertEqual(
            cm.output,
            ["WARNING:root:Unable to list services: "],
        )
        self.assertCountEqual(messages[0]["snaps"]["services"], [])
