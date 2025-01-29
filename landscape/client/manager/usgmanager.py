import glob
import os
import shutil
from pathlib import Path
from typing import Any
from typing import Dict
from typing import Optional
from typing import Tuple
from typing import Union

from twisted.internet import reactor
from twisted.internet.defer import Deferred

from landscape.client.attachments import save_attachments
from landscape.client.manager.plugin import FAILED
from landscape.client.manager.plugin import ManagerPlugin
from landscape.client.manager.plugin import SUCCEEDED
from landscape.client.manager.scriptexecution import (
    ProcessAccumulationProtocol,
)
from landscape.client.manager.scriptexecution import ProcessFailedError

REBOOT_REQUIRED_FILE = "/var/run/reboot-required"
REBOOT_REQUIRED_PKGS_FILE = REBOOT_REQUIRED_FILE + ".pkgs"
TAILORING_FILE_DIR = "usg-tailoring-files"
# USG CLI param used to specify a customization XML file.
TAILORING_FILE_PARAM = "--tailoring-file"
USG_AUDIT_RESULTS_GLOB = "/var/lib/usg/usg-results-*.xml"
USG_EXECUTABLE = "usg"
USG_EXECUTABLE_ABS = "/usr/sbin/usg"
USG_NOT_FOUND = (
    "USG is not installed on this client. See "
    "https://ubuntu.com/security/certifications/docs/disa-stig/installation"
)


class UsgManager(ManagerPlugin):
    """Plugin that performs Ubuntu Security Guide actions.
    See https://ubuntu.com/security/certifications/docs/usg for more
    information.

    It supports two actions:
        - audit: checks for compliance against a CIS or DISA-STIG profile,
          creating an XML report.
        - fix: modifies the system to comply with a CIS or DISA-STIG profile.
    """

    truncation_indicator = "\n**OUTPUT TRUNCATED**"

    def register(self, registry):
        super().register(registry)
        registry.register_message(
            "usg",
            self.handle_usg_message,
        )

    async def handle_usg_message(self, message: Dict[str, Any]) -> None:
        """Executes usg if we can, then responds to `message`.

        If the usg action was "audit", a second message is also sent, reporting
        the audit result.

        :message: A message of type "usg".
        """
        opid = message["operation-id"]

        if not self._has_usg():
            await self._respond(FAILED, USG_NOT_FOUND, opid)
            return

        action = message["action"]
        profile = message["profile"]
        tailoring_file = message.get("tailoring-file")

        try:
            result = await self._usg_operation(
                action,
                profile,
                tailoring_file,
            )
            await self._respond(SUCCEEDED, result, opid)

            if action == "audit":
                await self._send_audit_report()
            if action == "fix":
                self._set_reboot_required()
        except ProcessFailedError as e:
            await self._respond(FAILED, e.data, opid)
        except Exception as e:
            await self._respond(FAILED, str(e), opid)

    def _get_last_audit_results(self) -> Union[str, None]:
        """Returns the file path of the most recently produced audit report. If
        no audit reports exist, returns `None`.
        """
        audit_files = glob.glob(USG_AUDIT_RESULTS_GLOB)
        if not audit_files:
            return None

        last_audit_results = max(audit_files, key=os.path.getctime)

        return last_audit_results

    def _has_usg(self) -> bool:
        """Returns `True` if the USG CLI is present and executable."""
        return shutil.which(USG_EXECUTABLE_ABS) is not None

    def _respond(
        self,
        status: int,
        data: Union[str, bytes],
        opid: int,
    ) -> None:
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

    async def _save_attachment(
        self,
        attachment: Union[Tuple[str, int], None],
    ) -> Union[str, None]:
        """Downloads `attachment` from Landscape Server and saves it in the
        data directory's `TAILORING_FILE_DIR`.

        :param attachment: A tuple of filename and attachment ID.

        :returns: The downloaded attachment's path or `None` if no attachment
            exists.
        """
        if not attachment:
            return None

        attachment_dir = os.path.join(
            self.registry.config.data_path,
            TAILORING_FILE_DIR,
        )
        os.makedirs(attachment_dir, mode=0o700, exist_ok=True)

        attachment_path = os.path.join(attachment_dir, attachment[1])

        await save_attachments(
            self.registry.config,
            (attachment,),
            attachment_dir,
        )

        return attachment_path

    async def _send_audit_report(self) -> None:
        """Queues a `usg-audit` message to Landscape Server, containing the
        most recent audit report.
        """
        last_result = self._get_last_audit_results()

        if last_result is None:
            return

        with open(last_result, "rb") as audit_results:
            message = {"type": "usg-audit", "report": audit_results.read()}

        return await self.registry.broker.send_message(
            message,
            self._session_id,
            True,
        )

    def _set_reboot_required(self) -> None:
        """Attempts to indicate through the reboot-required mechanism that this
        system should reboot due to USG.
        """
        path = Path(REBOOT_REQUIRED_FILE)
        path.touch(exist_ok=True)

        if os.path.exists(REBOOT_REQUIRED_PKGS_FILE):
            with open(REBOOT_REQUIRED_PKGS_FILE, "r") as reboot_required_pkg:
                if any(line == USG_EXECUTABLE for line in reboot_required_pkg):
                    # It's already in there, no need to add it.
                    return

        with open(REBOOT_REQUIRED_PKGS_FILE, "a") as reboot_required_pkg:
            reboot_required_pkg.write(f"\n{USG_EXECUTABLE}\n")

    def _spawn_usg(
        self,
        action: str,
        profile: str,
        tailoring_file: Optional[str] = None,
    ) -> Deferred:
        """Execute the correct `usg` command for message in a non-blocking
        subprocess.

        :param action: The USG action to perform - one of "audit" or "fix".
        :param profile: The USG benchmark profile to use.
        :param tailoring_file: Path of the customization file to use.

        :returns: the deferred result of the usg process
        """
        args = [action, profile]

        if tailoring_file is not None:
            args.extend([TAILORING_FILE_PARAM, tailoring_file])

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

    async def _usg_operation(
        self,
        action: str,
        profile: str,
        tailoring_file: Union[Tuple[str, int]],
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
        attachment = await self._save_attachment(tailoring_file)

        try:
            result = await self._spawn_usg(action, profile, attachment)
            return result
        finally:
            # Clean up attachment files.
            if attachment:
                try:
                    os.unlink(attachment)
                except Exception:
                    pass
