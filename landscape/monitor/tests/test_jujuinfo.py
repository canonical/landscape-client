import json
import os

from landscape.monitor.jujuinfo import JujuInfo
from landscape.tests.helpers import LandscapeTest, MonitorHelper


SAMPLE_JUJU_INFO = json.dumps({"environment-uuid": "DEAD-BEEF",
                               "unit-name": "juju-unit-name",
                               "api-addresses": "10.0.3.1:17070",
                               "private-address": "127.0.0.1"})


class JujuInfoTest(LandscapeTest):

    helpers = [MonitorHelper]

    def setUp(self):
        super(JujuInfoTest, self).setUp()
        self.mstore.set_accepted_types(["juju-info"])
        self.plugin = JujuInfo()
        self.monitor.add(self.plugin)
        self.makeFile(SAMPLE_JUJU_INFO, path=self.config.juju_filename)

    def test_get_sample_juju_info(self):
        """
        Sample data is used to ensure that expected values end up in
        the Juju data reported by the plugin.
        """
        self.plugin.exchange()
        message = self.mstore.get_pending_messages()[0]
        self.assertEqual(message["type"], "juju-info")
        self.assertEqual(message["data"]["environment-uuid"], "DEAD-BEEF")
        self.assertEqual(message["data"]["unit-name"], "juju-unit-name")
        self.assertEqual(message["data"]["api-addresses"], "10.0.3.1:17070")
        self.assertEqual(message["data"]["private-address"], "127.0.0.1")

    def test_juju_info_reported_only_once(self):
        """
        Juju data shouldn't be reported unless it's changed since the
        last time it was reported.
        """
        self.plugin.exchange()
        messages = self.mstore.get_pending_messages()
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0]["type"], "juju-info")

        self.plugin.exchange()
        messages = self.mstore.get_pending_messages()
        self.assertEqual(len(messages), 1)

    def test_report_changed_juju_info(self):
        """
        When juju data changes, the new data should be sent to the
        server.
        """
        self.plugin.exchange()
        message = self.mstore.get_pending_messages()[0]
        self.assertEqual(message["type"], "juju-info")
        self.assertEqual(message["data"]["environment-uuid"], "DEAD-BEEF")
        self.assertEqual(message["data"]["unit-name"], "juju-unit-name")
        self.assertEqual(message["data"]["api-addresses"], "10.0.3.1:17070")
        self.assertEqual(message["data"]["private-address"], "127.0.0.1")

        self.makeFile(
            json.dumps({"environment-uuid": "FEED-BEEF",
                        "unit-name": "changed-unit-name",
                        "api-addresses": "10.0.3.2:17070",
                        "private-address": "127.0.1.1"}),
            path=self.config.juju_filename)
        self.plugin.exchange()
        message = self.mstore.get_pending_messages()[1]
        self.assertEqual(message["type"], "juju-info")
        self.assertEqual(message["data"]["environment-uuid"], "FEED-BEEF")
        self.assertEqual(message["data"]["unit-name"], "changed-unit-name")
        self.assertEqual(message["data"]["api-addresses"], "10.0.3.2:17070")
        self.assertEqual(message["data"]["private-address"], "127.0.1.1")

    def test_no_message_with_invalid_json(self):
        """No Juju message is sent if the JSON file is invalid."""
        self.makeFile("barf", path=self.config.juju_filename)

        self.plugin.exchange()
        messages = self.mstore.get_pending_messages()
        self.assertEqual(messages, [])
        self.log_helper.ignore_errors(ValueError)
        self.assertTrue(
            "Error attempting to read JSON from" in self.logfile.getvalue())

    def test_no_message_with_missing_file(self):
        """No Juju message is sent if the JSON file is missing."""
        os.remove(self.config.juju_filename)

        self.plugin.exchange()
        messages = self.mstore.get_pending_messages()
        self.assertEqual(messages, [])
