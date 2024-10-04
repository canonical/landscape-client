import json
from unittest import mock

from landscape.client.monitor.cloudinit import CloudInit
from landscape.client.tests.helpers import LandscapeTest
from landscape.client.tests.helpers import MonitorHelper


def subprocess_cloud_init_mock(*args, **kwargs):
    """Mock a cloud-init subprocess output."""
    data = {"availability_zone": "us-east-1"}
    output = json.dumps(data)
    return mock.Mock(stdout=output, stderr="", returncode=0)


class CloudInitTest(LandscapeTest):
    """Cloud init plugin tests."""

    helpers = [MonitorHelper]

    def setUp(self):
        super(CloudInitTest, self).setUp()
        self.mstore.set_accepted_types(["cloud-init"])

    def test_cloud_init(self):
        """Test calling cloud-init."""
        plugin = CloudInit()

        with mock.patch("subprocess.run") as run_mock:
            run_mock.side_effect = subprocess_cloud_init_mock
            self.monitor.add(plugin)
            plugin.exchange()

        messages = self.mstore.get_pending_messages()
        self.assertTrue(len(messages) > 0)
        message = json.loads(messages[0]["cloud-init"])
        self.assertEqual(message["output"]["availability_zone"], "us-east-1")
        self.assertEqual(message["return_code"], 0)
        self.assertFalse(message["error"])

    def test_cloud_init_when_not_installed(self):
        """Tests calling cloud-init when it is not installed."""
        plugin = CloudInit()

        with mock.patch("subprocess.run") as run_mock:
            run_mock.side_effect = FileNotFoundError("Not found!")
            self.monitor.add(plugin)
            plugin.exchange()

        messages = self.mstore.get_pending_messages()
        message = json.loads(messages[0]["cloud-init"])
        self.assertTrue(len(messages) > 0)
        self.assertTrue(message["error"])
        self.assertEqual(message["return_code"], -1)
        self.assertEqual({}, message["output"])

    def test_undefined_exception(self):
        """Test calling cloud-init when a random exception occurs."""
        plugin = CloudInit()

        with mock.patch("subprocess.run") as run_mock:
            run_mock.side_effect = ValueError("Not found!")
            self.monitor.add(plugin)
            plugin.exchange()

        messages = self.mstore.get_pending_messages()
        message = json.loads(messages[0]["cloud-init"])
        self.assertTrue(len(messages) > 0)
        self.assertTrue(message["error"])
        self.assertEqual(message["return_code"], -2)
        self.assertEqual({}, message["output"])

    def test_json_parse_error(self):
        """
        If a Json parsing error occurs, show the exception and unparsed data.
        """
        plugin = CloudInit()

        with mock.patch("subprocess.run") as run_mock:
            run_mock.return_value = mock.Mock(stdout="'")
            run_mock.return_value.returncode = 0
            self.monitor.add(plugin)
            plugin.exchange()

        messages = self.mstore.get_pending_messages()
        message = json.loads(messages[0]["cloud-init"])
        self.assertTrue(len(messages) > 0)
        self.assertTrue(message["error"])
        self.assertEqual({}, message["output"])

    def test_empty_string(self):
        """
        If cloud-init is disabled, stdout is an empty string.
        """
        plugin = CloudInit()

        with mock.patch("subprocess.run") as run_mock:
            run_mock.return_value = mock.Mock(stdout="", stderr="Error")
            run_mock.return_value.returncode = 1
            self.monitor.add(plugin)
            plugin.exchange()

        messages = self.mstore.get_pending_messages()
        message = json.loads(messages[0]["cloud-init"])
        self.assertTrue(len(messages) > 0)
        self.assertTrue(message["error"])
        self.assertEqual(message["return_code"], 1)
        self.assertEqual({}, message["output"])
