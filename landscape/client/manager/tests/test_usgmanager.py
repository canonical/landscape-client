import os
import tempfile
from unittest import mock

from twisted.internet.defer import ensureDeferred

from landscape.client.manager.plugin import FAILED
from landscape.client.manager.plugin import SUCCEEDED
from landscape.client.manager.scriptexecution import ProcessFailedError
from landscape.client.manager.usgmanager import TAILORING_FILE_DIR
from landscape.client.manager.usgmanager import USG_EXECUTABLE
from landscape.client.manager.usgmanager import USG_EXECUTABLE_ABS
from landscape.client.manager.usgmanager import USG_NOT_FOUND
from landscape.client.manager.usgmanager import UsgManager
from landscape.client.tests.helpers import LandscapeTest
from landscape.client.tests.helpers import ManagerHelper

MODULE = "landscape.client.manager.usgmanager"


class UsgManagerTests(LandscapeTest):

    helpers = [ManagerHelper]

    def setUp(self):
        super().setUp()
        self.plugin = UsgManager()
        self.manager.add(self.plugin)

        def process_success(protocol, cmd, *args, **kwargs):
            """Immediately invokes `protocol` as if `cmd` was successful."""
            protocol.result_deferred.callback(b"success!")

        self.tempdir = tempfile.mkdtemp()
        self.spawn_mock = mock.patch(
            MODULE + ".reactor.spawnProcess",
            side_effect=process_success,
        ).start()
        self.audit_result_glob = mock.patch(
            MODULE + ".USG_AUDIT_RESULTS_GLOB",
            new=os.path.join(self.tempdir, "usg-results-*.xml"),
        ).start()

        self.addCleanup(mock.patch.stopall)

    def test_audit(self):
        """An audit message results in an audit run and an audit results
        message.
        """
        which = mock.patch("shutil.which").start()
        send_message = mock.patch.object(
            self.plugin.registry.broker,
            "send_message",
            new=mock.AsyncMock(),
        ).start()
        audit_result = os.path.join(self.tempdir, "usg-results-TEST.xml")

        with open(audit_result, "w") as arfp:
            arfp.write("<test>TEST</test>\n")

        deferred = ensureDeferred(
            self.plugin.handle_usg_message(
                {
                    "operation-id": 1,
                    "action": "audit",
                    "profile": "cis_level1_workstation",
                },
            ),
        )

        def check(_):
            os.unlink(audit_result)

            self.spawn_mock.assert_called_once_with(
                mock.ANY,
                USG_EXECUTABLE_ABS,
                args=["audit", "cis_level1_workstation"],
            )
            which.assert_called_once_with(USG_EXECUTABLE_ABS)
            self.assertEqual(
                send_message.mock_calls,
                [
                    mock.call(
                        {
                            "type": "operation-result",
                            "result-text": b"success!",
                            "status": SUCCEEDED,
                            "operation-id": 1,
                        },
                        self.plugin._session_id,
                        True,
                    ),
                    mock.call(
                        {
                            "type": "usg-audit",
                            "report": b"<test>TEST</test>\n",
                        },
                        self.plugin._session_id,
                        True,
                    ),
                ],
            )

        deferred.addBoth(check)
        return deferred

    def test_no_usg(self):
        """Any message results in a failure response if USG is not
        available.
        """
        which = mock.patch("shutil.which").start()
        which.return_value = None
        send_message = mock.patch.object(
            self.plugin.registry.broker,
            "send_message",
            new=mock.AsyncMock(),
        ).start()

        deferred = ensureDeferred(
            self.plugin.handle_usg_message(
                {
                    "operation-id": 1,
                    "action": "audit",
                    "profile": "cis_level1_workstation",
                },
            ),
        )

        def check(_):
            self.spawn_mock.assert_not_called()
            which.assert_called_once_with(USG_EXECUTABLE_ABS)
            send_message.assert_has_calls(
                [
                    mock.call(
                        {
                            "type": "operation-result",
                            "result-text": USG_NOT_FOUND,
                            "status": FAILED,
                            "operation-id": 1,
                        },
                        self.plugin._session_id,
                        True,
                    ),
                ],
            )

        deferred.addBoth(check)
        return deferred

    def test_fix_reboot_required(self):
        """A successful 'usg fix' results in the reboot required flag being
        set.
        """
        which = mock.patch("shutil.which").start()
        path_touch = mock.patch(MODULE + ".Path.touch").start()
        send_message = mock.patch.object(
            self.plugin.registry.broker,
            "send_message",
            new=mock.AsyncMock(),
        ).start()
        pkgs_file = os.path.join(self.tempdir, "reboot-required.pkgs")
        mock.patch(
            MODULE + ".REBOOT_REQUIRED_PKGS_FILE",
            new=pkgs_file,
        ).start()

        deferred = ensureDeferred(
            self.plugin.handle_usg_message(
                {
                    "operation-id": 1,
                    "action": "fix",
                    "profile": "cis_level1_workstation",
                },
            ),
        )

        def check(_):
            path_touch.assert_called_once_with(exist_ok=True)
            self.spawn_mock.assert_called_once_with(
                mock.ANY,
                USG_EXECUTABLE_ABS,
                args=["fix", "cis_level1_workstation"],
            )
            which.assert_called_once_with(USG_EXECUTABLE_ABS)
            send_message.assert_has_calls(
                [
                    mock.call(
                        {
                            "type": "operation-result",
                            "result-text": b"success!",
                            "status": SUCCEEDED,
                            "operation-id": 1,
                        },
                        self.plugin._session_id,
                        True,
                    ),
                ],
            )

            with open(pkgs_file) as pfp:
                self.assertEqual(f"\n{USG_EXECUTABLE}\n", pfp.read())

            os.unlink(pkgs_file)

        deferred.addBoth(check)
        return deferred

    def test_tailoring_file(self):
        """When a tailoring file is provided, it is downloaded and passed to
        USG CLI.
        """
        mock.patch("shutil.which").start()
        mock.patch.object(
            self.plugin.registry.broker,
            "send_message",
            new=mock.AsyncMock(),
        ).start()
        save_attachments = mock.patch(
            MODULE + ".save_attachments",
            new=mock.AsyncMock(),
        ).start()

        deferred = ensureDeferred(
            self.plugin.handle_usg_message(
                {
                    "operation-id": 1,
                    "action": "audit",
                    "profile": "cis_level1_workstation",
                    "tailoring-file": (83497, "test-tailoring.xml"),
                },
            ),
        )

        def check(_):
            tailoring_file_path = os.path.join(
                self.plugin.registry.config.data_path,
                TAILORING_FILE_DIR,
                "test-tailoring.xml",
            )
            self.spawn_mock.assert_called_once_with(
                mock.ANY,
                USG_EXECUTABLE_ABS,
                args=[
                    "audit",
                    "cis_level1_workstation",
                    "--tailoring-file",
                    tailoring_file_path,
                ],
            )

            save_attachments.assert_called_once_with(
                self.plugin.registry.config,
                ((83497, "test-tailoring.xml"),),
                mock.ANY,
            )

        deferred.addBoth(check)
        return deferred

    def test_process_failed(self):
        """When the USG process errors, the activity fails and the error is
        reported.
        """
        which = mock.patch("shutil.which").start()
        send_message = mock.patch.object(
            self.plugin.registry.broker,
            "send_message",
            new=mock.AsyncMock(),
        ).start()

        def process_fail(protocol, *args, **kwargs):
            protocol.result_deferred.errback(
                ProcessFailedError(b"failed!", -1),
            )

        self.spawn_mock.side_effect = process_fail

        deferred = ensureDeferred(
            self.plugin.handle_usg_message(
                {
                    "operation-id": 1,
                    "action": "audit",
                    "profile": "cis_level1_workstation",
                },
            ),
        )

        def check(_):
            self.spawn_mock.assert_called_once_with(
                mock.ANY,
                USG_EXECUTABLE_ABS,
                args=["audit", "cis_level1_workstation"],
            )
            which.assert_called_once_with(USG_EXECUTABLE_ABS)
            self.assertEqual(
                send_message.mock_calls,
                [
                    mock.call(
                        {
                            "type": "operation-result",
                            "result-text": b"failed!",
                            "status": FAILED,
                            "operation-id": 1,
                        },
                        self.plugin._session_id,
                        True,
                    ),
                ],
            )

        deferred.addBoth(check)
        return deferred

    def test_other_exception(self):
        """If any other exception is raised, the activity fails and the error
        is reported.
        """
        which = mock.patch("shutil.which").start()
        send_message = mock.patch.object(
            self.plugin.registry.broker,
            "send_message",
            new=mock.AsyncMock(),
        ).start()
        self.spawn_mock.side_effect = ValueError(
            "something terrible has happened",
        )

        deferred = ensureDeferred(
            self.plugin.handle_usg_message(
                {
                    "operation-id": 1,
                    "action": "audit",
                    "profile": "cis_level1_workstation",
                },
            ),
        )

        def check(_):
            self.spawn_mock.assert_called_once_with(
                mock.ANY,
                USG_EXECUTABLE_ABS,
                args=["audit", "cis_level1_workstation"],
            )
            which.assert_called_once_with(USG_EXECUTABLE_ABS)
            self.assertEqual(
                send_message.mock_calls,
                [
                    mock.call(
                        {
                            "type": "operation-result",
                            "result-text": "something terrible has happened",
                            "status": FAILED,
                            "operation-id": 1,
                        },
                        self.plugin._session_id,
                        True,
                    ),
                ],
            )

        deferred.addBoth(check)
        return deferred
