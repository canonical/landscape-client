import json
import yaml
from unittest import mock

from landscape.client.manager.livepatch import LivePatch, get_livepatch_status
from landscape.client.tests.helpers import LandscapeTest, ManagerHelper


def subprocess_livepatch_mock(*args, **kwargs):
    """Mocks a json and yaml (humane) output"""
    data = {"Test": "test", "Last-Check": 1, "Uptime": 1, "last check": 1}
    if "json" in args[0]:
        output = json.dumps(data)
    elif "humane" in args[0]:
        output = yaml.dump(data)
    return mock.Mock(stdout=output, stderr="", returncode=0)


class LivePatchTest(LandscapeTest):
    """Livepatch status plugin tests."""

    helpers = [ManagerHelper]

    def setUp(self):
        super(LivePatchTest, self).setUp()
        self.mstore = self.broker_service.message_store
        self.mstore.set_accepted_types(["livepatch"])

    def test_livepatch(self):
        """Tests calling livepatch status."""
        plugin = LivePatch()

        with mock.patch("subprocess.run") as run_mock:
            run_mock.side_effect = subprocess_livepatch_mock
            self.manager.add(plugin)
            plugin.run()

        messages = self.mstore.get_pending_messages()
        self.assertTrue(len(messages) > 0)
        message = json.loads(messages[0]["livepatch"])
        self.assertEqual(message["json"]["output"]["Test"], "test")
        self.assertEqual(message["humane"]["output"]["Test"], "test")
        self.assertEqual(message["json"]["return_code"], 0)
        self.assertEqual(message["humane"]["return_code"], 0)
        self.assertFalse(message["humane"]["error"])
        self.assertFalse(message["json"]["error"])

    def test_livepatch_when_not_installed(self):
        """Tests calling livepatch when it is not installed."""
        plugin = LivePatch()

        with mock.patch("subprocess.run") as run_mock:
            run_mock.side_effect = FileNotFoundError("Not found!")
            self.manager.add(plugin)
            plugin.run()

        messages = self.mstore.get_pending_messages()
        message = json.loads(messages[0]["livepatch"])
        self.assertTrue(len(messages) > 0)
        self.assertTrue(message["json"]["error"])
        self.assertTrue(message["humane"]["error"])
        self.assertEqual(message["json"]["return_code"], -1)
        self.assertEqual(message["humane"]["return_code"], -1)

    @mock.patch("landscape.client.manager.livepatch.logging.error")
    def test_undefined_exception(self, logger_mock):
        """Tests calling livepatch when random exception occurs"""
        plugin = LivePatch()

        with mock.patch("subprocess.run") as run_mock:
            run_mock.side_effect = ValueError("Not found!")
            self.manager.add(plugin)
            plugin.run()

        logger_mock.assert_called()

        messages = self.mstore.get_pending_messages()
        message = json.loads(messages[0]["livepatch"])
        self.assertTrue(len(messages) > 0)
        self.assertTrue(message["json"]["error"])
        self.assertTrue(message["humane"]["error"])
        self.assertEqual(message["json"]["return_code"], -2)
        self.assertEqual(message["humane"]["return_code"], -2)

    def test_yaml_json_parse_error(self):
        """
        If json or yaml parsing error than show exception and unparsed data
        """
        plugin = LivePatch()

        invalid_data = "'"
        with mock.patch("subprocess.run") as run_mock:
            run_mock.return_value = mock.Mock(stdout=invalid_data)
            run_mock.return_value.returncode = 0
            self.manager.add(plugin)
            plugin.run()

        messages = self.mstore.get_pending_messages()
        message = json.loads(messages[0]["livepatch"])
        self.assertTrue(len(messages) > 0)
        self.assertTrue(message["json"]["error"])
        self.assertTrue(message["humane"]["error"])
        self.assertEqual(message["json"]["output"], invalid_data)
        self.assertEqual(message["humane"]["output"], invalid_data)

    def test_yaml_parse_status_fail_message(self):
        """
        Livepatch status may return values that are not possible to be parsed
        with default yaml. Ensure that outputs similar to "server check-in:
        failed: fail message" will be parsed without a parser error.
        """
        fail_key = "fail message"
        fail_value = "may have: multiple: colons"
        fail_message_data = f"{fail_key}: {fail_value}"

        message = []
        with mock.patch("subprocess.run") as run_mock:
            run_mock.return_value = mock.Mock(stdout=fail_message_data)
            run_mock.return_value.stderr = ""
            run_mock.return_value.returncode = 0
            message = get_livepatch_status(format_type="humane")

        self.assertTrue(len(message) > 0)
        self.assertEqual(message["output"][fail_key], fail_value)
        self.assertEqual(message["return_code"], 0)
        self.assertFalse(message["error"])

    def test_empty_string(self):
        """
        If livepatch is disabled, stdout is empty string
        """
        plugin = LivePatch()

        invalid_data = ""
        with mock.patch("subprocess.run") as run_mock:
            run_mock.return_value = mock.Mock(
                stdout=invalid_data, stderr="Error"
            )
            run_mock.return_value.returncode = 1
            self.manager.add(plugin)
            plugin.run()

        messages = self.mstore.get_pending_messages()
        message = json.loads(messages[0]["livepatch"])
        self.assertTrue(len(messages) > 0)
        self.assertTrue(message["json"]["error"])
        self.assertTrue(message["humane"]["error"])
        self.assertEqual(message["humane"]["return_code"], 1)
        self.assertEqual(message["json"]["output"], invalid_data)
        self.assertEqual(message["humane"]["output"], invalid_data)

    def test_timestamped_fields_deleted(self):
        """This is so data doesn't keep getting sent if not changed"""

        plugin = LivePatch()

        with mock.patch("subprocess.run") as run_mock:
            run_mock.side_effect = subprocess_livepatch_mock
            self.manager.add(plugin)
            plugin.run()

        messages = self.mstore.get_pending_messages()
        self.assertTrue(len(messages) > 0)
        message = json.loads(messages[0]["livepatch"])
        self.assertNotIn("Uptime", message["json"]["output"])
        self.assertNotIn("Last-Check", message["json"]["output"])
        self.assertNotIn("last check", message["humane"]["output"])
