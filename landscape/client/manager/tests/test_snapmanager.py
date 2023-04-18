from unittest import mock

from landscape.client.manager.manager import FAILED
from landscape.client.manager.manager import SUCCEEDED
from landscape.client.manager.snapmanager import SnapManager
from landscape.client.snap.http import SnapdHttpException
from landscape.client.snap.http import SnapHttp as OrigSnapHttp
from landscape.client.tests.helpers import LandscapeTest
from landscape.client.tests.helpers import ManagerHelper


class SnapManagerTest(LandscapeTest):
    helpers = [ManagerHelper]

    def setUp(self):
        super().setUp()

        self.broker_service.message_store.set_accepted_types(
            ["operation-result"],
        )
        self.plugin = SnapManager()
        self.manager.add(self.plugin)

        self.manager.config.snapd_poll_attempts = 2
        self.manager.config.snapd_poll_interval = 0.1

    @mock.patch("landscape.client.manager.snapmanager.SnapHttp")
    def test_install_snaps(self, SnapHttp):
        snap_http = mock.Mock(
            spec_set=OrigSnapHttp,
            install_snap=mock.Mock(return_value={"change": "1"}),
            check_change=mock.Mock(
                return_value={"result": {"status": "Done"}},
            ),
        )
        SnapHttp.return_value = snap_http

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
                        "status": SUCCEEDED,
                        "result-text": "{'completed': ['1'], 'errored': [], "
                        "'errors': {}}",
                        "operation-id": 123,
                    },
                ],
            )

        return result.addCallback(got_result)

    @mock.patch("landscape.client.manager.snapmanager.SnapHttp")
    def test_install_snap_immediate_error(self, SnapHttp):
        snap_http = mock.Mock(
            spec_set=OrigSnapHttp,
            install_snap=mock.Mock(
                side_effect=SnapdHttpException(b'{"result": "whoops"}'),
            ),
        )
        SnapHttp.return_value = snap_http

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
                        "'errors': {('hello', None, None): "
                        "'whoops'}}",
                        "operation-id": 123,
                    },
                ],
            )

        return result.addCallback(got_result)

    @mock.patch("landscape.client.manager.snapmanager.SnapHttp")
    def test_install_snap_timeout(self, SnapHttp):
        snap_http = mock.Mock(
            spec_set=OrigSnapHttp,
            install_snap=mock.Mock(return_value={"change": "1"}),
            check_change=mock.Mock(
                return_value={"result": {"status": "Doing"}},
            ),
        )
        SnapHttp.return_value = snap_http

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
                        "result-text": "{'completed': [], 'errored': ['1'], "
                        "'errors': {'1': 'hello: Timeout'}}",
                        "operation-id": 123,
                    },
                ],
            )

        return result.addCallback(got_result)

    @mock.patch("landscape.client.manager.snapmanager.SnapHttp")
    def test_install_snap_no_status(self, SnapHttp):
        snap_http = mock.Mock(
            spec_set=OrigSnapHttp,
            install_snap=mock.Mock(return_value={"change": "1"}),
            check_change=mock.Mock(return_value={"result": {}}),
        )
        SnapHttp.return_value = snap_http

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
                        "result-text": "{'completed': [], 'errored': ['1'], "
                        "'errors': {'1': 'hello: SnapdError'}}",
                        "operation-id": 123,
                    },
                ],
            )

        return result.addCallback(got_result)

    @mock.patch("landscape.client.manager.snapmanager.SnapHttp")
    def test_install_snap_check_error(self, SnapHttp):
        snap_http = mock.Mock(
            spec_set=OrigSnapHttp,
            install_snap=mock.Mock(return_value={"change": "1"}),
            check_change=mock.Mock(side_effect=SnapdHttpException("whoops")),
        )
        SnapHttp.return_value = snap_http

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
                        "result-text": "{'completed': [], 'errored': ['1'], "
                        "'errors': {'1': 'hello: whoops'}}",
                        "operation-id": 123,
                    },
                ],
            )

        return result.addCallback(got_result)

    @mock.patch("landscape.client.manager.snapmanager.SnapHttp")
    def test_remove_snap(self, SnapHttp):
        snap_http = mock.Mock(
            spec_set=OrigSnapHttp,
            remove_snap=mock.Mock(return_value={"change": "1"}),
            check_change=mock.Mock(
                return_value={"result": {"status": "Done"}},
            ),
        )
        SnapHttp.return_value = snap_http

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
                        "result-text": "{'completed': ['1'], 'errored': [], "
                        "'errors': {}}",
                        "operation-id": 123,
                    },
                ],
            )

        return result.addCallback(got_result)
