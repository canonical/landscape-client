from unittest import mock

from twisted.internet.defer import ensureDeferred

from landscape.client.manager.fderecoverykeymanager import (
    FDEKeyError,
    FDERecoveryKeyManager,
)
from landscape.client.snap_http.http import SnapdHttpException
from landscape.client.snap_http.types import SnapdResponse
from landscape.client.tests.helpers import LandscapeTest, ManagerHelper

MODULE = "landscape.client.manager.fderecoverykeymanager"


class FDERecoveryKeyManagerTests(LandscapeTest):
    helpers = [ManagerHelper]

    def setUp(self):
        super().setUp()
        self.plugin = FDERecoveryKeyManager()
        self.manager.add(self.plugin)
        self.mock_get_keyslots = mock.patch(
            MODULE + ".snap_http.get_keyslots",
            return_value=SnapdResponse(
                "sync",
                200,
                "OK",
                {"by-container-role": {"system-data": {"keyslots": []}}},
            ),
        ).start()
        self.mock_generate_key = mock.patch(
            MODULE + ".snap_http.generate_recovery_key",
            return_value=SnapdResponse(
                "sync",
                200,
                "OK",
                {"key-id": "realkey", "recovery-key": "my-recovery-key"},
            ),
        ).start()
        self.mock_update_key = mock.patch(
            MODULE + ".snap_http.update_recovery_key",
            return_value=SnapdResponse("async", 202, "OK", {}, change=1),
        ).start()
        self.mock_check_changes = mock.patch(
            MODULE + ".snap_http.check_change",
            return_value=SnapdResponse("sync", 200, "OK", {"status": "Done"}),
        ).start()
        self.send_message = mock.patch.object(
            self.plugin.registry.broker,
            "send_message",
            new=mock.AsyncMock(),
        ).start()

        self.addCleanup(mock.patch.stopall)

    def test_add_recovery_key(self):
        """If no landscape recovery key exists, we generate a new one."""
        deferred = ensureDeferred(
            self.plugin.handle_recovery_key_message(
                {
                    "operation-id": 1,
                },
            ),
        )

        def check(_):
            self.mock_get_keyslots.assert_called_once_with()
            self.mock_generate_key.assert_called_once_with()
            self.mock_update_key.assert_called_once_with(
                "realkey", "landscape-recovery-key", False
            )
            self.mock_check_changes.assert_called()
            self.assertEqual(
                self.send_message.mock_calls,
                [
                    mock.call(
                        {
                            "type": "fde-recovery-key",
                            "operation-id": 1,
                            "successful": True,
                            "result-text": "Generated new FDE recovery key.",
                        },
                        self.plugin._session_id,
                        True,
                    ),
                ],
            )

        deferred.addCallback(check)
        return deferred

    def test_replace_recovery_key(self):
        """If the recovery key already exists, we replace the recovery key."""
        self.mock_get_keyslots = mock.patch(
            MODULE + ".snap_http.get_keyslots",
            return_value=SnapdResponse(
                "sync",
                200,
                "OK",
                {
                    "by-container-role": {
                        "system-data": {
                            "keyslots": {"landscape-recovery-key": {"type": "recovery"}}
                        }
                    }
                },
            ),
        ).start()

        deferred = ensureDeferred(
            self.plugin.handle_recovery_key_message(
                {
                    "operation-id": 1,
                },
            ),
        )

        def check(_):
            self.mock_get_keyslots.assert_called_once_with()
            self.mock_generate_key.assert_called_once_with()
            self.mock_update_key.assert_called_once_with(
                "realkey", "landscape-recovery-key", True
            )
            self.mock_check_changes.assert_called()
            self.assertEqual(
                self.send_message.mock_calls,
                [
                    mock.call(
                        {
                            "type": "fde-recovery-key",
                            "operation-id": 1,
                            "successful": True,
                            "result-text": "Generated new FDE recovery key.",
                        },
                        self.plugin._session_id,
                        True,
                    ),
                ],
            )

        deferred.addCallback(check)
        return deferred

    def test_get_keyslots_fails(self):
        """If _get_keyslots fails, we get an unsuccessful message."""
        self.mock_get_keyslots = mock.patch(
            MODULE + ".snap_http.get_keyslots",
            side_effect=SnapdHttpException("some error"),
        ).start()
        deferred = ensureDeferred(
            self.plugin.handle_recovery_key_message(
                {
                    "operation-id": 1,
                },
            ),
        )

        def check(_):
            self.mock_get_keyslots.assert_called_once_with()
            self.mock_generate_key.assert_not_called()
            self.mock_update_key.assert_not_called()
            self.mock_check_changes.assert_not_called()
            self.assertEqual(
                self.send_message.mock_calls,
                [
                    mock.call(
                        {
                            "type": "fde-recovery-key",
                            "operation-id": 1,
                            "successful": False,
                            "result-text": "Unable to list recovery keys: some error",
                        },
                        self.plugin._session_id,
                        True,
                    ),
                ],
            )

        deferred.addCallback(check)
        return deferred

    def test_generate_fails(self):
        """If _generate_recovery_key fails, we get an unsuccessful message."""
        self.mock_generate_key = mock.patch(
            MODULE + ".snap_http.generate_recovery_key",
            side_effect=SnapdHttpException("some error"),
        ).start()
        deferred = ensureDeferred(
            self.plugin.handle_recovery_key_message(
                {
                    "operation-id": 1,
                },
            ),
        )

        def check(_):
            self.mock_get_keyslots.assert_called_once_with()
            self.mock_generate_key.assert_called_once_with()
            self.mock_update_key.assert_not_called()
            self.mock_check_changes.assert_not_called()
            self.assertEqual(
                self.send_message.mock_calls,
                [
                    mock.call(
                        {
                            "type": "fde-recovery-key",
                            "operation-id": 1,
                            "successful": False,
                            "result-text": "Unable to generate recovery key: "
                            "some error",
                        },
                        self.plugin._session_id,
                        True,
                    ),
                ],
            )

        deferred.addCallback(check)
        return deferred

    def test_update_fails(self):
        """If _update_recovery_key fails, we get an unsuccessful message."""
        self.mock_update_key = mock.patch(
            MODULE + ".snap_http.update_recovery_key",
            side_effect=SnapdHttpException("some error"),
        ).start()
        deferred = ensureDeferred(
            self.plugin.handle_recovery_key_message(
                {
                    "operation-id": 1,
                },
            ),
        )

        def check(_):
            self.mock_get_keyslots.assert_called_once_with()
            self.mock_generate_key.assert_called_once_with()
            self.mock_update_key.assert_called_once_with(
                "realkey", "landscape-recovery-key", False
            )
            self.mock_check_changes.assert_not_called()
            self.assertEqual(
                self.send_message.mock_calls,
                [
                    mock.call(
                        {
                            "type": "fde-recovery-key",
                            "operation-id": 1,
                            "successful": False,
                            "result-text": "Unable to update recovery key: some error",
                        },
                        self.plugin._session_id,
                        True,
                    ),
                ],
            )

        deferred.addCallback(check)
        return deferred

    def test_poll_for_completion(self):
        """Calls check_change and waits until the result is 'Done'."""
        mock_check_changes = mock.patch(
            MODULE + ".snap_http.check_change",
            side_effect=[
                SnapdResponse("sync", 200, "OK", {"status": "Not Done"}),
                SnapdResponse("sync", 200, "OK", {"status": "Done"}),
            ],
        ).start()

        deferred = ensureDeferred(
            self.plugin._poll_for_completion("1"),
        )

        def check(_):
            mock_check_changes.assert_called_with("1")

        deferred.addCallback(check)
        return deferred

    def test_poll_for_completion_fails(self):
        """If the call fails, we raise an FDEKeyError."""
        mock_check_changes = mock.patch(
            MODULE + ".snap_http.check_change",
            side_effect=[
                SnapdResponse("sync", 200, "OK", {"status": "Not Done"}),
                SnapdHttpException("something went wrong"),
            ],
        ).start()

        deferred = ensureDeferred(
            self.plugin._poll_for_completion("1"),
        )

        def check(result):
            mock_check_changes.assert_called_with("1")
            self.assertEqual(result, FDEKeyError("something went wrong"))

        deferred.addErrback(check)
        return deferred
