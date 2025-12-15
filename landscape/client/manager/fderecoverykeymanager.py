import json
from typing import Any, Tuple

from twisted.internet import threads
from twisted.internet.defer import Deferred, ensureDeferred
from twisted.internet import reactor
from twisted.internet.threads import deferToThread

from landscape.client.manager.plugin import (
    FAILED,
    SUCCEEDED,
    ManagerPlugin,
)
from landscape.client.manager.scriptexecution import (
    ProcessAccumulationProtocol,
    ProcessFailedError,
)
from landscape.client.manager.ubuntuproinfo import get_ubuntu_pro_info
from landscape.lib.uaclient import (
    ProManagementError,
    attach_pro,
    detach_pro,
)

# FDE_EXECUTABLE = whatever the snapd api is
FDE_EXECUTABLE = "cat"


class FDEKeyError(Exception):
    """Raised when the FDE key generation fails."""

    def __init__(self, message):
        self.message = message


class FDERecoveryKeyManager(ManagerPlugin):
    """Plugin that generates FDE recovery keys."""

    truncation_indicator = "\n**OUTPUT TRUNCATED**"

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

        If the recovery key is successfully generated, we will attempt to add the recovery key
        to the message just before sending it to server.

        :message: A message of type "fde-recovery-key".
        """
        opid = message["operation-id"]

        try:
            # check if the snap is installed and it is possible to use
            # await self._send_fde_recovery_key(opid, FAILED, "fde recovery key can't be generated")

            # check if the recovery key is already generated
            recovery_key_exists = False
            recovery_key, key_id = await self._generate_recovery_key()
            result = await self._update_recovery_key(key_id, recovery_key_exists)

            self.registry.broker.update_exchange_state("recovery-key", recovery_key)

            await self._send_fde_recovery_key(opid, True, result)
        except ProcessFailedError as e:
            await self._send_fde_recovery_key(opid, False, e.data, e.exit_code)
        except Exception as e:
            await self._send_fde_recovery_key(opid, False, str(e))

    async def _send_fde_recovery_key(
        self,
        opid: int,
        successful: bool,
        result_text: str,
        result_code: int | None = None,
    ) -> None:
        """Queues a `fde-recovery-key` message to Landscape Server."""

        message = {
            "type": "fde-recovery-key",
            "operation-id": opid,
            "successful": successful,
            "result-text": result_text,
        }
        if result_code is not None:
            message["result-code"] = result_code

        return await self.registry.broker.send_message(
            message,
            self._session_id,
            True,
        )

    def _spawn_process(self, args: list[str]) -> Deferred:
        """Execute the command in a non-blocking subprocess.

        :param args: List of arguments to pass to the process.

        :returns: the deferred result of the process
        """

        protocol = ProcessAccumulationProtocol(
            self.registry.reactor,
            self.registry.config.script_output_limit,
            self.truncation_indicator,
        )
        reactor.spawnProcess(
            protocol,
            FDE_EXECUTABLE,
            args=args,
        )

        return protocol.result_deferred

    async def _generate_recovery_key(
        self,
    ) -> Tuple[str, str]:
        """Generates the recovery key and a key-id used to update the recovery key keyslots.

        :raises ProcessFailedError: If the FDE key process exits with an error.
        :raises FDEKeyGenerationError: If the process does not return a valid response.
        """

        # POST /v2/system-volumes action=generate-recovery-key
        args = ["cat", "generate-key-output.txt"]
        result = await self._spawn_process(args)

        try:
            generate_result = json.loads(result)
            recovery_key = generate_result["recovery-key"]
            key_id = generate_result["key-id"]
        except (json.JSONDecodeError, KeyError) as e:
            raise FDEKeyError(f"Failed to parse result: {e}")

        return recovery_key, key_id

    async def _update_recovery_key(self, key_id: str, recovery_key_exists: bool) -> str:
        """Generates the recovery key and a key-id used to update the recovery key keyslots.

        :key_id: The id used to authorize the recovery key update.

        :raises ProcessFailedError: If the call exits with an error.
        """

        # POST /v2/system-volumes action=? key-id=key_id
        args = ["cat"]
        if recovery_key_exists:
            # action=replace-recovery-key
            args.append("/home/ubuntu/landscape-client/add-key-output.txt")
        else:
            # action=add-recovery-key
            args.append("/home/ubuntu/landscape-client/add-key-output.txt")

        return await self._spawn_process(args)
