import glob
import json
import os
import shutil
from pathlib import Path
import subprocess
from typing import Any

from twisted.internet import reactor
from twisted.internet.defer import Deferred, ensureDeferred

from landscape.client.attachments import save_attachments
from landscape.client.manager.plugin import FAILED, SUCCEEDED, ManagerPlugin
from landscape.client.manager.scriptexecution import (
    ProcessAccumulationProtocol,
    ProcessFailedError,
)


class FDERecoveryKeyManager(ManagerPlugin):
    """Plugin that performs Ubuntu Security Guide actions.
    See https://ubuntu.com/security/certifications/docs/usg for more
    information.

    It supports two actions:
        - audit: checks for compliance against a CIS or DISA-STIG profile,
          creating an XML report.
        - fix: modifies the system to comply with a CIS or DISA-STIG profile.
    """

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
        """Executes usg if we can, then responds to `message`.

        If the usg action was "audit", a second message is also sent, reporting
        the audit result.

        :message: A message of type "fde-recovery-key".
        """
        opid = message["operation-id"]
        runid = message["run-id"]

        # check if the snap is installed
        # await self._respond(FAILED, "fde recovery key can't be generated", opid)

        try:
            result = await self._generate_recovery_key()
            await self._respond(SUCCEEDED, result, opid)

            await self._send_fde_recovery_key(opid, runid)
        except ProcessFailedError as e:
            await self._respond(FAILED, e.data, opid)
        except Exception as e:
            await self._respond(FAILED, str(e), opid)

    def _respond(
        self,
        status: int,
        data: str | bytes,
        opid: int,
    ) -> Deferred:
        """Queues sending a result message for the activity to server."""
        message = {
            "type": "operation-result",
            "status": status,
            "result-text": data,
            "operation-id": opid,
        }

        return self.registry.broker.send_message(
            message,
            self._session_id,
            True,
        )

    async def _send_fde_recovery_key(self, opid: int, runid: str) -> None:
        """Queues a `fde-recovery-key` message to Landscape Server, containing the
        intent to include the FDE recovery key.
        """
        message = {
            "type": "fde-recovery-key",
            "recovery-key": "",
            "result": REQUIRES_RECOVERY_KEY,
            "operation-id": opid,
            "run-id": runid,
        }

        return await self.registry.broker.send_message(
            message,
            self._session_id,
            True,
        )

    def _spawn_usg(
        self,
    ) -> Deferred:
        """Execute the correct `usg` command for message in a non-blocking
        subprocess.

        :param action: The USG action to perform - one of "audit" or "fix".
        :param profile: The USG benchmark profile to use.
        :param tailoring_file: Path of the customization file to use.

        :returns: the deferred result of the usg process
        """
        args = [USG_EXECUTABLE_ABS]

        protocol = ProcessAccumulationProtocol(
            self.registry.reactor,
            self.registry.config.script_output_limit,
            self.truncation_indicator,
        )
        reactor.spawnProcess(
            protocol,
            USG_EXECUTABLE_ABS,
            args=args,
        )

        return protocol.result_deferred

    async def _generate_recovery_key(
        self,
    ) -> str:
        """Runs usg, first downloading `tailoring_file` if it's provided.
        Cleans up the tailoring file as well.

        :action: The USG action: `"audit"` or `"fix"`
        :profile: The USG benchmark profile to use.
        :tailoring_file: The optional USG tailoring XML file to download from
            Landscape Server.

        :raises ProcessFailedError: If the usg process exits with an error.
        :raises HTTPException: If downloading `tailoring_file` fails.
        """

        # POST /v2/system-volumes action=generate-recovery-key
        generation_result = json.loads(
            subprocess.run(
                ["cat", "generate-key-output.txt"],
                check=True,
                timeout=1,
            ).stdout
        )

        recovery_key = generation_result["recovery-key"]
        key_id = generation_result["key-id"]

        # POST /v2/system-volumes action=add-recovery-key
        addition_result = subprocess.run(
            ["cat", "add-key-output.txt"], check=True, timeout=1
        ).stdout

        return addition_result
