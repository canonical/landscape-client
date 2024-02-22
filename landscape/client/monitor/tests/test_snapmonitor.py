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
        self.snap_http = patch(
            "landscape.client.monitor.snapmonitor.snap_http",
        ).start()

    def tearDown(self):
        patch.stopall()

    def test_get_data(self):
        """Tests getting installed snap data."""
        plugin = SnapMonitor()
        self.monitor.add(plugin)

        self.snap_http.get_conf.return_value = SnapdResponse(
            "sync",
            200,
            "OK",
            {},
        )
        self.snap_http.list.return_value = SnapdResponse("sync", 200, "OK", [])

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

        with self.assertLogs(level="ERROR") as cm:
            self.snap_http.list.side_effect = SnapdHttpException
            plugin.exchange()

        messages = self.mstore.get_pending_messages()

        self.assertEqual(len(messages), 0)
        self.assertEqual(
            cm.output,
            ["ERROR:root:Unable to list installed snaps: "],
        )

    def test_get_snap_config(self):
        """Tests that we can get and coerce snap config."""
        plugin = SnapMonitor()
        self.monitor.add(plugin)

        def _mock_get_config(name, *_):
            if name == "landscape-client":
                result = {"experimental": {"monitor-config": True}}
            else:
                result = {
                    "foo": {"baz": "default", "qux": [1, True, 2.0]},
                    "bar": "enabled",
                }

            return SnapdResponse("sync", 200, "OK", result)

        self.snap_http.list.return_value = SnapdResponse(
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
        self.snap_http.get_conf.side_effect = _mock_get_config
        self.snap_http.get_apps.return_value = SnapdResponse(
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

    def test_get_snap_config_experimental_flag_off(self):
        """Tests attempt to get snap config with the feature flag off."""
        plugin = SnapMonitor()
        self.monitor.add(plugin)

        self.snap_http.list.return_value = SnapdResponse(
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
        self.snap_http.get_conf.return_value = SnapdResponse(
            "sync",
            200,
            "OK",
            {
                "experimental": {"monitor-config": False},
            },
        )
        self.snap_http.get_apps.return_value = []

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
            },
        )

    def test_get_snap_services(self):
        """Tests that we can get and coerce snap services."""
        plugin = SnapMonitor()
        self.monitor.add(plugin)

        def _mock_get_config(name, *_):
            if name == "landscape-client":
                result = {"experimental": {"monitor-services": True}}
            else:
                result = {}

            return SnapdResponse("sync", 200, "OK", result)

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
        self.snap_http.list.return_value = SnapdResponse("sync", 200, "OK", [])
        self.snap_http.get_conf.side_effect = _mock_get_config
        self.snap_http.get_apps.return_value = SnapdResponse(
            "sync",
            200,
            "OK",
            services,
        )
        plugin.exchange()

        messages = self.mstore.get_pending_messages()

        self.assertTrue(len(messages) > 0)
        self.assertCountEqual(messages[0]["snaps"]["services"], services)

    def test_get_snap_services_experimental_flag_off(self):
        """Tests attempt to get snap services with the feature flag off."""
        plugin = SnapMonitor()
        self.monitor.add(plugin)

        def _mock_get_config(name, *_):
            if name == "landscape-client":
                result = {
                    "experimental": {"monitor-services": False},
                }
            else:
                result = {}

            return SnapdResponse("sync", 200, "OK", result)

        self.snap_http.list.return_value = SnapdResponse("sync", 200, "OK", [])
        self.snap_http.get_conf.side_effect = _mock_get_config
        self.snap_http.get_apps.return_value = []

        plugin.exchange()
        messages = self.mstore.get_pending_messages()

        self.assertTrue(len(messages) > 0)
        self.assertNotIn("services", messages[0]["snaps"])

    def test_get_snap_services_error(self):
        """Tests that we can get and coerce snap services."""
        plugin = SnapMonitor()
        self.monitor.add(plugin)

        def _mock_get_config(name, *_):
            if name == "landscape-client":
                result = {
                    "experimental": {
                        "monitor-config": True,
                        "monitor-services": True,
                    },
                }
            else:
                result = {}

            return SnapdResponse("sync", 200, "OK", result)

        self.snap_http.list.return_value = SnapdResponse("sync", 200, "OK", [])
        self.snap_http.get_conf.side_effect = _mock_get_config

        with self.assertLogs(level="WARNING") as cm:
            self.snap_http.get_apps.side_effect = SnapdHttpException
            plugin.exchange()

        messages = self.mstore.get_pending_messages()

        self.assertTrue(len(messages) > 0)
        self.assertEqual(
            cm.output,
            ["WARNING:root:Unable to list services: "],
        )
