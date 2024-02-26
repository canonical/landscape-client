from unittest.mock import patch

from landscape.client.monitor.snapservicesmonitor import SnapServicesMonitor
from landscape.client.snap_http import SnapdHttpException
from landscape.client.snap_http import SnapdResponse
from landscape.client.tests.helpers import LandscapeTest
from landscape.client.tests.helpers import MonitorHelper


class SnapServicesMonitorTest(LandscapeTest):

    helpers = [MonitorHelper]

    def setUp(self):
        super().setUp()
        self.mstore.set_accepted_types(["snap-services"])

    @patch("landscape.client.monitor.snapservicesmonitor.snap_http")
    def test_get_data(self, snap_http_mock):
        """Tests getting running snap services data."""
        snap_http_mock.get_apps.return_value = SnapdResponse(
            "sync",
            200,
            "OK",
            [
                {
                    "snap": "test-snap",
                    "name": "bye-svc",
                    "daemon": "simple",
                    "daemon-scope": "system",
                },
            ],
        )

        plugin = SnapServicesMonitor()
        self.monitor.add(plugin)

        plugin.exchange()

        messages = self.mstore.get_pending_messages()

        self.assertTrue(len(messages) > 0)
        self.assertIn("running", messages[0]["services"])

    @patch("landscape.client.monitor.snapservicesmonitor.snap_http")
    def test_get_snap_services(self, snap_http_mock):
        """Tests that we can get and coerce snap services."""
        plugin = SnapServicesMonitor()
        self.monitor.add(plugin)
        self.maxDiff = None

        services = [
            {
                "snap": "test-snap",
                "name": "bye-svc",
                "daemon": "simple",
                "daemon-scope": "system",
            },
            {
                "snap": "test-snap",
                "name": "hello-svc",
                "daemon": "simple",
                "daemon-scope": "system",
                "active": True,
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
        self.assertCountEqual(messages[0]["services"]["running"], services)

    @patch("landscape.client.monitor.snapservicesmonitor.snap_http")
    def test_get_snap_services_error(self, snap_http_mock):
        """Tests that we can get and coerce snap services."""
        plugin = SnapServicesMonitor()
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
        self.assertCountEqual(messages[0]["services"]["running"], [])
