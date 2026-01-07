import json
from typing import Any, Tuple

from twisted.internet import reactor
from twisted.internet.defer import Deferred, ensureDeferred

from landscape.client.manager.plugin import (
    ManagerPlugin,
)
from landscape.client.manager.scriptexecution import (
    ProcessAccumulationProtocol,
    ProcessFailedError,
)
from landscape.lib.user import get_user_info

CURL = "curl"
SNAP_CURL_ARGS = [CURL, "--unix-socket", "/run/snapd.socket"]


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

    async def _generate_recovery_key(
        self,
    ) -> Tuple[str, str]:
        """Generates the recovery key and a key-id used to update the recovery key keyslots.

        :raises ProcessFailedError: If the FDE key process exits with an error.
        :raises FDEKeyGenerationError: If the process does not return a valid response.
        """

        # POST /v2/system-volumes action=generate-recovery-key
        body = {"action": "generate-recovery-key"}
        result = await self._snap_post("v2/system-volumes", body)

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
        body = {"key-id": key_id, "keyslots": [{"name": "landscape-recovery-key"}]}
        if recovery_key_exists:
            # action=replace-recovery-key
            body["action"] = "replace-recovery-key"
        else:
            # action=add-recovery-key
            body["action"] = "add-recovery-key"

        return await self._snap_post("v2/system-volumes", body)

    def _spawn_process(self, command: str, args: list[str]) -> Deferred:
        """Execute the command in a non-blocking subprocess.

        :param args: List of arguments to pass to the process.

        :returns: the deferred result of the process
        """

        protocol = ProcessAccumulationProtocol(
            self.registry.reactor,
            self.registry.config.script_output_limit,
            self.truncation_indicator,
        )
        uid, gid, path = get_user_info("root")

        reactor.spawnProcess(
            protocol,
            command,
            args=args,
            uid=uid,
            gid=gid,
            path=path,
        )

        return protocol.result_deferred

    def _snap_get(self, endpoint: str) -> Deferred:
        """Spawns a process to call GET on a snapd endpoint.

        :param endpoint: Endpoint to get. Don't include a leading /

        :returns: the deferred result of the process
        """
        url = f"http://localhost/{endpoint}"

        args = SNAP_CURL_ARGS + ["-X", "GET", url]
        return self._spawn_process(CURL, args)

    def _snap_post(self, endpoint: str, body: dict) -> Deferred:
        """Spawns a process to call POST on a snapd endpoint.

        :param endpoint: Endpoint to get. Don't include a leading /
        :param body: JSON encodable body to pass to the endpoint.

        :returns: the deferred result of the process
        """
        url = f"http://localhost/{endpoint}"

        contents = json.dumps(body)

        args = SNAP_CURL_ARGS + [
            "-X",
            "POST",
            url,
            "-H",
            "Content-Type: application/json",
            "-d",
            contents,
        ]
        return self._spawn_process(CURL, args)
