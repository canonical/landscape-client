from unittest import mock

from landscape.client.manager.manager import FAILED
from landscape.client.manager.manager import SUCCEEDED
from landscape.client.manager.snapmanager import SnapManager
from landscape.client.snap_http import SnapdHttpException
from landscape.client.snap_http import SnapdResponse
from landscape.client.tests.helpers import LandscapeTest
from landscape.client.tests.helpers import ManagerHelper


class SnapManagerTest(LandscapeTest):
    helpers = [ManagerHelper]

    def setUp(self):
        super().setUp()

        self.snap_http = mock.patch(
            "landscape.client.manager.snapmanager.snap_http",
        ).start()

        self.broker_service.message_store.set_accepted_types(
            ["operation-result"],
        )
        self.plugin = SnapManager()
        self.manager.add(self.plugin)

        self.manager.config.snapd_poll_attempts = 2
        self.manager.config.snapd_poll_interval = 0.1

    def tearDown(self):
        mock.patch.stopall()

    def test_install_snaps(self):
        """
        When at least one channel or revision is specified, snaps are
        installed via one call to snapd per snap.
        """

        def install_snap(name, revision=None, channel=None, classic=False):
            if name == "hello":
                return SnapdResponse("async", 200, "OK", None, change="1")

            if name == "goodbye":
                return SnapdResponse("async", 200, "OK", None, change="2")

            return mock.DEFAULT

        self.snap_http.install.side_effect = install_snap
        self.snap_http.check_changes.return_value = SnapdResponse(
            "sync",
            "200",
            "OK",
            [
                {"id": "1", "status": "Done"},
                {"id": "2", "status": "Done"},
            ],
        )
        self.snap_http.list.return_value = SnapdResponse(
            "sync",
            200,
            "OK",
            {"installed": []},
        )

        result = self.manager.dispatch_message(
            {
                "type": "install-snaps",
                "operation-id": 123,
                "snaps": [
                    {"name": "hello", "args": {"revision": 9001}},
                    {"name": "goodbye"},
                ],
            },
        )

        def got_result(r):
            self.assertMessages(
                self.broker_service.message_store.get_pending_messages(),
                [
                    {
                        "type": "operation-result",
                        "status": SUCCEEDED,
                        "result-text": "{'completed': ['hello', 'goodbye'], "
                        "'errored': [], 'errors': {}}",
                        "operation-id": 123,
                    },
                ],
            )

        return result.addCallback(got_result)

    def test_install_snaps_batch(self):
        """
        When no channels or revisions are specified, snaps are installed
        via a single call to snapd.
        """
        self.snap_http.install_all.return_value = SnapdResponse(
            "async",
            202,
            "Accepted",
            None,
            change="1",
        )
        self.snap_http.check_changes.return_value = SnapdResponse(
            "sync",
            200,
            "OK",
            [{"id": "1", "status": "Done"}],
        )
        self.snap_http.list.return_value = SnapdResponse(
            "sync",
            200,
            "OK",
            {
                "installed": [
                    {
                        "name": "hello",
                        "id": "test",
                        "confinement": "strict",
                        "tracking-channel": "latest/stable",
                        "revision": "100",
                        "publisher": {"validation": "yep", "username": "me"},
                        "version": "1.2.3",
                    },
                ],
            },
        )

        result = self.manager.dispatch_message(
            {
                "type": "install-snaps",
                "operation-id": 123,
                "snaps": [
                    {"name": "hello"},
                    {"name": "goodbye"},
                ],
            },
        )

        def got_result(r):
            self.assertMessages(
                self.broker_service.message_store.get_pending_messages(),
                [
                    {
                        "type": "operation-result",
                        "status": SUCCEEDED,
                        "result-text": "{'completed': ['BATCH'], 'errored': "
                        "[], 'errors': {}}",
                        "operation-id": 123,
                    },
                ],
            )

        return result.addCallback(got_result)

    def test_install_snap_immediate_error(self):
        self.snap_http.install_all.side_effect = SnapdHttpException(
            b'{"result": "whoops"}',
        )
        self.snap_http.list.return_value = SnapdResponse(
            "sync",
            200,
            "OK",
            {"installed": []},
        )

        result = self.manager.dispatch_message(
            {
                "type": "install-snaps",
                "operation-id": 123,
                "snaps": [{"name": "hello"}],
            },
        )

        self.log_helper.ignore_errors(r".+whoops$")

        def got_result(r):
            self.assertMessages(
                self.broker_service.message_store.get_pending_messages(),
                [
                    {
                        "type": "operation-result",
                        "status": FAILED,
                        "result-text": "{'completed': [], 'errored': [], "
                        "'errors': {'BATCH': 'whoops'}}",
                        "operation-id": 123,
                    },
                ],
            )

        return result.addCallback(got_result)

    def test_install_snap_no_status(self):
        self.snap_http.install_all.return_value = SnapdResponse(
            "async",
            202,
            "Accepted",
            None,
            change="1",
        )
        self.snap_http.check_changes.return_value = SnapdResponse(
            "sync",
            200,
            "OK",
            [],
        )
        self.snap_http.list.return_value = SnapdResponse(
            "sync",
            200,
            "OK",
            {"installed": []},
        )

        result = self.manager.dispatch_message(
            {
                "type": "install-snaps",
                "operation-id": 123,
                "snaps": [{"name": "hello"}],
            },
        )

        def got_result(r):
            self.assertMessages(
                self.broker_service.message_store.get_pending_messages(),
                [
                    {
                        "type": "operation-result",
                        "status": FAILED,
                        "result-text": "{'completed': [], 'errored': ['BATCH']"
                        ", 'errors': {'BATCH': 'Unknown'}}",
                        "operation-id": 123,
                    },
                ],
            )

        return result.addCallback(got_result)

    def test_install_snap_check_error(self):
        self.snap_http.install_all.return_value = SnapdResponse(
            "async",
            200,
            "Accepted",
            None,
            change="1",
        )
        self.snap_http.check_changes.side_effect = SnapdHttpException("whoops")
        self.snap_http.list.return_value = SnapdResponse(
            "sync",
            200,
            "OK",
            {"installed": []},
        )

        result = self.manager.dispatch_message(
            {
                "type": "install-snaps",
                "operation-id": 123,
                "snaps": [{"name": "hello"}],
            },
        )

        self.log_helper.ignore_errors(r".+whoops$")

        def got_result(r):
            self.assertMessages(
                self.broker_service.message_store.get_pending_messages(),
                [
                    {
                        "type": "operation-result",
                        "status": FAILED,
                        "result-text": "{'completed': [], 'errored': ['BATCH']"
                        ", 'errors': {'BATCH': 'whoops'}}",
                        "operation-id": 123,
                    },
                ],
            )

        return result.addCallback(got_result)

    def test_remove_snap(self):
        self.snap_http.remove_all.return_value = SnapdResponse(
            "async",
            202,
            "Accepted",
            None,
            change="1",
        )
        self.snap_http.check_changes.return_value = SnapdResponse(
            "sync",
            200,
            "OK",
            [{"id": "1", "status": "Done"}],
        )
        self.snap_http.list.return_value = SnapdResponse(
            "sync",
            200,
            "OK",
            {"installed": []},
        )

        result = self.manager.dispatch_message(
            {
                "type": "remove-snaps",
                "operation-id": 123,
                "snaps": [{"name": "hello"}],
            },
        )

        def got_result(r):
            self.assertMessages(
                self.broker_service.message_store.get_pending_messages(),
                [
                    {
                        "type": "operation-result",
                        "status": SUCCEEDED,
                        "result-text": "{'completed': ['BATCH'], 'errored': []"
                        ", 'errors': {}}",
                        "operation-id": 123,
                    },
                ],
            )

        return result.addCallback(got_result)

    def test_set_config(self):
        self.snap_http.set_conf.return_value = SnapdResponse(
            "async",
            202,
            "Accepted",
            None,
            change="1",
        )
        self.snap_http.check_changes.return_value = SnapdResponse(
            "sync",
            "200",
            "OK",
            [{"id": "1", "status": "Done"}],
        )
        self.snap_http.list.return_value = SnapdResponse(
            "sync",
            200,
            "OK",
            {"installed": []},
        )

        result = self.manager.dispatch_message(
            {
                "type": "set-snap-config",
                "operation-id": 123,
                "snaps": [
                    {
                        "name": "hello",
                        "args": {
                            "config": {"foo": {"bar": "qux", "baz": "quux"}},
                        },
                    },
                ],
            },
        )

        def got_result(r):
            self.assertMessages(
                self.broker_service.message_store.get_pending_messages(),
                [
                    {
                        "type": "operation-result",
                        "status": SUCCEEDED,
                        "result-text": "{'completed': ['hello'], "
                        "'errored': [], 'errors': {}}",
                        "operation-id": 123,
                    },
                ],
            )

        return result.addCallback(got_result)

    def test_set_config_sync_error(self):
        self.snap_http.set_conf.side_effect = SnapdHttpException(
            b'{"result": "whoops"}',
        )
        self.snap_http.list.return_value = SnapdResponse(
            "sync",
            200,
            "OK",
            {"installed": []},
        )

        result = self.manager.dispatch_message(
            {
                "type": "set-snap-config",
                "operation-id": 123,
                "snaps": [
                    {
                        "name": "hello",
                        "args": {
                            "config": {"foo": {"bar": "qux", "baz": "quux"}},
                        },
                    },
                ],
            },
        )

        def got_result(r):
            self.assertMessages(
                self.broker_service.message_store.get_pending_messages(),
                [
                    {
                        "type": "operation-result",
                        "status": FAILED,
                        "result-text": (
                            "{'completed': [], 'errored': [], "
                            "'errors': {'hello': 'whoops'}}"
                        ),
                        "operation-id": 123,
                    },
                ],
            )

        return result.addCallback(got_result)

    def test_start_service(self):
        self.snap_http.start.return_value = SnapdResponse(
            "async",
            202,
            "Accepted",
            None,
            change="1",
        )
        self.snap_http.check_changes.return_value = SnapdResponse(
            "sync",
            200,
            "OK",
            [{"id": "1", "status": "Done"}],
        )
        self.snap_http.list.return_value = SnapdResponse(
            "sync",
            200,
            "OK",
            {"installed": []},
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

        def got_result(r):
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
        self.snap_http.list.return_value = SnapdResponse(
            "sync",
            200,
            "OK",
            {"installed": []},
        )

        result = self.manager.dispatch_message(
            {
                "type": "start-snap-service",
                "operation-id": 123,
                "snaps": [{"name": "idonotexist", "args": {"enable": True}}],
            },
        )

        self.log_helper.ignore_errors(r".+idonotexist$")

        def got_result(r):
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

    def test_stop_service_batch(self):
        self.snap_http.stop_all.return_value = SnapdResponse(
            "async",
            202,
            "Accepted",
            None,
            change="1",
        )
        self.snap_http.check_changes.return_value = SnapdResponse(
            "sync",
            200,
            "OK",
            [{"id": "1", "status": "Done"}],
        )
        self.snap_http.list.return_value = SnapdResponse(
            "sync",
            200,
            "OK",
            {"installed": []},
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

        def got_result(r):
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

    def test_restart_service(self):
        self.snap_http.restart_all.return_value = SnapdResponse(
            "async",
            202,
            "Accepted",
            None,
            change="1",
        )
        self.snap_http.check_changes.return_value = SnapdResponse(
            "sync",
            200,
            "OK",
            [{"id": "1", "status": "Done"}],
        )
        self.snap_http.list.return_value = SnapdResponse(
            "sync",
            200,
            "OK",
            {"installed": []},
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

        def got_result(r):
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
