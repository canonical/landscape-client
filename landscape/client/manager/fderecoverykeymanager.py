import logging
from typing import Any, Tuple

from twisted.internet import task
from twisted.internet.defer import Deferred, ensureDeferred

from landscape.client import snap_http
from landscape.client.manager.plugin import (
    ManagerPlugin,
)
from landscape.client.snap_http.http import SnapdHttpException
from landscape.client.snap_http.types import INCOMPLETE_STATUSES

KEYSLOT_NAME = "landscape-recovery-key"


class FDEKeyError(Exception):
    """Raised when the FDE key generation fails."""

    def __init__(self, message):
        self.message = message


class FDERecoveryKeyManager(ManagerPlugin):
    """Plugin that generates FDE recovery keys."""

    def register(self, client):
        super().register(client)
        client.register_message(
            "fde-recovery-key",
            self._handle_recovery_key_message,
        )

    def _handle_recovery_key_message(self, message):
        return ensureDeferred(self.handle_recovery_key_message(message))

    async def handle_recovery_key_message(self, message: dict[str, Any]) -> None:
        """Generates an FDE recovery key, then responds to `message`.

        If the recovery key is successfully generated, we will store it in the
        exchanger in-memory data store and attempt to add the recovery key to
        the message just before sending it to server.

        :message: A message of type "fde-recovery-key".
        """
        opid = message["operation-id"]

        try:
            recovery_key_exists = self._recovery_key_exists()
            recovery_key, key_id = self._generate_recovery_key()
            await self._update_recovery_key(key_id, recovery_key_exists)

            self.registry.broker.update_exchange_state("recovery-key", recovery_key)

            await self._send_fde_recovery_key(
                opid, True, "Generated new FDE recovery key."
            )
        except FDEKeyError as e:
            await self._send_fde_recovery_key(opid, False, str(e))
        except Exception as e:
            await self._send_fde_recovery_key(opid, False, str(e))

    async def _send_fde_recovery_key(
        self,
        opid: int,
        successful: bool,
        result_text: str,
    ) -> None:
        """Queues a `fde-recovery-key` message to Landscape Server."""

        message = {
            "type": "fde-recovery-key",
            "operation-id": opid,
            "successful": successful,
            "result-text": result_text,
        }

        return await self.registry.broker.send_message(
            message,
            self._session_id,
            True,
        )

    def _recovery_key_exists(
        self,
    ) -> bool:
        """Checks if the Landscape recovery key keyslot already exists.

        :raises FDEKeyError: If the snapd API returns an error.
        """

        try:
            result = snap_http.get_keyslots()
        except SnapdHttpException as e:
            raise FDEKeyError(f"Unable to list recovery keys: {e}")

        slots = result.result["by-container-role"]["system-data"]["keyslots"]

        return KEYSLOT_NAME in slots

    def _generate_recovery_key(
        self,
    ) -> Tuple[str, str]:
        """Generates the recovery key and a key-id used to update the
        Landscape recovery key keyslot.

        :raises FDEKeyError: If the snapd API returns an error.
        """

        try:
            result = snap_http.generate_recovery_key()
        except SnapdHttpException as e:
            raise FDEKeyError(f"Unable to generate recovery key: {e}")

        recovery_key = result.result["recovery-key"]
        key_id = result.result["key-id"]

        return recovery_key, key_id

    async def _update_recovery_key(
        self, key_id: str, recovery_key_exists: bool
    ) -> None:
        """Uses the key-id to add or replace the Landscape recovery key keyslot.

        :key_id: The identifier for the generated recovery key.
        :recovery_key_exists: If True, replaces the recovery key instead of adding it.

        :raises FDEKeyError: If the snapd API returns an error.
        """

        try:
            result = snap_http.update_recovery_key(
                key_id, KEYSLOT_NAME, recovery_key_exists
            )
        except SnapdHttpException as e:
            raise FDEKeyError(f"Unable to update recovery key: {e}")

        await self._poll_for_completion(result.change)

    def _poll_for_completion(self, change_id: str) -> Deferred:
        """Waits for an async operation to be complete.

        :change_id: The change id for the async operation.

        :raises FDEKeyError: If the snapd API returns an error.
        """
        interval = getattr(self.registry.config, "snapd_poll_interval", 15)

        def get_status():
            logging.info("Polling snapd for status of pending recovery key update.")

            try:
                status = snap_http.check_change(change_id).result["status"]
            except SnapdHttpException as e:
                logging.error(f"Error checking status of snap changes: {e}")
                loop.stop()
                raise FDEKeyError(str(e))

            if status in INCOMPLETE_STATUSES:
                logging.debug(
                    "Incomplete status for recovery key update, waiting...",
                )
            else:
                logging.debug("Complete status for recovery key update")
                loop.stop()

        loop = task.LoopingCall(get_status)
        loopDeferred = loop.start(interval)

        return loopDeferred
