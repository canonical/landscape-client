import json
import yaml
from unittest import mock

from landscape.client.monitor.livepatch import LivePatch
from landscape.client.tests.helpers import LandscapeTest, MonitorHelper


def subprocess_livepatch_mock(*args, **kwargs):
    """Mocks a json and yaml (humane) output"""
    data = {'Test': 'test', 'Last-Check': 1, 'Uptime': 1, 'last check': 1}
    if 'json' in args[0]:
        output = json.dumps(data)
    elif 'humane' in args[0]:
        output = yaml.dump(data)
    return mock.Mock(stdout=output, stderr="", returncode=0)


class LivePatchTest(LandscapeTest):
    """Livepatch status plugin tests."""

    helpers = [MonitorHelper]

    def setUp(self):
        super(LivePatchTest, self).setUp()
        self.mstore.set_accepted_types(["livepatch"])

    def test_livepatch(self):
        """Tests calling livepatch status."""
        plugin = LivePatch()
        self.monitor.add(plugin)

        with mock.patch("subprocess.run") as run_mock:
            run_mock.side_effect = subprocess_livepatch_mock
            plugin.exchange()

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
        self.monitor.add(plugin)

        with mock.patch("subprocess.run") as run_mock:
            run_mock.side_effect = FileNotFoundError("Not found!")
            plugin.exchange()

        messages = self.mstore.get_pending_messages()
        message = json.loads(messages[0]["livepatch"])
        self.assertTrue(len(messages) > 0)
        self.assertTrue(message["json"]["error"])
        self.assertTrue(message["humane"]["error"])
        self.assertEqual(message["json"]["return_code"], -1)
        self.assertEqual(message["humane"]["return_code"], -1)

    def test_undefined_exception(self):
        """Tests calling livepatch when random exception occurs"""
        plugin = LivePatch()
        self.monitor.add(plugin)

        with mock.patch("subprocess.run") as run_mock:
            run_mock.side_effect = ValueError("Not found!")
            plugin.exchange()

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
        self.monitor.add(plugin)

        invalid_data = "'"
        with mock.patch("subprocess.run") as run_mock:
            run_mock.return_value = mock.Mock(stdout=invalid_data)
            run_mock.return_value.returncode = 0
            plugin.exchange()

        messages = self.mstore.get_pending_messages()
        message = json.loads(messages[0]["livepatch"])
        self.assertTrue(len(messages) > 0)
        self.assertTrue(message["json"]["error"])
        self.assertTrue(message["humane"]["error"])
        self.assertEqual(message["json"]["output"], invalid_data)
        self.assertEqual(message["humane"]["output"], invalid_data)

    def test_empty_string(self):
        """
        If livepatch is disabled, stdout is empty string
        """
        plugin = LivePatch()
        self.monitor.add(plugin)

        invalid_data = ""
        with mock.patch("subprocess.run") as run_mock:
            run_mock.return_value = mock.Mock(stdout=invalid_data,
                                              stderr='Error')
            run_mock.return_value.returncode = 1
            plugin.exchange()

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
        self.monitor.add(plugin)

        with mock.patch("subprocess.run") as run_mock:
            run_mock.side_effect = subprocess_livepatch_mock
            plugin.exchange()

        messages = self.mstore.get_pending_messages()
        self.assertTrue(len(messages) > 0)
        message = json.loads(messages[0]["livepatch"])
        self.assertNotIn("Uptime", message["json"]["output"])
        self.assertNotIn("Last-Check", message["json"]["output"])
        self.assertNotIn("last check", message["humane"]["output"])
