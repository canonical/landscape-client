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
        self.mstore = self.broker_service.message_store
        self.mstore.set_accepted_types(["snaps", "operation-result"])

        self.snap_http = mock.patch(
            "landscape.client.manager.snapmanager.snap_http",
        ).start()

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
        self.snap_http.list.return_value = SnapdResponse("sync", 200, "OK", [])

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

        def got_result(_):
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
        self.snap_http.list.return_value = SnapdResponse("sync", 200, "OK", [])
        self.snap_http.get_conf.return_value = SnapdResponse(
            "sync",
            200,
            "OK",
            {},
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

        def got_result(_):
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
        self.snap_http.list.return_value = SnapdResponse("sync", 200, "OK", [])

        result = self.manager.dispatch_message(
            {
                "type": "install-snaps",
                "operation-id": 123,
                "snaps": [{"name": "hello"}],
            },
        )

        self.log_helper.ignore_errors(r".+whoops$")

        def got_result(_):
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
        self.snap_http.list.return_value = SnapdResponse("sync", 200, "OK", [])

        result = self.manager.dispatch_message(
            {
                "type": "install-snaps",
                "operation-id": 123,
                "snaps": [{"name": "hello"}],
            },
        )

        def got_result(_):
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
        self.snap_http.list.return_value = SnapdResponse("sync", 200, "OK", [])

        result = self.manager.dispatch_message(
            {
                "type": "install-snaps",
                "operation-id": 123,
                "snaps": [{"name": "hello"}],
            },
        )

        self.log_helper.ignore_errors(r".+whoops$")

        def got_result(_):
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
        self.snap_http.list.return_value = SnapdResponse("sync", 200, "OK", [])

        result = self.manager.dispatch_message(
            {
                "type": "remove-snaps",
                "operation-id": 123,
                "snaps": [{"name": "hello"}],
            },
        )

        def got_result(_):
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
        self.snap_http.list.return_value = SnapdResponse("sync", 200, "OK", [])

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

        def got_result(_):
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
        self.snap_http.list.return_value = SnapdResponse("sync", 200, "OK", [])

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

        def got_result(_):
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

    def test_get_data(self):
        """Tests getting installed snap data."""
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
            {},
        )

        self.plugin.run()
        messages = self.mstore.get_pending_messages()

        self.assertTrue(len(messages) > 0)
        self.assertIn("installed", messages[0]["snaps"])

    def test_get_data_snapd_http_exception(self):
        """
        Tests that we return no data if there is an error getting it.
        """
        with self.assertLogs(level="ERROR") as cm:
            self.snap_http.list.side_effect = SnapdHttpException
            self.plugin.run()

        messages = self.mstore.get_pending_messages()

        self.assertEqual(len(messages), 0)
        self.assertEqual(
            cm.output,
            ["ERROR:root:Unable to list installed snaps: "],
        )

    def test_get_snap_config(self):
        """Tests that we can get and coerce snap config."""
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
                "foo": {"baz": "default", "qux": [1, True, 2.0]},
                "bar": "enabled",
            },
        )

        self.plugin.run()
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
