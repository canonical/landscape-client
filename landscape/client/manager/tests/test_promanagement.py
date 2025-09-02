from unittest import mock

from landscape.client.manager.manager import FAILED, SUCCEEDED
from landscape.client.manager.promanagement import ProManagement
from landscape.client.tests.helpers import LandscapeTest, ManagerHelper

from landscape.lib.uaclient import (
    AttachProError,
    ConnectivityException,
    ContractAPIException,
    LockHeldException,
)


class RunScriptTests(LandscapeTest):

    helpers = [ManagerHelper]

    def setUp(self):
        super().setUp()
        self.plugin = ProManagement()
        self.manager.add(self.plugin)

        self.broker_service.message_store.set_accepted_types(
            ["operation-result"],
        )

    def _send_attach(self):
        message = {
            "type": "attach-pro",
            "operation-id": 123,
            "token": "fake-token"
        }
        return self.manager.dispatch_message(message)

    def test_success(self):
        self.assertMessages(
            self.broker_service.message_store.get_pending_messages(),
            [],
        )

        with mock.patch(
            "landscape.client.manager.promanagement.attach_pro"
        ) as mock_attach:
            mock_attach.return_value = None
            result = self._send_attach()
            mock_attach.assert_called_once_with("fake-token")

        def got_result(r):
            self.assertMessages(
                self.broker_service.message_store.get_pending_messages(),
                [
                    {
                        "type": "operation-result",
                        "operation-id": 123,
                        "status": SUCCEEDED,
                        "result-text": "{}",
                    },
                ],
            )

        result.addCallback(got_result)
        return result

    def test_failure_creating_deferred(self):
        self.assertMessages(
            self.broker_service.message_store.get_pending_messages(),
            [],
        )

        with mock.patch(
            "landscape.client.manager.promanagement.ensureDeferred"
        ) as mock_deferred:
            mock_deferred.side_effect = Exception
            result = self._send_attach()

        def got_result(r):
            self.assertMessages(
                self.broker_service.message_store.get_pending_messages(),
                [
                    {
                        "type": "operation-result",
                        "operation-id": 123,
                        "status": FAILED,
                        "result-text": "Error attaching pro.",
                    },
                ],
            )

        result.addCallback(got_result)
        return result

    def test_failure_attach_pro_error(self):
        self.assertMessages(
            self.broker_service.message_store.get_pending_messages(),
            [],
        )

        with mock.patch(
            "landscape.client.manager.promanagement.attach_pro"
        ) as mock_attach:
            mock_attach.side_effect = AttachProError
            result = self._send_attach()

        def got_result(r):
            self.assertMessages(
                self.broker_service.message_store.get_pending_messages(),
                [
                    {
                        "type": "operation-result",
                        "operation-id": 123,
                        "status": FAILED,
                        "result-text": AttachProError.message,
                        "result-code": 2,
                    },
                ],
            )

        result.addCallback(got_result)
        return result

    def test_failure_connectivity_error(self):
        self.assertMessages(
            self.broker_service.message_store.get_pending_messages(),
            [],
        )

        with mock.patch(
            "landscape.client.manager.promanagement.attach_pro"
        ) as mock_attach:
            mock_attach.side_effect = ConnectivityException
            result = self._send_attach()

        def got_result(r):
            self.assertMessages(
                self.broker_service.message_store.get_pending_messages(),
                [
                    {
                        "type": "operation-result",
                        "operation-id": 123,
                        "status": FAILED,
                        "result-text": ConnectivityException.message,
                        "result-code": 2,
                    },
                ],
            )

        result.addCallback(got_result)
        return result

    def test_failure_contract_api_error(self):
        self.assertMessages(
            self.broker_service.message_store.get_pending_messages(),
            [],
        )

        with mock.patch(
            "landscape.client.manager.promanagement.attach_pro"
        ) as mock_attach:
            mock_attach.side_effect = ContractAPIException
            result = self._send_attach()

        def got_result(r):
            self.assertMessages(
                self.broker_service.message_store.get_pending_messages(),
                [
                    {
                        "type": "operation-result",
                        "operation-id": 123,
                        "status": FAILED,
                        "result-text": ContractAPIException.message,
                        "result-code": 2,
                    },
                ],
            )

        result.addCallback(got_result)
        return result

    def test_failure_lock_held_error(self):
        self.assertMessages(
            self.broker_service.message_store.get_pending_messages(),
            [],
        )

        with mock.patch(
            "landscape.client.manager.promanagement.attach_pro"
        ) as mock_attach:
            mock_attach.side_effect = LockHeldException
            result = self._send_attach()

        def got_result(r):
            self.assertMessages(
                self.broker_service.message_store.get_pending_messages(),
                [
                    {
                        "type": "operation-result",
                        "operation-id": 123,
                        "status": FAILED,
                        "result-text": LockHeldException.message,
                        "result-code": 2,
                    },
                ],
            )

        result.addCallback(got_result)
        return result

    def test_failure_general_error(self):
        self.assertMessages(
            self.broker_service.message_store.get_pending_messages(),
            [],
        )

        with mock.patch(
            "landscape.client.manager.promanagement.attach_pro"
        ) as mock_attach:
            mock_attach.side_effect = Exception
            result = self._send_attach()

        def got_result(r):
            message = self.broker_service.message_store.get_pending_messages()
            message = message[0]
            self.assertEqual("operation-result", message["type"])
            self.assertEqual(123, message["operation-id"])
            self.assertEqual(FAILED, message["status"])
            self.assertEqual(mock.ANY, message["result-text"])
            self.assertNotIn("result-code", message)

        result.addCallback(got_result)
        return result
