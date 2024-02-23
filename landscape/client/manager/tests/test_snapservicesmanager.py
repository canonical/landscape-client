import sys
from unittest import mock

from landscape.client.manager.manager import FAILED
from landscape.client.manager.manager import SUCCEEDED
from landscape.client.manager.snapservicesmanager import SnapServicesManager
from landscape.client.snap_http import SnapdHttpException
from landscape.client.snap_http import SnapdResponse
from landscape.client.tests.helpers import LandscapeTest
from landscape.client.tests.helpers import ManagerHelper


class SnapServicesManagerTest(LandscapeTest):
    helpers = [ManagerHelper]

    def setUp(self):
        super().setUp()

        self.snap_http = mock.patch(
            "landscape.client.manager.snapservicesmanager.snap_http",
        ).start()

        self.broker_service.message_store.set_accepted_types(
            ["operation-result"],
        )
        self.plugin = SnapServicesManager()
        self.manager.add(self.plugin)

        self.manager.config.snapd_poll_attempts = 2
        self.manager.config.snapd_poll_interval = 0.1

    def tearDown(self):
        mock.patch.stopall()

    @mock.patch("landscape.client.manager.snapmanager.snap_http")
    def test_start_service(self, mock_base_snap_http):
        self.snap_http.start.return_value = SnapdResponse(
            "async",
            202,
            "Accepted",
            None,
            change="1",
        )
        mock_base_snap_http.check_changes.return_value = SnapdResponse(
            "sync",
            200,
            "OK",
            [{"id": "1", "status": "Done"}],
        )
        self.snap_http.get_apps.return_value = SnapdResponse(
            "sync",
            200,
            "OK",
            [
                {
                    "snap": "test-snap",
                    "name": "bye-svc",
                    "daemon": "simple",
                    "daemon-scope": "system",
                    "enabled": True,
                },
            ],
        )

        result = self.manager.dispatch_message(
            {
                "type": "start-snap-service",
                "operation-id": 123,
                "snaps": [
                    {"name": "test-snap.hello-svc", "args": {"enable": True}},
                ],
            },
        )

        def got_result(_):
            self.assertMessages(
                self.broker_service.message_store.get_pending_messages(),
                [
                    {
                        "type": "operation-result",
                        "status": SUCCEEDED,
                        "result-text": "{'completed': ['test-snap.hello-svc'],"
                        " 'errored': [], 'errors': {}}",
                        "operation-id": 123,
                    },
                ],
            )

        self.snap_http.start.assert_called_once_with(
            "test-snap.hello-svc",
            enable=True,
        )

        return result.addCallback(got_result)

    def test_start_service_error(self):
        self.snap_http.start.side_effect = SnapdHttpException(
            b'{"result": "snap idonotexist not found"}',
        )
        self.snap_http.get_apps.return_value = SnapdResponse(
            "sync",
            200,
            "OK",
            [],
        )

        result = self.manager.dispatch_message(
            {
                "type": "start-snap-service",
                "operation-id": 123,
                "snaps": [{"name": "idonotexist", "args": {"enable": True}}],
            },
        )

        self.log_helper.ignore_errors(r".+idonotexist$")

        def got_result(_):
            self.assertMessages(
                self.broker_service.message_store.get_pending_messages(),
                [
                    {
                        "type": "operation-result",
                        "status": FAILED,
                        "result-text": "{'completed': [], "
                        "'errored': [], 'errors': {'idonotexist': "
                        "'snap idonotexist not found'}}",
                        "operation-id": 123,
                    },
                ],
            )

        self.snap_http.start.assert_called_once_with(
            "idonotexist",
            enable=True,
        )

        return result.addCallback(got_result)

    @mock.patch("landscape.client.manager.snapmanager.snap_http")
    def test_stop_service_batch(self, mock_base_snap_http):
        self.snap_http.stop_all.return_value = SnapdResponse(
            "async",
            202,
            "Accepted",
            None,
            change="1",
        )
        mock_base_snap_http.check_changes.return_value = SnapdResponse(
            "sync",
            200,
            "OK",
            [{"id": "1", "status": "Done"}],
        )
        self.snap_http.get_apps.return_value = SnapdResponse(
            "sync",
            200,
            "OK",
            [
                {
                    "snap": "lxd",
                    "name": "lxd",
                    "daemon": "simple",
                    "daemon-scope": "system",
                },
                {
                    "snap": "landscape-client",
                    "name": "landscape-client",
                    "daemon": "simple",
                    "daemon-scope": "system",
                },
            ],
        )

        result = self.manager.dispatch_message(
            {
                "type": "stop-snap-service",
                "operation-id": 123,
                "snaps": [
                    {"name": "lxd"},
                    {"name": "landscape-client"},
                ],
                "args": {"disable": False},
            },
        )

        def got_result(_):
            self.assertMessages(
                self.broker_service.message_store.get_pending_messages(),
                [
                    {
                        "type": "operation-result",
                        "status": SUCCEEDED,
                        "result-text": "{'completed': ['BATCH'], "
                        "'errored': [], 'errors': {}}",
                        "operation-id": 123,
                    },
                ],
            )

        self.snap_http.stop_all.assert_called_once_with(
            ["lxd", "landscape-client"],
            disable=False,
        )

        return result.addCallback(got_result)

    @mock.patch("landscape.client.manager.snapmanager.snap_http")
    def test_restart_service(self, mock_base_snap_http):
        self.snap_http.restart_all.return_value = SnapdResponse(
            "async",
            202,
            "Accepted",
            None,
            change="1",
        )
        mock_base_snap_http.check_changes.return_value = SnapdResponse(
            "sync",
            200,
            "OK",
            [{"id": "1", "status": "Done"}],
        )
        self.snap_http.get_apps.return_value = SnapdResponse(
            "sync",
            200,
            "OK",
            [
                {
                    "snap": "lxd",
                    "name": "lxd",
                    "daemon": "simple",
                    "daemon-scope": "system",
                },
                {
                    "snap": "test-snap",
                    "name": "bye-svc",
                    "daemon": "simple",
                    "daemon-scope": "system",
                },
            ],
        )

        result = self.manager.dispatch_message(
            {
                "type": "restart-snap-service",
                "operation-id": 123,
                "snaps": [
                    {"name": "test-snap"},
                    {"name": "lxd"},
                ],
            },
        )

        def got_result(_):
            self.assertMessages(
                self.broker_service.message_store.get_pending_messages(),
                [
                    {
                        "type": "operation-result",
                        "status": SUCCEEDED,
                        "result-text": "{'completed': ['BATCH'], "
                        "'errored': [], 'errors': {}}",
                        "operation-id": 123,
                    },
                ],
            )

        self.snap_http.restart_all.assert_called_once_with(
            ["test-snap", "lxd"],
        )

        return result.addCallback(got_result)

    @mock.patch("landscape.client.manager.snapmanager.snap_http")
    def test_restart_service_update_failure(self, mock_base_snap_http):
        """
        Test when the client runs the operation successfully but
         `_send_snap_update` fails.
        """
        self.snap_http.restart_all.return_value = SnapdResponse(
            "async",
            202,
            "Accepted",
            None,
            change="1",
        )
        mock_base_snap_http.check_changes.return_value = SnapdResponse(
            "sync",
            200,
            "OK",
            [{"id": "1", "status": "Done"}],
        )
        self.snap_http.get_apps.side_effect = SnapdHttpException(
            "An error occurred.",
        )
        mock_logger = mock.Mock()
        self.patch(sys.modules["logging"], "error", mock_logger)

        result = self.manager.dispatch_message(
            {
                "type": "restart-snap-service",
                "operation-id": 123,
                "snaps": [
                    {"name": "test-snap"},
                    {"name": "lxd"},
                ],
            },
        )

        self.log_helper.ignore_errors(r".+error$")

        def got_result(_):
            self.assertMessages(
                self.broker_service.message_store.get_pending_messages(),
                [
                    {
                        "type": "operation-result",
                        "status": SUCCEEDED,
                        "result-text": "{'completed': ['BATCH'], "
                        "'errored': [], 'errors': {}}",
                        "operation-id": 123,
                    },
                ],
            )

            mock_logger.assert_called_once_with(
                "Unable to list services: An error occurred.",
            )

        self.snap_http.restart_all.assert_called_once_with(
            ["test-snap", "lxd"],
        )

        return result.addCallback(got_result)
